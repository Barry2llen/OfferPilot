from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from math import ceil

import pytest
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool
from pydantic import ValidationError

from agent.base import GraphRuntime
from agent.compaction import (
    ApproximateTokenCounter,
    CompactedMessage,
    CompactionContext,
    CompactionRequest,
    CompactionResult,
    ContextBudget,
    ContextGrouper,
    DefaultContextBudgetPolicy,
    IdentityCompactor,
    MessageRef,
    PipelineCompactor,
    SingleMessageUnit,
    ToolExchangeUnit,
)
from agent.compaction.layers import (
    HardTrimLayer,
    HistoricalAttachmentCompactor,
    HistoricalReasoningPruner,
    ToolResultCompactor,
)
from agent.graphs.model_call import ModelCallGraph
from schemas.config import Config, ContextCompactionConfig
from schemas.model_provider import ModelProvider
from schemas.model_selection import ModelSelection


MODEL_SELECTION = ModelSelection(
    provider=ModelProvider(provider="OpenAI", name="test-provider"),
    model_name="test-model",
)


def make_budget(*, trigger: int = 100, target: int = 50) -> ContextBudget:
    return ContextBudget(
        max_context_tokens=1_000,
        reserved_output_tokens=0,
        safety_margin_tokens=0,
        trigger_input_tokens=trigger,
        target_input_tokens=target,
    )


def make_request(
    messages: list[BaseMessage],
    *,
    budget: ContextBudget | None = None,
    system_prompts: tuple[BaseMessage, ...] = (),
    tools: tuple = (),
) -> CompactionRequest:
    return CompactionRequest(
        runtime=GraphRuntime(
            state={"messages": messages},
            additional_args=(),
            additional_keywords={},
        ),
        messages=tuple(messages),
        system_prompts=system_prompts,
        tools=tools,
        model_selection=MODEL_SELECTION,
        budget=budget or make_budget(),
    )


def make_entries(messages: list[BaseMessage]) -> tuple[CompactedMessage, ...]:
    return tuple(
        CompactedMessage(
            rendered=message,
            sources=(
                MessageRef(
                    index=index,
                    message_id=message.id if isinstance(message.id, str) else None,
                ),
            ),
            kind="identity",
            layer="identity",
        )
        for index, message in enumerate(messages)
    )


def make_context(
    messages: list[BaseMessage],
    *,
    keep_recent_turns: int = 1,
    budget: ContextBudget | None = None,
) -> CompactionContext:
    request = make_request(messages, budget=budget)
    return CompactionContext(
        request=request,
        units=ContextGrouper(keep_recent_turns=keep_recent_turns).group(
            make_entries(messages)
        ),
    )


class CharacterTokenCounter:
    def __init__(self) -> None:
        self.calls = 0

    async def acount(self, *, system_prompts, messages, tools) -> int:
        self.calls += 1
        total = sum(
            len(str(message.content))
            for message in [*system_prompts, *messages]
        )
        return ceil(total / 4) + len(system_prompts) + len(tools)


class SequenceTokenCounter:
    def __init__(self, values: list[int]) -> None:
        self.values = values
        self.calls = 0

    async def acount(self, *, system_prompts, messages, tools) -> int:
        value = self.values[min(self.calls, len(self.values) - 1)]
        self.calls += 1
        return value


@dataclass
class RecordingLayer:
    name: str
    calls: int = 0

    async def apply(self, context: CompactionContext) -> CompactionContext:
        self.calls += 1
        return context


def test_compacted_message_is_a_trace_record_not_a_langchain_message() -> None:
    assert not issubclass(CompactedMessage, BaseMessage)


async def test_identity_compactor_preserves_messages_and_returns_standard_messages() -> None:
    messages = [
        HumanMessage(content="hello", id="h1"),
        AIMessage(content="answer", id="a1"),
    ]
    result = await IdentityCompactor(token_counter=CharacterTokenCounter()).acompact(
        make_request(messages)
    )

    assert result.model_messages == messages
    assert result.entries[0].kind == "identity"
    assert [action.kind for action in result.actions] == ["keep", "keep"]
    assert all(isinstance(message, BaseMessage) for message in result.model_messages)
    assert not any(isinstance(message, CompactedMessage) for message in result.model_messages)


async def test_pipeline_skips_layers_below_trigger() -> None:
    counter = SequenceTokenCounter([20])
    layer = RecordingLayer("should_not_run")
    pipeline = PipelineCompactor(
        token_counter=counter,
        grouper=ContextGrouper(),
        layers=[layer],
    )

    result = await pipeline.acompact(
        make_request(
            [HumanMessage(content="hello")],
            budget=make_budget(trigger=30, target=10),
        )
    )

    assert layer.calls == 0
    assert result.applied_layers == ()
    assert result.compacted_tokens == 20


async def test_pipeline_stops_after_target_and_recounts_each_layer() -> None:
    counter = SequenceTokenCounter([120, 40])
    first = RecordingLayer("first")
    second = RecordingLayer("second")
    pipeline = PipelineCompactor(
        token_counter=counter,
        grouper=ContextGrouper(),
        layers=[first, second],
    )

    result = await pipeline.acompact(
        make_request(
            [HumanMessage(content="hello")],
            budget=make_budget(trigger=100, target=50),
        )
    )

    assert first.calls == 1
    assert second.calls == 0
    assert counter.calls == 2
    assert result.applied_layers == ("first",)
    assert result.reached_target is True


def test_context_budget_policy_resolves_model_specific_window() -> None:
    config = ContextCompactionConfig(
        default_max_context_tokens=1_000,
        reserved_output_tokens=100,
        safety_margin_tokens=100,
        trigger_ratio=0.8,
        target_ratio=0.5,
        model_context_windows={"OpenAI:test-model": 2_000, "test-model": 1_500},
    )
    budget = DefaultContextBudgetPolicy(config).resolve(MODEL_SELECTION)

    assert budget.max_context_tokens == 2_000
    assert budget.trigger_input_tokens == 1_440
    assert budget.target_input_tokens == 900


def test_context_compaction_config_validates_ratios_and_windows() -> None:
    with pytest.raises(ValidationError):
        ContextCompactionConfig(target_ratio=0.9, trigger_ratio=0.8)
    with pytest.raises(ValidationError):
        ContextCompactionConfig(model_context_windows={"test-model": 0})
    with pytest.raises(ValidationError):
        ContextCompactionConfig(tool_result_max_characters=0)


@tool
def compactable_tool(query: str) -> str:
    """Search a source and return a result."""
    return query


async def test_token_counter_includes_system_prompts_and_tool_schema() -> None:
    counter = ApproximateTokenCounter()
    without_system_or_tool = await counter.acount(
        system_prompts=(),
        messages=[HumanMessage(content="hello")],
        tools=(),
    )
    with_system_and_tool = await counter.acount(
        system_prompts=(SystemMessage(content="system instructions"),),
        messages=[HumanMessage(content="hello")],
        tools=(compactable_tool,),
    )

    assert with_system_and_tool > without_system_or_tool


def test_context_grouper_keeps_multi_tool_exchange_atomic() -> None:
    messages = [
        HumanMessage(content="run tools", id="h1"),
        AIMessage(
            content="",
            id="a1",
            tool_calls=[
                {"name": "one", "args": {}, "id": "call-a"},
                {"name": "two", "args": {}, "id": "call-b"},
            ],
        ),
        ToolMessage(content="one result", tool_call_id="call-a", name="one"),
        ToolMessage(content="two result", tool_call_id="call-b", name="two"),
        HumanMessage(content="done", id="h2"),
    ]
    units = ContextGrouper(keep_recent_turns=0).group(make_entries(messages))

    exchange = next(unit for unit in units if isinstance(unit, ToolExchangeUnit))
    assert exchange.tool_call_ids == ("call-a", "call-b")
    assert exchange.complete is True
    assert len(exchange.entries) == 3
    assert exchange.protected is True


def test_context_grouper_protects_incomplete_and_orphan_tool_messages() -> None:
    messages = [
        HumanMessage(content="run", id="h1"),
        AIMessage(
            content="",
            tool_calls=[{"name": "one", "args": {}, "id": "call-a"}],
        ),
        ToolMessage(content="unexpected", tool_call_id="call-other", name="other"),
    ]
    units = ContextGrouper(keep_recent_turns=0).group(make_entries(messages))

    assert isinstance(units[1], ToolExchangeUnit)
    assert units[1].complete is False
    assert units[1].protected is True
    assert isinstance(units[2], SingleMessageUnit)
    assert units[2].protected is True


async def test_reasoning_pruner_rewrites_old_reasoning_without_mutating_source() -> None:
    old = AIMessage(
        content="old answer",
        id="a-old",
        tool_calls=[{"name": "keep", "args": {}, "id": "call-old"}],
        additional_kwargs={
            "reasoning_content": "old reasoning",
            "reasoning_duration_ms": 12,
        },
    )
    recent = AIMessage(
        content="recent answer",
        id="a-recent",
        additional_kwargs={
            "reasoning_content": "recent reasoning",
            "reasoning_duration_ms": 8,
        },
    )
    messages = [
        HumanMessage(content="old user"),
        old,
        ToolMessage(content="result", tool_call_id="call-old", name="keep"),
        HumanMessage(content="recent user"),
        recent,
    ]
    before = copy.deepcopy(old.model_dump(mode="python"))
    context = make_context(messages, keep_recent_turns=1)

    result = await HistoricalReasoningPruner(keep_recent_reasoning_messages=1).apply(context)
    rendered = result.model_messages

    assert rendered[1].additional_kwargs == {}
    assert rendered[1].content == old.content
    assert rendered[1].tool_calls == old.tool_calls
    assert rendered[1].id == old.id
    assert rendered[-1].additional_kwargs["reasoning_content"] == "recent reasoning"
    assert old.model_dump(mode="python") == before
    assert any(action.kind == "rewrite" for action in result.actions)


async def test_reasoning_pruner_does_not_create_action_without_reasoning() -> None:
    message = AIMessage(content="plain")
    context = make_context([HumanMessage(content="user"), message], keep_recent_turns=0)

    result = await HistoricalReasoningPruner(keep_recent_reasoning_messages=0).apply(context)

    assert result.actions == ()
    assert result.model_messages[-1] is message


def _tool_exchange_messages() -> list[BaseMessage]:
    return [
        HumanMessage(content="old request"),
        AIMessage(
            content="",
            tool_calls=[{"name": "search", "args": {}, "id": "old-call"}],
        ),
        ToolMessage(
            content=json.dumps(
                {
                    "query": "important query",
                    "url": "https://example.com",
                    "data": "x" * 4_000,
                    "items": list(range(100)),
                }
            ),
            tool_call_id="old-call",
            name="search",
            status="success",
            additional_kwargs={"trace": "keep"},
        ),
        HumanMessage(content="current request"),
        AIMessage(
            content="",
            tool_calls=[{"name": "search", "args": {}, "id": "current-call"}],
        ),
        ToolMessage(content="current result", tool_call_id="current-call", name="search"),
        HumanMessage(content="latest request"),
    ]


async def test_tool_result_compactor_keeps_exchange_pairing_and_valid_json() -> None:
    messages = _tool_exchange_messages()
    original_tool = messages[2]
    assert isinstance(original_tool, ToolMessage)
    before = copy.deepcopy(original_tool.model_dump(mode="python"))
    context = make_context(messages, keep_recent_turns=1)

    result = await ToolResultCompactor(max_characters=200).apply(context)
    old_tool = result.model_messages[2]
    current_ai = result.model_messages[4]
    current_tool = result.model_messages[5]

    assert isinstance(old_tool, ToolMessage)
    assert len(old_tool.content) < len(original_tool.content)
    assert json.loads(old_tool.content)["query"] == "important query"
    assert old_tool.tool_call_id == "old-call"
    assert old_tool.name == "search"
    assert old_tool.status == "success"
    assert old_tool.additional_kwargs == {"trace": "keep"}
    assert isinstance(current_ai, AIMessage)
    assert isinstance(current_tool, ToolMessage)
    assert current_tool.content == "current result"
    assert original_tool.model_dump(mode="python") == before


async def test_tool_result_compactor_text_result_is_shorter_and_small_result_is_kept() -> None:
    messages = [
        HumanMessage(content="old"),
        AIMessage(content="", tool_calls=[{"name": "search", "args": {}, "id": "c1"}]),
        ToolMessage(
            content="start " + "x" * 500 + " error at the end",
            tool_call_id="c1",
            name="search",
        ),
        HumanMessage(content="middle"),
        AIMessage(content="", tool_calls=[{"name": "search", "args": {}, "id": "c2"}]),
        ToolMessage(content="current result", tool_call_id="c2", name="search"),
        HumanMessage(content="latest"),
    ]
    context = make_context(messages, keep_recent_turns=1)
    result = await ToolResultCompactor(max_characters=100).apply(context)

    compacted = result.model_messages[2]
    assert isinstance(compacted, ToolMessage)
    assert len(compacted.content) < len(messages[2].content)
    assert "历史工具结果已压缩" in compacted.content
    assert "error at the end" in compacted.content

    small_messages = [
        HumanMessage(content="old"),
        AIMessage(content="", tool_calls=[{"name": "search", "args": {}, "id": "c2"}]),
        ToolMessage(content="small", tool_call_id="c2", name="search"),
        HumanMessage(content="latest"),
    ]
    small_result = await ToolResultCompactor(max_characters=100).apply(
        make_context(small_messages, keep_recent_turns=1)
    )
    assert small_result.actions == ()


async def test_historical_attachment_compactor_keeps_reference_metadata_and_latest_message() -> None:
    old_attachment = HumanMessage(
        content=[
            {"type": "text", "text": "old visible request"},
            {"type": "text", "text": "full attachment body"},
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,AAAA"},
            },
        ],
        additional_kwargs={
            "display_content": "old visible request",
            "attachments": [
                {
                    "file_id": "A1B2C3",
                    "original_filename": "resume.pdf",
                    "injection_mode": "text",
                }
            ],
            "requires_image_input": False,
        },
    )
    latest_attachment = HumanMessage(
        content="latest",
        additional_kwargs={
            "display_content": "latest",
            "attachments": [
                {
                    "file_id": "D4E5F6",
                    "original_filename": "job.png",
                    "injection_mode": "ocr_text",
                }
            ],
        },
    )
    before = copy.deepcopy(old_attachment.model_dump(mode="python"))
    context = make_context(
        [old_attachment, AIMessage(content="old answer"), latest_attachment],
        keep_recent_turns=1,
    )

    result = await HistoricalAttachmentCompactor().apply(context)
    old_rendered = result.model_messages[0]
    latest_rendered = result.model_messages[-1]

    assert isinstance(old_rendered, HumanMessage)
    assert "历史附件上下文已压缩" in old_rendered.content
    assert "A1B2C3 (resume.pdf, mode=text)" in old_rendered.content
    assert old_rendered.additional_kwargs == old_attachment.additional_kwargs
    assert old_attachment.model_dump(mode="python") == before
    assert latest_rendered.content == "latest"
    assert latest_rendered.additional_kwargs == latest_attachment.additional_kwargs


async def test_hard_trim_drops_oldest_units_without_splitting_tool_exchange() -> None:
    messages = [
        HumanMessage(content="old user " + "x" * 300),
        AIMessage(content="old answer " + "x" * 300),
        HumanMessage(content="tool user"),
        AIMessage(
            content="",
            tool_calls=[{"name": "search", "args": {}, "id": "call-current"}],
        ),
        ToolMessage(
            content="tool result " + "x" * 300,
            tool_call_id="call-current",
            name="search",
        ),
        HumanMessage(content="latest user"),
    ]
    context = make_context(
        messages,
        keep_recent_turns=1,
        budget=make_budget(trigger=1_000, target=100),
    )
    result = await HardTrimLayer(token_counter=CharacterTokenCounter()).apply(context)
    rendered = result.model_messages

    assert rendered[0].content == "tool user"
    assert isinstance(rendered[1], AIMessage)
    assert isinstance(rendered[2], ToolMessage)
    assert rendered[2].tool_call_id == "call-current"
    assert rendered[-1].content == "latest user"
    assert not any(message.content == "old user " + "x" * 300 for message in rendered)
    assert not any(message.content == "old answer " + "x" * 300 for message in rendered)


async def test_hard_trim_reports_unreachable_target_without_dropping_protected_messages() -> None:
    messages = [
        HumanMessage(content="latest"),
        AIMessage(
            content="",
            tool_calls=[{"name": "search", "args": {}, "id": "call"}],
        ),
        ToolMessage(content="result", tool_call_id="call", name="search"),
    ]
    context = make_context(
        messages,
        keep_recent_turns=0,
        budget=make_budget(trigger=100, target=1),
    )

    result = await HardTrimLayer(token_counter=CharacterTokenCounter()).apply(context)

    assert len(result.model_messages) == 3
    assert "hard_trim_target_unreachable" in result.warnings[0]
    assert [message.type for message in result.model_messages] == ["human", "ai", "tool"]


async def test_model_call_compacts_once_and_reuses_same_input_for_retries(monkeypatch) -> None:
    original = HumanMessage(content="original", id="original-id")

    class FakeCompactor:
        def __init__(self) -> None:
            self.calls = 0
            self.requests: list[CompactionRequest] = []

        async def acompact(self, request: CompactionRequest) -> CompactionResult:
            self.calls += 1
            self.requests.append(request)
            entry = CompactedMessage(
                rendered=HumanMessage(content="compressed view", id="original-id"),
                sources=(MessageRef(index=0, message_id="original-id"),),
                kind="rewrite",
                layer="test",
            )
            return CompactionResult(
                entries=(entry,),
                actions=(),
                original_tokens=100,
                compacted_tokens=10,
                applied_layers=("test",),
                reached_target=True,
            )

    class FakePolicy:
        def resolve(self, model_selection) -> ContextBudget:
            return make_budget(trigger=100, target=50)

    class FakeModel:
        def __init__(self) -> None:
            self.inputs: list[object] = []
            self.calls = 0

        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            self.calls += 1
            self.inputs.append(messages)
            if self.calls == 1:
                raise RuntimeError("retry once")
            return AIMessage(content="response")

    fake_model = FakeModel()
    compactor = FakeCompactor()
    monkeypatch.setattr("agent.graphs.model_call.load_chat_model", lambda _: fake_model)
    graph = ModelCallGraph(
        config=Config(model_call_retry_attempts=2),
        compactor=compactor,
        context_budget_policy=FakePolicy(),
    )
    state = {"model": object(), "messages": [original]}
    before = copy.deepcopy(original.model_dump(mode="python"))

    result = await graph._model_call_node(state)

    assert compactor.calls == 1
    assert compactor.requests[0].messages == (original,)
    assert fake_model.calls == 2
    assert fake_model.inputs[0] is fake_model.inputs[1]
    assert fake_model.inputs[0][0].content == "compressed view"
    assert state["messages"] == [original]
    assert original.model_dump(mode="python") == before
    assert result["messages"][0].content == "response"


async def test_model_call_with_disabled_config_uses_identity_view(monkeypatch) -> None:
    seen: list[list[BaseMessage]] = []
    original = HumanMessage(content="original")

    class FakeModel:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            seen.append(messages)
            return AIMessage(content="response")

    monkeypatch.setattr("agent.graphs.model_call.load_chat_model", lambda _: FakeModel())
    graph = ModelCallGraph(
        config=Config(
            context_compaction=ContextCompactionConfig(enabled=False),
        )
    )

    await graph._model_call_node({"model": object(), "messages": [original]})

    assert seen[0] == [original]
    assert seen[0][0] is original
