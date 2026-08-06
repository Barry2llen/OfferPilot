from __future__ import annotations

from collections.abc import Sequence

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from agent.base import BaseAgentState, GraphRuntime
from agent.agents.supervisor.agent import SupervisorAgent
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
from agent.graphs.model_call import ModelCallGraph
from agent.compaction.protection import protect_entries
from agent.compaction.token_counter import ApproximateTokenCounter
from schemas.config import Config, ContextCompactionConfig
from schemas.model_provider import ModelProvider
from schemas.model_selection import ModelSelection


class CharacterTokenCounter:
    async def acount(
        self,
        *,
        system_prompts: Sequence[SystemMessage],
        messages: Sequence[object],
        tools: Sequence[object],
    ) -> int:
        del tools
        return sum(
            len(str(getattr(message, "content", "")))
            for message in (*system_prompts, *messages)
        )


class SummaryMergeTokenCounter(CharacterTokenCounter):
    def __init__(self) -> None:
        self.calls = 0

    async def acount(
        self,
        *,
        system_prompts: Sequence[SystemMessage],
        messages: Sequence[object],
        tools: Sequence[object],
    ) -> int:
        del system_prompts, messages, tools
        self.calls += 1
        return 20 if self.calls == 1 else 5


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
    messages: list[object],
    *,
    model: ModelSelection | None = None,
) -> GraphRuntime:
    return GraphRuntime(
        state={
            "messages": messages,
            "model": model or make_selection(),
        },
        additional_args=(),
        additional_keywords={},
    )


def make_request(
    messages: list[object],
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
    messages: list[object],
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


def exchange(call_id: str, result: str, *, return_direct: bool = False) -> list[object]:
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
    ).acompact(make_request(messages, budget=ContextBudget(
        max_context_tokens=1_000,
        reserved_output_tokens=100,
        safety_margin_tokens=0,
    )))

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


def test_protection_preserves_latest_recent_and_incomplete_tool_context() -> None:
    messages = [
        HumanMessage(content="old one"),
        *exchange("old-call", "old result"),
        HumanMessage(content="recent"),
        AIMessage(
            content="",
            tool_calls=[{"name": "lookup", "args": {}, "id": "incomplete"}],
        ),
    ]
    entries = make_context(messages, keep_recent_turns=1).entries

    assert [entry.protected for entry in entries] == [False, False, False, True, True]


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
    assert entries[4].protected is True
    assert entries[5].protected is True


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
    assert compacted_tool.additional_kwargs == {"return_direct": False}
    assert messages[2].content == original


async def test_attachment_compactor_rewrites_old_attachment_and_preserves_metadata() -> None:
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
    assert "file-1" in rewritten.content
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
    def __init__(self, runnable: FakeStructuredRunnable) -> None:
        self.runnable = runnable
        self.selections: list[ModelSelection] = []
        self.schemas: list[type[ContextCompactionSummary]] = []

    def __call__(
        self,
        selection: ModelSelection,
        schema: type[ContextCompactionSummary],
    ) -> FakeStructuredRunnable:
        self.selections.append(selection)
        self.schemas.append(schema)
        return self.runnable


def summary_result() -> ContextCompactionSummary:
    return ContextCompactionSummary(
        primary_request_and_intent="Finish the application",
        key_technical_concepts=["structured compaction"],
        files_and_code_sections=["backend/agent/compaction/layers/auto.py"],
        errors_and_fixes=["The old lookup succeeded; no fix was needed."],
        problem_solving=["Use structured compaction"],
        all_user_messages=["old history"],
        pending_tasks=["Run verification"],
        current_work="Implementing the application",
        optional_next_step="Run verification",
    )


async def test_auto_compact_summarizes_unprotected_history_with_structured_model() -> None:
    runnable = FakeStructuredRunnable(summary_result())
    loader = FakeStructuredModelLoader(runnable)
    messages = [
        HumanMessage(content="old history"),
        AIMessage(content="old answer"),
        HumanMessage(content="latest request"),
    ]
    context = make_context(messages, keep_recent_turns=1, current_tokens=100_000)
    context = context.with_current_tokens(100_000)
    policy = DefaultContextBudgetPolicy(ContextCompactionConfig())

    result = await AutoCompactLayer(
        model_resolver=StaticResolver(make_selection(model_name="compact-model")),
        budget_policy=policy,
        token_counter=CharacterTokenCounter(),
        structured_model_loader=loader,
    ).apply(context)

    assert runnable.calls == 1
    assert runnable.kwargs == [{"max_repair_attempts": 0}]
    assert loader.selections == [make_selection(model_name="compact-model")]
    assert loader.schemas == [ContextCompactionSummary]
    assert len(result.entries) == 2
    assert isinstance(result.entries[0].rendered, SystemMessage)
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
    assert prompt.startswith("WARNING: DO NOT CALL TOOLS")
    assert prompt.endswith(
        "WARNING: DO NOT CALL TOOLS. Return the structured context summary only."
    )
    assert "6. All User Messages" in prompt
    assert "preserving its original text and order" in prompt
    assert "untrusted historical data" in prompt
    assert "tool_call_id" in prompt
    assert summary_input[1:] == messages[:2]


async def test_auto_compact_requires_unprotected_history() -> None:
    messages = [HumanMessage(content="only current")]
    context = make_context(messages, keep_recent_turns=1, current_tokens=100_000)

    with pytest.raises(ContextCompactionError, match="no unprotected"):
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
    loader = FakeStructuredModelLoader(runnable)  # type: ignore[arg-type]
    context = make_context(
        [HumanMessage(content="old"), HumanMessage(content="latest")],
        keep_recent_turns=1,
        current_tokens=100_000,
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
    assert not hasattr(settings, "trigger_ratio")
    assert not hasattr(settings, "target_ratio")


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
    assert "compact" not in SupervisorAgent(config=disabled_config)._model_call_node.nodes


def test_context_summary_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        ContextCompactionSummary.model_validate(
            {
                **summary_result().model_dump(),
                "unexpected": "must be rejected",
            }
        )


def test_context_compaction_summary_requires_all_sections_and_string_lists() -> None:
    missing_field = summary_result().model_dump()
    del missing_field["current_work"]

    with pytest.raises(ValueError):
        ContextCompactionSummary.model_validate(missing_field)

    invalid_list_item = summary_result().model_dump()
    invalid_list_item["key_technical_concepts"] = [123]

    with pytest.raises(ValueError):
        ContextCompactionSummary.model_validate(invalid_list_item)


async def test_auto_compact_blocks_when_summary_model_has_insufficient_capacity() -> None:
    runnable = FakeStructuredRunnable(summary_result())
    loader = FakeStructuredModelLoader(runnable)
    context = make_context(
        [HumanMessage(content="historical " * 50), HumanMessage(content="latest")],
        keep_recent_turns=1,
        current_tokens=200,
        budget=ContextBudget(
            max_context_tokens=100,
            reserved_output_tokens=10,
            safety_margin_tokens=0,
        ),
    )

    with pytest.raises(ContextCompactionError, match="summary input"):
        await AutoCompactLayer(
            budget_policy=DefaultContextBudgetPolicy(
                ContextCompactionConfig(
                    default_max_context_tokens=100,
                    reserved_output_tokens=10,
                    safety_margin_tokens=0,
                )
            ),
            token_counter=CharacterTokenCounter(),
            structured_model_loader=loader,
        ).apply(context)

    assert runnable.calls == 0


async def test_token_counter_ignores_historical_reasoning_metadata() -> None:
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

    assert with_reasoning == without_reasoning


def _snapshot_state(
    messages: list[object],
    snapshot: dict[str, object],
) -> GraphRuntime:
    return GraphRuntime(
        state={
            "messages": messages,
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
    snapshot = {
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
    assert runtime.state["messages"] == original_messages
    assert result.source_message_count == len(raw_messages)
    assert result.source_message_ids == ("human-old", "ai-old", "human-new")


async def test_pipeline_does_not_repeat_summary_without_new_raw_history() -> None:
    raw_messages = [
        HumanMessage(content="old user", id="human-old"),
        AIMessage(content="old answer", id="ai-old"),
    ]
    summary = SystemMessage(content="[Historical context summary]\nold context")
    snapshot = {
        "messages": [summary, raw_messages[1]],
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
    assert [message for message in result.model_messages if isinstance(message, SystemMessage)] == [summary]
    assert result.auto_compacted is True
    assert result.auto_compacted_this_run is False


async def test_pipeline_merges_existing_summary_with_new_historical_messages() -> None:
    raw_messages = [
        HumanMessage(content="old user", id="human-old"),
        AIMessage(content="old answer", id="ai-old"),
        HumanMessage(content="new request", id="human-new"),
    ]
    old_summary = SystemMessage(content="[Historical context summary]\nold context")
    snapshot = {
        "messages": [old_summary, raw_messages[1]],
        "source_message_count": 2,
        "source_message_ids": ["human-old", "ai-old"],
        "status": "complete",
        "auto_compacted": True,
    }
    runnable = FakeStructuredRunnable(summary_result())
    loader = FakeStructuredModelLoader(runnable)

    result = await PipelineCompactor(
        token_counter=SummaryMergeTokenCounter(),
        keep_recent_turns=1,
        layers=(
            AutoCompactLayer(
                model_resolver=StaticResolver(make_selection(model_name="compact")),
                budget_policy=DefaultContextBudgetPolicy(ContextCompactionConfig()),
                token_counter=SummaryMergeTokenCounter(),
                structured_model_loader=loader,
            ),
        ),
    ).acompact(
        _snapshot_request(
            _snapshot_state(raw_messages, snapshot),
            budget=ContextBudget(
                max_context_tokens=10,
                reserved_output_tokens=0,
                safety_margin_tokens=0,
            ),
        )
    )

    assert runnable.calls == 1
    assert result.auto_compacted_this_run is True
    assert sum(
        isinstance(message, SystemMessage)
        and message.content.startswith("[Historical context summary]")
        for message in result.model_messages
    ) == 1
    summary_input = runnable.inputs[0]
    assert isinstance(summary_input, list)
    assert summary_input[1] == old_summary
    assert summary_input[2] == raw_messages[1]
    assert result.model_messages[-1] == raw_messages[-1]


async def test_pending_snapshot_retries_summary_even_below_threshold() -> None:
    raw_messages = [
        HumanMessage(content="old user", id="human-old"),
        HumanMessage(content="latest", id="human-latest"),
    ]
    snapshot = {
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
    ).acompact(
        _snapshot_request(_snapshot_state(raw_messages, snapshot))
    )

    assert runnable.calls == 1
    assert result.snapshot_status == "complete"
    assert result.auto_compacted is True


async def test_context_compaction_snapshot_round_trips_through_langgraph_checkpoint() -> None:
    summary = SystemMessage(content="[Historical context summary]\ncheckpoint")
    snapshot = {
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
        {"messages": [HumanMessage(content="old", id="old"), HumanMessage(content="latest", id="latest")]},
        {"configurable": {"thread_id": "context-sidecar"}},
    )

    checkpoint = saver.get_tuple({"configurable": {"thread_id": "context-sidecar"}})
    assert checkpoint is not None
    stored = checkpoint.checkpoint["channel_values"]["context_compaction"]
    assert stored["source_message_count"] == 2
    assert stored["auto_compacted"] is True
    assert isinstance(stored["messages"][0], SystemMessage)
