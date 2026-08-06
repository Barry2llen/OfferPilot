from __future__ import annotations

from collections.abc import Sequence

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from agent.base import GraphRuntime
from agent.compaction import (
    AutoCompactLayer,
    CompactedMessage,
    CompactionContext,
    CompactionRequest,
    ContextBudget,
    ContextCompactionError,
    ContextSummary,
    DefaultContextBudgetPolicy,
    HistoricalAttachmentCompactor,
    MessageRef,
    PipelineCompactor,
    ToolResultCompactor,
    build_supervisor_compactor,
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
            trigger_input_tokens=100,
            target_input_tokens=50,
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
        trigger_input_tokens=500,
        target_input_tokens=100,
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
    def __init__(self, result: ContextSummary) -> None:
        self.result = result
        self.inputs: list[object] = []
        self.calls = 0

    async def ainvoke(self, messages: object) -> ContextSummary:
        self.calls += 1
        self.inputs.append(messages)
        return self.result


class FakeSummaryModel:
    def __init__(self, runnable: FakeStructuredRunnable) -> None:
        self.runnable = runnable
        self.schemas: list[type[BaseModel]] = []

    def with_structured_output(self, schema: type[BaseModel]) -> FakeStructuredRunnable:
        self.schemas.append(schema)
        return self.runnable


def summary_result() -> ContextSummary:
    return ContextSummary(
        goal="Finish the application",
        constraints=["Keep the existing API"],
        facts=["The old history is complete"],
        decisions=["Use structured compaction"],
        pending=["Run verification"],
        tool_results=[
            {
                "tool_call_id": "old-call",
                "name": "lookup",
                "summary": "The old lookup succeeded",
            }
        ],
        attachment_refs=[],
    )


async def test_auto_compact_summarizes_unprotected_history_with_structured_model() -> None:
    runnable = FakeStructuredRunnable(summary_result())
    model = FakeSummaryModel(runnable)
    messages = [
        HumanMessage(content="old history"),
        AIMessage(content="old answer"),
        HumanMessage(content="latest request"),
    ]
    context = make_context(messages, keep_recent_turns=1, current_tokens=200)
    context = context.with_current_tokens(200)
    policy = DefaultContextBudgetPolicy(ContextCompactionConfig())

    result = await AutoCompactLayer(
        model_resolver=StaticResolver(make_selection(model_name="compact-model")),
        budget_policy=policy,
        token_counter=CharacterTokenCounter(),
        model_loader=lambda selection: model,
    ).apply(context)

    assert runnable.calls == 1
    assert model.schemas == [ContextSummary]
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
    assert summary_input[0].content.startswith("You are OfferPilot")
    assert summary_input[1:] == messages[:2]


async def test_auto_compact_requires_unprotected_history() -> None:
    messages = [HumanMessage(content="only current")]
    context = make_context(messages, keep_recent_turns=1, current_tokens=200)

    with pytest.raises(ContextCompactionError, match="no unprotected"):
        await AutoCompactLayer(
            budget_policy=DefaultContextBudgetPolicy(ContextCompactionConfig()),
            token_counter=CharacterTokenCounter(),
        ).apply(context)


async def test_auto_compact_does_not_retry_structured_output_failure() -> None:
    class FailingRunnable:
        calls = 0

        async def ainvoke(self, messages: object) -> object:
            del messages
            self.calls += 1
            raise RuntimeError("provider failed")

    runnable = FailingRunnable()
    model = FakeSummaryModel(runnable)  # type: ignore[arg-type]
    context = make_context(
        [HumanMessage(content="old"), HumanMessage(content="latest")],
        keep_recent_turns=1,
        current_tokens=200,
    )

    with pytest.raises(ContextCompactionError, match="structured output failed"):
        await AutoCompactLayer(
            budget_policy=DefaultContextBudgetPolicy(ContextCompactionConfig()),
            token_counter=CharacterTokenCounter(),
            model_loader=lambda selection: model,
        ).apply(context)

    assert runnable.calls == 1


def test_context_compaction_config_no_longer_contains_reasoning_setting() -> None:
    settings = ContextCompactionConfig()

    assert not hasattr(settings, "keep_recent_reasoning_messages")
    assert settings.keep_recent_turns == 4


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


def test_context_summary_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        ContextSummary.model_validate(
            {
                **summary_result().model_dump(),
                "unexpected": "must be rejected",
            }
        )


async def test_auto_compact_blocks_when_summary_model_has_insufficient_capacity() -> None:
    runnable = FakeStructuredRunnable(summary_result())
    model = FakeSummaryModel(runnable)
    context = make_context(
        [HumanMessage(content="historical " * 50), HumanMessage(content="latest")],
        keep_recent_turns=1,
        current_tokens=200,
        budget=ContextBudget(
            max_context_tokens=100,
            reserved_output_tokens=10,
            safety_margin_tokens=0,
            trigger_input_tokens=70,
            target_input_tokens=50,
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
            model_loader=lambda selection: model,
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
