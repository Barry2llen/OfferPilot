from __future__ import annotations

import json
from collections.abc import Sequence
from typing import cast

import pytest
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from agent.agents.supervisor.agent import SupervisorAgent
from agent.base import BaseAgentState, ContextCompactionSnapshot, GraphRuntime
from agent.compaction import (
    AutoCompactLayer,
    CompactedMessage,
    CompactionContext,
    CompactionRequest,
    ContextBudget,
    ContextCompactionError,
    ContextCompactionSummary,
    DefaultContextBudgetPolicy,
    HistoricalAttachmentCompactor,
    MessageRef,
    PipelineCompactor,
    ToolResultCompactor,
    build_supervisor_compactor,
    model_messages_for_state,
)
from agent.compaction.protection import message_groups, protect_entries
from agent.compaction.protocols import ToolSchema
from agent.compaction.token_counter import ApproximateTokenCounter
from agent.graphs.model_call import ModelCallGraph
from agent.models.structured import StructuredModel
from schemas.config import Config, ContextCompactionConfig
from schemas.model_provider import ModelProvider
from schemas.model_selection import ModelSelection


def build_test_pipeline(
    runnable: object,
    *,
    layers: Sequence[ToolResultCompactor] = (),
) -> PipelineCompactor:
    counter = CharacterTokenCounter()
    return PipelineCompactor(
        token_counter=counter,
        keep_recent_turns=4,
        layers=(
            *layers,
            AutoCompactLayer(
                budget_policy=DefaultContextBudgetPolicy(ContextCompactionConfig()),
                token_counter=counter,
                structured_model_loader=FakeStructuredModelLoader(runnable),
            ),
        ),
    )


class CharacterTokenCounter:
    async def acount(
        self,
        *,
        system_prompts: Sequence[BaseMessage],
        messages: Sequence[BaseMessage],
        tools: Sequence[ToolSchema],
    ) -> int:
        return sum(
            len(str(message.content)) for message in (*system_prompts, *messages)
        ) + sum(len(str(tool)) for tool in tools)


def make_selection(
    *,
    provider: str = "OpenAI",
    name: str = "default-openai",
    model_name: str = "gpt-4o-mini",
) -> ModelSelection:
    return ModelSelection(
        provider=ModelProvider(provider=provider, name=name),
        model_name=model_name,
    )


def make_runtime(
    messages: Sequence[BaseMessage],
    *,
    model: ModelSelection | None = None,
) -> GraphRuntime:
    return GraphRuntime[BaseAgentState](
        state={
            "messages": list(messages),
            "model": model or make_selection(),
        },
        additional_args=(),
        additional_keywords={},
    )


def make_request(
    messages: Sequence[BaseMessage],
    *,
    budget: ContextBudget | None = None,
    model: ModelSelection | None = None,
) -> CompactionRequest:
    return CompactionRequest(
        runtime=make_runtime(messages, model=model),
        system_prompts=(),
        tools=(),
        budget=budget
        or ContextBudget(
            max_context_tokens=1_000,
            reserved_output_tokens=100,
            safety_margin_tokens=0,
        ),
    )


def make_context(
    messages: Sequence[BaseMessage],
    *,
    keep_recent_turns: int = 1,
    current_tokens: int = 0,
    budget: ContextBudget | None = None,
) -> CompactionContext:
    request = make_request(messages, budget=budget)
    entries = tuple(
        CompactedMessage(
            rendered=message,
            sources=(
                MessageRef(
                    index=index,
                    message_id=getattr(message, "id", None),
                ),
            ),
            kind="identity",
            layer="identity",
        )
        for index, message in enumerate(messages)
    )
    return CompactionContext(
        request=request,
        entries=protect_entries(entries, keep_recent_turns=keep_recent_turns),
        current_tokens=current_tokens,
    )


def exchange(
    call_id: str, result: str, *, return_direct: bool = False
) -> list[BaseMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[{"name": "lookup", "args": {"q": call_id}, "id": call_id}],
        ),
        ToolMessage(
            content=result,
            tool_call_id=call_id,
            name="lookup",
            additional_kwargs={"return_direct": return_direct},
        ),
    ]


class RecordingLayer:
    name = "recording"

    def __init__(self) -> None:
        self.calls = 0
        self.tokens_seen: list[int] = []

    async def apply(self, context: CompactionContext) -> CompactionContext:
        self.calls += 1
        self.tokens_seen.append(context.current_tokens)
        return context


class RewriteLayer:
    name = "rewrite"

    async def apply(self, context: CompactionContext) -> CompactionContext:
        entries = list(context.entries)
        for index, entry in enumerate(entries):
            if not entry.protected and isinstance(entry.rendered, HumanMessage):
                entries[index] = CompactedMessage(
                    rendered=HumanMessage(content="short"),
                    sources=entry.sources,
                    kind="rewrite",
                    layer=self.name,
                )
                break
        return context.with_entries(tuple(entries))


async def test_pipeline_calls_every_layer_without_global_budget_gate() -> None:
    recorder = RecordingLayer()
    counter = CharacterTokenCounter()
    messages = [HumanMessage(content="historical " * 20), HumanMessage(content="now")]
    result = await PipelineCompactor(
        token_counter=counter,
        keep_recent_turns=1,
        layers=(recorder,),
    ).acompact(
        make_request(
            messages,
            budget=ContextBudget(
                max_context_tokens=1_000,
                reserved_output_tokens=100,
                safety_margin_tokens=0,
            ),
        )
    )

    assert recorder.calls == 1
    assert result.applied_layers == ()
    assert result.original_tokens == result.compacted_tokens


async def test_pipeline_recounts_and_passes_current_tokens_to_next_layer() -> None:
    first = RewriteLayer()
    second = RecordingLayer()
    messages = [HumanMessage(content="historical " * 20), HumanMessage(content="now")]

    result = await PipelineCompactor(
        token_counter=CharacterTokenCounter(),
        keep_recent_turns=1,
        layers=(first, second),
    ).acompact(make_request(messages))

    assert second.calls == 1
    assert second.tokens_seen == [result.compacted_tokens]
    assert result.applied_layers == ("rewrite",)
    assert result.model_messages[-1] == messages[-1]


def test_protection_rejects_incomplete_exchange_before_rewriting() -> None:
    messages = [
        HumanMessage(content="old one"),
        *exchange("old-call", "old result"),
        HumanMessage(content="recent"),
        AIMessage(
            content="",
            tool_calls=[{"name": "lookup", "args": {}, "id": "incomplete"}],
        ),
    ]
    with pytest.raises(ContextCompactionError, match="unfinished tool call"):
        make_context(messages, keep_recent_turns=1)


def test_protection_does_not_count_persisted_summary_as_user_turn() -> None:
    entries = (
        CompactedMessage(
            rendered=HumanMessage(
                content="[Historical context summary]\nprior context"
            ),
            sources=(MessageRef(index=0, message_id=None),),
            kind="summary",
            layer="auto_compact",
            protected=True,
        ),
        CompactedMessage(
            rendered=AIMessage(content="old answer"),
            sources=(MessageRef(index=1, message_id=None),),
            kind="identity",
            layer="identity",
        ),
        CompactedMessage(
            rendered=HumanMessage(content="recent request"),
            sources=(MessageRef(index=2, message_id=None),),
            kind="identity",
            layer="identity",
        ),
        CompactedMessage(
            rendered=AIMessage(content="recent answer"),
            sources=(MessageRef(index=3, message_id=None),),
            kind="identity",
            layer="identity",
        ),
        CompactedMessage(
            rendered=HumanMessage(content="new request"),
            sources=(MessageRef(index=4, message_id=None),),
            kind="identity",
            layer="identity",
        ),
        CompactedMessage(
            rendered=AIMessage(content="new answer"),
            sources=(MessageRef(index=5, message_id=None),),
            kind="identity",
            layer="identity",
        ),
    )

    protected = protect_entries(entries, keep_recent_turns=4)

    assert [entry.protected for entry in protected] == [
        True,
        False,
        False,
        False,
        True,
        False,
    ]
    assert [entry.recent for entry in protected] == [
        False,
        False,
        True,
        True,
        True,
        True,
    ]


def test_return_direct_does_not_add_an_extra_protection_rule() -> None:
    messages = [
        HumanMessage(content="old"),
        *exchange("old-call", "old result", return_direct=True),
        HumanMessage(content="new"),
        *exchange("new-call", "new result"),
    ]
    entries = make_context(messages, keep_recent_turns=1).entries

    assert entries[0].protected is False
    assert entries[2].protected is False
    assert entries[3].protected is True
    assert entries[4].protected is False
    assert entries[5].protected is False
    assert entries[4].recent and entries[5].recent


async def test_tool_result_compactor_rewrites_only_unprotected_messages() -> None:
    messages = [
        HumanMessage(content="old"),
        *exchange("old-call", "x" * 400),
        HumanMessage(content="middle"),
        *exchange("new-call", "new"),
        HumanMessage(content="latest"),
    ]
    original = messages[2].content
    context = make_context(messages, keep_recent_turns=1)

    result = await ToolResultCompactor(max_characters=80).apply(context)

    assert len(result.actions) == 1
    compacted = result.entries[1].rendered
    assert isinstance(compacted, AIMessage)
    compacted_tool = result.entries[2].rendered
    assert isinstance(compacted_tool, ToolMessage)
    assert len(compacted_tool.content) <= 80
    assert compacted_tool.tool_call_id == "old-call"
    assert compacted_tool.additional_kwargs["return_direct"] is False
    assert "truncated" in compacted_tool.content
    assert messages[2].content == original


async def test_attachment_compactor_preserves_legacy_message_with_no_trusted_boundary() -> (
    None
):
    old = HumanMessage(
        content=[{"type": "text", "text": "old prompt"}],
        additional_kwargs={
            "attachments": [
                {
                    "file_id": "file-1",
                    "original_filename": "resume.pdf",
                    "injection_mode": "text",
                }
            ],
            "display_content": "old prompt",
            "requires_image_input": False,
            "custom": "kept",
        },
    )
    latest = HumanMessage(content="latest")
    context = make_context([old, latest], keep_recent_turns=1)

    result = await HistoricalAttachmentCompactor().apply(context)

    rewritten = result.entries[0].rendered
    assert isinstance(rewritten, HumanMessage)
    assert rewritten == old
    assert not result.actions
    assert rewritten.additional_kwargs == old.additional_kwargs
    assert result.entries[1].rendered == latest
    assert old.content == [{"type": "text", "text": "old prompt"}]


class StaticResolver:
    def __init__(self, selection: ModelSelection) -> None:
        self.selection = selection

    async def aresolve(self, runtime: GraphRuntime) -> ModelSelection:
        del runtime
        return self.selection


class FakeStructuredRunnable:
    def __init__(self, result: ContextCompactionSummary) -> None:
        self.result = result
        self.inputs: list[object] = []
        self.kwargs: list[dict[str, object]] = []
        self.calls = 0

    async def ainvoke(
        self,
        messages: object,
        **kwargs: object,
    ) -> ContextCompactionSummary:
        self.calls += 1
        self.inputs.append(messages)
        self.kwargs.append(kwargs)
        return self.result


class FakeStructuredModelLoader:
    def __init__(self, runnable: object) -> None:
        self.runnable = runnable
        self.selections: list[ModelSelection] = []
        self.schemas: list[type[ContextCompactionSummary]] = []

    def __call__(
        self,
        selection: ModelSelection,
        schema: type[ContextCompactionSummary],
    ) -> StructuredModel[ContextCompactionSummary]:
        self.selections.append(selection)
        self.schemas.append(schema)
        return cast(StructuredModel[ContextCompactionSummary], self.runnable)


def summary_result() -> ContextCompactionSummary:
    return ContextCompactionSummary(
        primary_request_and_intent="Find suitable opportunities and prepare an application",
        key_context_and_constraints=[
            "Prioritize roles matching the user's target criteria."
        ],
        relevant_resources_and_artifacts=[
            "Current job descriptions and search results"
        ],
        issues_and_resolutions=[
            "The initial search was too broad; narrow the criteria."
        ],
        progress_and_decisions=[
            "Use a focused job search and compare the strongest matches."
        ],
        user_message_summaries=["用户希望找到匹配的岗位并准备申请材料"],
        pending_tasks=["Run verification"],
        current_work="Comparing opportunities against the user's criteria",
        optional_next_step="Review the strongest match",
    )


async def test_auto_compact_summarizes_unprotected_history_with_structured_model() -> (
    None
):
    runnable = FakeStructuredRunnable(summary_result())
    loader = FakeStructuredModelLoader(runnable)
    messages = [
        HumanMessage(content="old history" * 800),
        AIMessage(content="old answer"),
        HumanMessage(content="latest request"),
    ]
    counter = CharacterTokenCounter()
    context = make_context(
        messages, keep_recent_turns=1, budget=ContextBudget(10_000, 0, 0)
    )
    context = context.with_current_tokens(
        await counter.acount(
            system_prompts=(),
            messages=messages,
            tools=(),
        )
    )
    policy = DefaultContextBudgetPolicy(ContextCompactionConfig())

    result = await AutoCompactLayer(
        model_resolver=StaticResolver(make_selection(model_name="compact-model")),
        budget_policy=policy,
        token_counter=CharacterTokenCounter(),
        structured_model_loader=loader,
    ).apply(context)

    assert runnable.calls == 1
    assert runnable.kwargs == [{"max_repair_attempts": 0}]
    assert loader.selections[0].model_name == "compact-model"
    assert loader.selections[0].extra_params == {"max_tokens": 4000}
    assert loader.schemas == [ContextCompactionSummary]
    assert len(result.entries) == 2
    assert isinstance(result.entries[0].rendered, HumanMessage)
    assert isinstance(result.entries[0].rendered.content, str)
    assert result.entries[0].rendered.content.startswith("[Historical context summary]")
    assert result.entries[0].sources[0].index == 0
    assert result.entries[0].sources[1].index == 1
    assert result.entries[1].rendered == messages[-1]
    assert result.actions[0].kind == "summarize"
    assert result.entries[0].protected is True

    summary_input = runnable.inputs[0]
    assert isinstance(summary_input, list)
    assert isinstance(summary_input[0], SystemMessage)
    prompt = summary_input[0].content
    assert isinstance(prompt, str)
    assert prompt.startswith("WARNING: DO NOT CALL TOOLS")
    assert "Use at most 4000 total generation tokens" in prompt
    assert "general user workflow" in prompt
    assert "6. User Message Summaries" in prompt
    assert "exactly one concise summary item" in prompt
    assert "Do not quote or reproduce the original text" in prompt
    assert '"无文本请求"' in prompt
    assert "untrusted historical data" in prompt
    assert "attachments" in prompt
    assert "tool_call_id" in prompt
    assert "preserving its original text and order" not in prompt
    assert isinstance(summary_input[1], HumanMessage)
    assert isinstance(summary_input[1].content, str)
    records = json.loads(summary_input[1].content)
    assert records == [
        {"role": "human", "content": messages[0].content},
        {"role": "ai", "content": messages[1].content},
    ]
    for text in (prompt, result.entries[0].rendered.content):
        assert "read_file" not in text and "fetch_context" not in text


async def test_auto_compact_requires_unprotected_history() -> None:
    messages = [HumanMessage(content="x" * 1_001)]
    context = make_context(messages, current_tokens=len(str(messages[0].content)))

    with pytest.raises(ContextCompactionError, match="no eligible history"):
        await AutoCompactLayer(
            budget_policy=DefaultContextBudgetPolicy(ContextCompactionConfig()),
            token_counter=CharacterTokenCounter(),
        ).apply(context)


async def test_auto_compact_does_not_retry_structured_output_failure() -> None:
    class FailingRunnable:
        calls = 0

        async def ainvoke(self, messages: object, **kwargs: object) -> object:
            del messages
            del kwargs
            self.calls += 1
            raise RuntimeError("provider failed")

    runnable = FailingRunnable()
    loader = FakeStructuredModelLoader(runnable)
    context = make_context(
        [HumanMessage(content="x" * 1000), HumanMessage(content="latest")],
        keep_recent_turns=1,
        current_tokens=len("x" * 1000 + "latest"),
    )

    with pytest.raises(ContextCompactionError, match="structured output failed"):
        await AutoCompactLayer(
            budget_policy=DefaultContextBudgetPolicy(ContextCompactionConfig()),
            token_counter=CharacterTokenCounter(),
            structured_model_loader=loader,
        ).apply(context)

    assert runnable.calls == 1


def test_context_compaction_config_no_longer_contains_reasoning_setting() -> None:
    settings = ContextCompactionConfig()

    assert not hasattr(settings, "keep_recent_reasoning_messages")
    assert settings.keep_recent_turns == 4
    assert settings.reserved_output_tokens == 20_000
    assert settings.safety_margin_tokens == 10_000
    assert settings.trigger_input_ratio == 0.80
    assert settings.target_input_ratio == 0.60
    assert settings.summary_max_tokens == 4000


def test_only_enabled_supervisor_path_builds_the_fixed_compaction_pipeline() -> None:
    disabled_config = Config(
        context_compaction=ContextCompactionConfig(enabled=False),
    )
    enabled_config = Config(
        context_compaction=ContextCompactionConfig(enabled=True),
    )

    assert build_supervisor_compactor(disabled_config) is None
    supervisor_compactor = build_supervisor_compactor(enabled_config)
    assert isinstance(supervisor_compactor, PipelineCompactor)
    assert [layer.name for layer in supervisor_compactor.layers] == [
        "historical_tool_results",
        "historical_attachments",
        "auto_compact",
    ]
    assert ModelCallGraph(config=enabled_config).compactor is None
    assert "compact" in SupervisorAgent(config=enabled_config)._model_call_node.nodes
    assert (
        "compact" not in SupervisorAgent(config=disabled_config)._model_call_node.nodes
    )


def test_context_summary_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        ContextCompactionSummary.model_validate(
            {
                **summary_result().model_dump(),
                "unexpected": "must be rejected",
            }
        )


def test_context_summary_uses_general_task_state_fields() -> None:
    payload = summary_result().model_dump()

    assert set(payload) == {
        "primary_request_and_intent",
        "key_context_and_constraints",
        "relevant_resources_and_artifacts",
        "issues_and_resolutions",
        "progress_and_decisions",
        "user_message_summaries",
        "pending_tasks",
        "current_work",
        "optional_next_step",
    }
    assert "all_user_messages" not in payload


def test_context_compaction_summary_requires_all_sections_and_string_lists() -> None:
    missing_field = summary_result().model_dump()
    del missing_field["current_work"]

    with pytest.raises(ValueError):
        ContextCompactionSummary.model_validate(missing_field)

    invalid_list_item = summary_result().model_dump()
    invalid_list_item["key_context_and_constraints"] = [123]

    with pytest.raises(ValueError):
        ContextCompactionSummary.model_validate(invalid_list_item)


async def test_auto_compact_blocks_when_summary_model_has_insufficient_capacity() -> (
    None
):
    runnable = FakeStructuredRunnable(summary_result())
    loader = FakeStructuredModelLoader(runnable)
    messages = [
        HumanMessage(content="historical " * 1000),
        HumanMessage(content="latest"),
    ]
    counter = CharacterTokenCounter()
    context = make_context(messages, budget=ContextBudget(10_000, 0, 0))
    context = context.with_current_tokens(
        await counter.acount(
            system_prompts=(),
            messages=messages,
            tools=(),
        )
    )

    with pytest.raises(ContextCompactionError, match="summary input"):
        await AutoCompactLayer(
            model_resolver=StaticResolver(make_selection(model_name="compact")),
            budget_policy=DefaultContextBudgetPolicy(
                ContextCompactionConfig(model_context_windows={"compact": 5_000})
            ),
            token_counter=counter,
            structured_model_loader=loader,
        ).apply(context)

    assert runnable.calls == 0


async def test_token_counter_includes_reasoning_forwarded_by_deepseek() -> None:
    counter = ApproximateTokenCounter()

    without_reasoning = await counter.acount(
        system_prompts=(),
        messages=[AIMessage(content="answer")],
        tools=(),
    )
    with_reasoning = await counter.acount(
        system_prompts=(),
        messages=[
            AIMessage(
                content="answer",
                additional_kwargs={"reasoning_content": "historical reasoning" * 100},
            )
        ],
        tools=(),
    )

    assert with_reasoning > without_reasoning


def _snapshot_state(
    messages: Sequence[BaseMessage],
    snapshot: ContextCompactionSnapshot,
) -> GraphRuntime:
    return GraphRuntime[BaseAgentState](
        state={
            "messages": list(messages),
            "model": make_selection(),
            "context_compaction": snapshot,
        },
        additional_args=(),
        additional_keywords={},
    )


def _snapshot_request(
    runtime: GraphRuntime,
    *,
    budget: ContextBudget | None = None,
) -> CompactionRequest:
    return CompactionRequest(
        runtime=runtime,
        system_prompts=(),
        tools=(),
        budget=budget
        or ContextBudget(
            max_context_tokens=10_000,
            reserved_output_tokens=100,
            safety_margin_tokens=0,
        ),
    )


async def test_pipeline_reuses_snapshot_and_appends_only_raw_suffix() -> None:
    raw_messages = [
        HumanMessage(content="old user", id="human-old"),
        AIMessage(content="old answer", id="ai-old"),
        HumanMessage(content="new request", id="human-new"),
    ]
    summary = SystemMessage(content="[Historical context summary]\nold context")
    snapshot: ContextCompactionSnapshot = {
        "messages": [summary, raw_messages[1]],
        "source_message_count": 2,
        "source_message_ids": ["human-old", "ai-old"],
        "status": "complete",
        "auto_compacted": True,
    }
    runtime = _snapshot_state(raw_messages, snapshot)
    original_messages = list(raw_messages)

    result = await PipelineCompactor(
        token_counter=CharacterTokenCounter(),
        keep_recent_turns=1,
        layers=(RecordingLayer(),),
    ).acompact(_snapshot_request(runtime))

    assert result.model_messages == [summary, raw_messages[1], raw_messages[2]]
    assert model_messages_for_state(runtime.state) == result.model_messages
    assert runtime.state.get("messages") == original_messages
    assert result.source_message_count == len(raw_messages)
    assert result.source_message_ids == ("human-old", "ai-old", "human-new")


@pytest.mark.parametrize("summary_message_type", [HumanMessage, SystemMessage])
async def test_pipeline_does_not_repeat_summary_without_new_raw_history(
    summary_message_type: type[HumanMessage] | type[SystemMessage],
) -> None:
    raw_messages = [
        HumanMessage(content="old user", id="human-old"),
        AIMessage(content="old answer", id="ai-old"),
    ]
    summary = summary_message_type(content="[Historical context summary]\nold context")
    snapshot: ContextCompactionSnapshot = {
        "messages": [summary, *raw_messages],
        "source_message_count": 2,
        "source_message_ids": ["human-old", "ai-old"],
        "status": "complete",
        "auto_compacted": True,
    }
    runnable = FakeStructuredRunnable(summary_result())
    loader = FakeStructuredModelLoader(runnable)
    runtime = _snapshot_state(raw_messages, snapshot)

    result = await PipelineCompactor(
        token_counter=CharacterTokenCounter(),
        keep_recent_turns=1,
        layers=(
            AutoCompactLayer(
                model_resolver=StaticResolver(make_selection(model_name="compact")),
                budget_policy=DefaultContextBudgetPolicy(ContextCompactionConfig()),
                token_counter=CharacterTokenCounter(),
                structured_model_loader=loader,
            ),
        ),
    ).acompact(_snapshot_request(runtime))

    assert runnable.calls == 0
    assert result.model_messages[0] == summary
    assert result.auto_compacted is True
    assert result.auto_compacted_this_run is False


async def test_pipeline_recompacts_complete_summary_when_budget_shrinks() -> None:
    raw_messages = [
        HumanMessage(content="old user", id="human-old"),
        AIMessage(content="old answer", id="ai-old"),
    ]
    old_summary = SystemMessage(content="[Historical context summary]\n" + "x" * 11_000)
    snapshot: ContextCompactionSnapshot = {
        "messages": [old_summary, *raw_messages[:2]],
        "source_message_count": 2,
        "source_message_ids": ["human-old", "ai-old"],
        "status": "complete",
        "auto_compacted": True,
    }
    runnable = FakeStructuredRunnable(summary_result())
    loader = FakeStructuredModelLoader(runnable)

    result = await PipelineCompactor(
        token_counter=CharacterTokenCounter(),
        keep_recent_turns=1,
        layers=(
            AutoCompactLayer(
                model_resolver=StaticResolver(make_selection(model_name="compact")),
                budget_policy=DefaultContextBudgetPolicy(ContextCompactionConfig()),
                token_counter=CharacterTokenCounter(),
                structured_model_loader=loader,
            ),
        ),
    ).acompact(
        _snapshot_request(
            _snapshot_state(raw_messages, snapshot),
            budget=ContextBudget(
                max_context_tokens=10_000,
                reserved_output_tokens=0,
                safety_margin_tokens=0,
            ),
        )
    )

    assert runnable.calls == 1
    assert result.auto_compacted_this_run is True
    assert result.original_tokens > 10_000
    assert result.compacted_tokens == sum(
        len(str(message.content)) for message in result.model_messages
    )
    assert result.compacted_tokens <= 6_000
    assert (
        sum(
            isinstance(message, HumanMessage)
            and isinstance(message.content, str)
            and message.content.startswith("[Historical context summary]")
            for message in result.model_messages
        )
        == 1
    )


async def test_pipeline_merges_existing_summary_with_new_historical_messages() -> None:
    raw_messages = [
        HumanMessage(content="old user", id="human-old"),
        AIMessage(content="old answer " * 800, id="ai-old"),
        HumanMessage(content="new request", id="human-new"),
    ]
    old_summary = SystemMessage(content="[Historical context summary]\nold context")
    snapshot: ContextCompactionSnapshot = {
        "messages": [old_summary, raw_messages[1]],
        "source_message_count": 2,
        "source_message_ids": ["human-old", "ai-old"],
        "status": "complete",
        "auto_compacted": True,
    }
    runnable = FakeStructuredRunnable(summary_result())
    loader = FakeStructuredModelLoader(runnable)

    result = await PipelineCompactor(
        token_counter=CharacterTokenCounter(),
        keep_recent_turns=1,
        layers=(
            AutoCompactLayer(
                model_resolver=StaticResolver(make_selection(model_name="compact")),
                budget_policy=DefaultContextBudgetPolicy(ContextCompactionConfig()),
                token_counter=CharacterTokenCounter(),
                structured_model_loader=loader,
            ),
        ),
    ).acompact(
        _snapshot_request(
            _snapshot_state(raw_messages, snapshot),
            budget=ContextBudget(
                max_context_tokens=10_000,
                reserved_output_tokens=0,
                safety_margin_tokens=0,
            ),
        )
    )

    assert runnable.calls == 1
    assert result.auto_compacted_this_run is True
    assert (
        sum(
            isinstance(message, HumanMessage)
            and isinstance(message.content, str)
            and message.content.startswith("[Historical context summary]")
            for message in result.model_messages
        )
        == 1
    )
    summary_input = runnable.inputs[0]
    assert isinstance(summary_input, list)
    assert isinstance(summary_input[1], HumanMessage)
    assert isinstance(summary_input[1].content, str)
    records = json.loads(summary_input[1].content)
    assert records[0] == {"role": "prior_summary", "content": old_summary.content}
    assert records[1] == {"role": "ai", "content": raw_messages[1].content}
    assert result.model_messages[-1] == raw_messages[-1]


async def test_pending_snapshot_retries_summary_even_below_threshold() -> None:
    raw_messages = [
        HumanMessage(content="old user", id="human-old"),
        HumanMessage(content="latest", id="human-latest"),
    ]
    snapshot: ContextCompactionSnapshot = {
        "messages": list(raw_messages),
        "source_message_count": 2,
        "source_message_ids": ["human-old", "human-latest"],
        "status": "pending_auto_compact",
        "auto_compacted": False,
    }
    runnable = FakeStructuredRunnable(summary_result())
    loader = FakeStructuredModelLoader(runnable)

    result = await PipelineCompactor(
        token_counter=CharacterTokenCounter(),
        keep_recent_turns=1,
        layers=(
            AutoCompactLayer(
                model_resolver=StaticResolver(make_selection(model_name="compact")),
                budget_policy=DefaultContextBudgetPolicy(ContextCompactionConfig()),
                token_counter=CharacterTokenCounter(),
                structured_model_loader=loader,
            ),
        ),
    ).acompact(_snapshot_request(_snapshot_state(raw_messages, snapshot)))

    assert runnable.calls == 1
    assert result.snapshot_status == "complete"
    assert result.auto_compacted is True


async def test_context_compaction_snapshot_round_trips_through_langgraph_checkpoint() -> (
    None
):
    summary = SystemMessage(content="[Historical context summary]\ncheckpoint")
    snapshot: ContextCompactionSnapshot = {
        "messages": [summary, HumanMessage(content="latest", id="latest")],
        "source_message_count": 2,
        "source_message_ids": ["old", "latest"],
        "status": "complete",
        "auto_compacted": True,
    }
    saver = InMemorySaver()
    graph = StateGraph(BaseAgentState)
    graph.add_node("persist", lambda state: {"context_compaction": snapshot})
    graph.add_edge(START, "persist")
    graph.add_edge("persist", END)
    compiled = graph.compile(checkpointer=saver)

    await compiled.ainvoke(
        {
            "messages": [
                HumanMessage(content="old", id="old"),
                HumanMessage(content="latest", id="latest"),
            ]
        },
        {"configurable": {"thread_id": "context-sidecar"}},
    )

    checkpoint = saver.get_tuple({"configurable": {"thread_id": "context-sidecar"}})
    assert checkpoint is not None
    stored = checkpoint.checkpoint["channel_values"]["context_compaction"]
    assert stored["source_message_count"] == 2
    assert stored["auto_compacted"] is True
    assert isinstance(stored["messages"][0], SystemMessage)


@pytest.mark.parametrize(
    "size, calls", [(7999, 0), (8000, 1), (8001, 1), (10000, 1), (10001, 1)]
)
async def test_watermarks_use_the_actual_post_layer_count(
    size: int, calls: int
) -> None:
    runnable = FakeStructuredRunnable(summary_result())
    messages = [AIMessage(content="x" * (size - 3)), HumanMessage(content="new")]
    result = await build_test_pipeline(runnable).acompact(
        make_request(messages, budget=ContextBudget(10_000, 0, 0))
    )

    assert result.original_tokens == size
    assert runnable.calls == calls
    assert result.auto_compacted_this_run is bool(calls)
    assert result.compacted_tokens <= (6_000 if calls else size)


async def test_deterministic_rewrite_below_trigger_skips_summary() -> None:
    runnable = FakeStructuredRunnable(summary_result())
    messages = [HumanMessage(content="new"), *exchange("done", "x" * 11_000)]
    result = await build_test_pipeline(
        runnable, layers=(ToolResultCompactor(max_characters=80),)
    ).acompact(make_request(messages, budget=ContextBudget(10_000, 0, 0)))

    assert result.original_tokens == 11_003
    assert result.compacted_tokens == 83
    assert result.applied_layers == ("historical_tool_results",)
    assert not result.auto_compacted
    assert runnable.calls == 0


class InvalidOrLongSummary:
    def __init__(self, responses: Sequence[object]) -> None:
        self.responses = iter(responses)
        self.prompts: list[str] = []

    async def ainvoke(
        self, messages: list[BaseMessage], *, max_repair_attempts: int
    ) -> object:
        assert max_repair_attempts == 0
        self.prompts.append(str(messages[0].content))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.parametrize(
    "first",
    [
        OutputParserException("invalid JSON"),
        summary_result().model_copy(update={"current_work": "x" * 11_000}),
    ],
)
async def test_summary_repairs_invalid_or_hard_oversize_once(first: object) -> None:
    runnable = InvalidOrLongSummary([first, summary_result()])
    messages = [AIMessage(content="x" * 10_001), HumanMessage(content=" user \n")]
    result = await build_test_pipeline(runnable).acompact(
        make_request(messages, budget=ContextBudget(10_000, 0, 0))
    )

    assert len(runnable.prompts) == 2
    assert runnable.prompts[1] != runnable.prompts[0]
    assert result.auto_compacted_this_run
    assert result.model_messages[-1] == messages[-1]
    assert result.compacted_tokens == sum(
        len(str(message.content)) for message in result.model_messages
    )
    assert result.compacted_tokens <= 6_000


@pytest.mark.parametrize("size", [9_000, 10_001])
async def test_summary_two_failures_preserve_candidate_and_obey_hard_limit(
    size: int,
) -> None:
    runnable = InvalidOrLongSummary([{"invalid": True}, {"invalid": True}])
    current = HumanMessage(content="new")
    messages = [AIMessage(content="x" * (size - 3)), current]
    pipeline = build_test_pipeline(runnable)
    request = make_request(messages, budget=ContextBudget(10_000, 0, 0))

    if size == 10_001:
        with pytest.raises(
            ContextCompactionError, match="invalid structured output"
        ) as caught:
            await pipeline.acompact(request)
        result = caught.value.partial_result
        assert result is not None and result.snapshot_status == "pending_auto_compact"
    else:
        result = await pipeline.acompact(request)
        assert result.snapshot_status == "complete"
        assert any(
            "soft_degraded" in warning and "invalid structured output" in warning
            for warning in result.warnings
        )
        assert not result.should_persist_snapshot
    assert len(runnable.prompts) == 2
    assert result.model_messages == messages
    assert not result.auto_compacted and not result.auto_compacted_this_run


async def test_summary_above_target_but_under_hard_limit_is_accepted_once() -> None:
    runnable = FakeStructuredRunnable(
        summary_result().model_copy(update={"current_work": "z" * 5_900})
    )
    messages = [AIMessage(content="x" * 7_500), HumanMessage(content="c" * 1_500)]
    result = await build_test_pipeline(runnable).acompact(
        make_request(messages, budget=ContextBudget(10_000, 0, 0))
    )

    assert 6_000 < result.compacted_tokens < result.original_tokens == 9_000
    assert result.auto_compacted_this_run
    assert any(warning.startswith("target_unmet") for warning in result.warnings)
    assert runnable.calls == 1


async def test_soft_failure_reuses_prior_summary_and_every_raw_suffix_message() -> None:
    raw = [
        HumanMessage(content="old", id="old"),
        AIMessage(content="previous answer", id="answer"),
        HumanMessage(content=" brand new \n", id="new"),
        *exchange("new-result", "x" * 4_000),
    ]
    summary = HumanMessage(content="[Historical context summary]\n" + "p" * 4_500)
    snapshot: ContextCompactionSnapshot = {
        "messages": [summary, raw[1]],
        "source_message_count": 2,
        "source_message_ids": ["old", "answer"],
        "status": "complete",
        "auto_compacted": True,
    }
    runnable = InvalidOrLongSummary([RuntimeError("unavailable")])
    request = _snapshot_request(
        _snapshot_state(raw, snapshot), budget=ContextBudget(10_000, 0, 0)
    )
    result = await build_test_pipeline(runnable).acompact(request)

    assert len(runnable.prompts) == 1
    assert result.auto_compacted and not result.auto_compacted_this_run
    assert result.model_messages == [*snapshot["messages"], *raw[2:]]
    assert any(warning.startswith("soft_degraded") for warning in result.warnings)


async def test_pending_below_trigger_remains_pending_on_failed_recovery() -> None:
    raw: list[BaseMessage] = [
        HumanMessage(content="old", id="old"),
        HumanMessage(content="new", id="new"),
    ]
    snapshot: ContextCompactionSnapshot = {
        "messages": raw,
        "source_message_count": 2,
        "source_message_ids": ["old", "new"],
        "status": "pending_auto_compact",
        "auto_compacted": False,
    }
    runnable = InvalidOrLongSummary([RuntimeError("unavailable")])
    with pytest.raises(
        ContextCompactionError, match="structured output failed"
    ) as caught:
        await build_test_pipeline(runnable).acompact(
            _snapshot_request(_snapshot_state(raw, snapshot))
        )
    assert len(runnable.prompts) == 1
    assert caught.value.partial_result is not None
    assert caught.value.partial_result.build_snapshot() == snapshot


@pytest.mark.parametrize("kind", ["json", "text", "invalid_json"])
@pytest.mark.parametrize("character_limit", [1, 2, 8, 80, 6000])
async def test_tool_result_omission_is_honest_stable_and_size_checked(
    kind: str,
    character_limit: int,
) -> None:
    raw_text = 'Quoted "text" and newline\n' * 500
    content = (
        json.dumps({"error": "known", "source_ref": "src", "data": raw_text})
        if kind == "json"
        else ("{invalid:" if kind == "invalid_json" else "") + raw_text
    )
    call, original = exchange("out", content)
    assert isinstance(original, ToolMessage)
    original.status = "error"
    original.artifact = {"raw": raw_text}
    layer = ToolResultCompactor(max_characters=character_limit)
    context = make_context([HumanMessage(content="query"), call, original])
    result = await layer.apply(context)
    rewritten = result.entries[-1].rendered
    assert isinstance(rewritten, ToolMessage)

    if character_limit <= 8:
        assert rewritten == original
        assert any(
            "tool_result_limit_too_small" in warning for warning in result.warnings
        )
    else:
        assert isinstance(rewritten.content, str)
        assert len(rewritten.content) <= character_limit
        assert rewritten.content != original.content
        if kind == "json":
            decoded = json.loads(rewritten.content)
            assert decoded["truncated"] is True
            assert decoded["tool_status"] == "error"
            assert decoded["source_ref"] == "src"
        else:
            assert rewritten.content.startswith("[Tool result truncated, status=error]")
    assert rewritten.status == "error" and rewritten.name == "lookup"
    assert rewritten.tool_call_id == original.tool_call_id
    assert rewritten.artifact == original.artifact
    assert original.content == content
    assert (await layer.apply(result)).entries == result.entries


@pytest.mark.parametrize("content", ["0", "false", "null", "{}", "[]"])
async def test_original_small_business_values_survive(content: str) -> None:
    messages = [HumanMessage(content="query"), *exchange("out", content)]
    result = await ToolResultCompactor(max_characters=8).apply(make_context(messages))
    assert not result.actions
    assert result.model_messages == messages


@pytest.mark.parametrize(
    "fault",
    [
        "missing_call_id",
        "duplicate_call",
        "orphan",
        "duplicate_result",
        "missing_result_id",
    ],
)
def test_invalid_tool_protocol_is_rejected_without_modification(fault: str) -> None:
    call, result = exchange("valid", "value")
    assert isinstance(call, AIMessage) and isinstance(result, ToolMessage)
    history: list[BaseMessage] = [call, result]
    if fault == "missing_call_id":
        call.tool_calls[0]["id"] = None
    elif fault == "duplicate_call":
        call.tool_calls.append(call.tool_calls[0])
    elif fault == "orphan":
        history.pop(0)
    elif fault == "duplicate_result":
        history.append(result)
    else:
        result.tool_call_id = ""
    with pytest.raises(ContextCompactionError, match="Invalid tool exchange"):
        message_groups(history)


async def test_parallel_exchange_is_summarized_as_a_complete_group() -> None:
    parallel: list[BaseMessage] = [
        AIMessage(
            content="",
            tool_calls=[
                {"id": f"call-{i}", "name": "lookup", "args": {}} for i in range(3)
            ],
        ),
        *(
            ToolMessage(content="x" * 3_400, tool_call_id=f"call-{i}", name="lookup")
            for i in range(3)
        ),
    ]
    user = HumanMessage(
        content=" 只考虑上海，税前月薪不低于 20k，不得编造经历，先比较岗位，不要替我投递\n `x = 'a&b'` \n"
    )
    system = SystemMessage(content="Retain this system instruction verbatim.\n")
    runnable = FakeStructuredRunnable(summary_result())
    result = await build_test_pipeline(runnable).acompact(
        make_request([system, user, *parallel], budget=ContextBudget(10_000, 0, 0))
    )
    assert result.auto_compacted_this_run
    assert result.model_messages[0] == system
    assert result.model_messages[-1] == user
    assert message_groups(result.model_messages) == [
        range(0, 1),
        range(1, 2),
        range(2, 3),
    ]
    request = cast(list[BaseMessage], runnable.inputs[0])
    history = json.loads(str(request[1].content))
    assert [item["id"] for item in history[0]["tool_calls"]] == [
        "call-0",
        "call-1",
        "call-2",
    ]
    assert [item["tool_call_id"] for item in history[1:]] == [
        "call-0",
        "call-1",
        "call-2",
    ]
    assert all(item["status"] == "success" for item in history[1:])


async def test_recent_four_turns_yield_older_complete_exchanges_first() -> None:
    user_text = "  只考虑上海，税前月薪不低于 20k。\n禁止编造经历，先比较岗位，不要替我投递。\n`x = 'A&B'`  "
    messages: list[BaseMessage] = []
    for index in range(4):
        messages.append(
            HumanMessage(content=user_text if index == 3 else f"Request {index}")
        )
        messages.extend(exchange(f"turn-{index}", "role description " * 200))
    before = list(messages)
    runnable = FakeStructuredRunnable(summary_result())
    result = await build_test_pipeline(runnable).acompact(
        make_request(messages, budget=ContextBudget(10_000, 0, 0))
    )
    assert result.original_tokens > 10_000 and result.compacted_tokens <= 6_000
    assert result.auto_compacted_this_run and runnable.calls == 1
    assert [
        message.tool_call_id
        for message in result.model_messages
        if isinstance(message, ToolMessage)
    ] == ["turn-3"]
    assert any(
        isinstance(message, HumanMessage) and message.content == user_text
        for message in result.model_messages
    )
    message_groups(result.model_messages)
    assert messages == before


@pytest.mark.parametrize("size", [9_000, 10_001])
async def test_insufficient_summary_allowance_does_not_override_provider_or_lose_user(
    size: int,
) -> None:
    previous, current = (
        AIMessage(content="x" * (size - 5_900)),
        HumanMessage(content="c" * 5_900),
    )
    runnable = FakeStructuredRunnable(summary_result())
    compact_request = make_request(
        [previous, current], budget=ContextBudget(10_000, 0, 0)
    )
    pipeline = build_test_pipeline(runnable)
    if size > 10_000:
        with pytest.raises(ContextCompactionError, match="too little room") as caught:
            await pipeline.acompact(compact_request)
        result = caught.value.partial_result
        assert result is not None and result.snapshot_status == "pending_auto_compact"
    else:
        result = await pipeline.acompact(compact_request)
        assert result.snapshot_status == "complete"
        assert any(
            "soft_degraded" in warning and "too little room" in warning
            for warning in result.warnings
        )
    assert result.model_messages == [previous, current]
    assert not result.auto_compacted
    assert runnable.calls == 0


async def test_existing_accepted_summary_can_resolve_pending_when_no_history_remains() -> (
    None
):
    raw = [
        HumanMessage(content="earlier", id="earlier"),
        HumanMessage(content="current", id="current"),
    ]
    prior = HumanMessage(
        content="[Historical context summary]\nPrior history",
        additional_kwargs={"_offerpilot_context_compaction": "summary"},
    )
    snapshot: ContextCompactionSnapshot = {
        "messages": [prior, raw[-1]],
        "source_message_count": 2,
        "source_message_ids": ["earlier", "current"],
        "status": "pending_auto_compact",
        "auto_compacted": True,
    }
    runnable = FakeStructuredRunnable(summary_result())
    result = await build_test_pipeline(runnable).acompact(
        _snapshot_request(_snapshot_state(raw, snapshot))
    )
    assert result.snapshot_status == "complete"
    assert result.auto_compacted and not result.auto_compacted_this_run
    assert result.model_messages == snapshot["messages"]
    assert runnable.calls == 0


async def test_legacy_sidecar_placeholders_are_rebuilt_from_the_raw_tool_result() -> (
    None
):
    user = HumanMessage(content="latest", id="user")
    call, original = exchange("lookup", "A verified result with supporting evidence.")
    call.id = "assistant"
    original.id = "result"
    assert isinstance(original, ToolMessage)
    prior = original.model_copy(update={"content": "0"})
    raw = [user, call, original]
    snapshot: ContextCompactionSnapshot = {
        "messages": [user, call, prior],
        "source_message_count": 3,
        "source_message_ids": ["user", "assistant", "result"],
        "status": "complete",
        "auto_compacted": True,
    }
    runnable = FakeStructuredRunnable(summary_result())
    result = await build_test_pipeline(runnable).acompact(
        _snapshot_request(_snapshot_state(raw, snapshot))
    )
    assert result.model_messages == raw
    assert result.should_persist_snapshot and result.auto_compacted
    assert not result.auto_compacted_this_run and runnable.calls == 0
