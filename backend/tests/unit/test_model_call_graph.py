import asyncio
import importlib
import json
import time

import pytest
from langgraph.errors import GraphInterrupt
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.runtime import Runtime
from langgraph.types import Interrupt
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.graphs.model_call import ModelCallGraph
from agent.compaction import (
    CompactedMessage,
    CompactionResult,
    ContextBudget,
    MessageRef,
)
from agent.prompts import PromptComposer, PromptFragment
from agent.tools.query import query as query_tool
from exceptions import AgentStateError, ModelCallExecutionError
from schemas.config.base import Config


@tool
def echo_value(value: int) -> str:
    """Return the formatted value."""
    return f"value={value}"


@tool
def fail_value(value: int) -> str:
    """Raise an error for testing."""
    raise RuntimeError(f"boom: {value}")


@tool
def interrupt_value(value: int) -> str:
    """Raise a graph interrupt for testing."""
    raise GraphInterrupt(
        (
            Interrupt(
                value={
                    "type": "query",
                    "question": "Choose next step.",
                    "firstChoice": "first",
                    "firstChoiceDescription": "Use the first option.",
                    "secondChoice": "second",
                    "secondChoiceDescription": "Use the second option.",
                    "thirdChoice": "third",
                    "thirdChoiceDescription": "Use the third option.",
                },
                id=f"interrupt-{value}",
            ),
        )
    )


@tool
async def async_echo_value(value: int, delay: float = 0.0) -> str:
    """Return the formatted value asynchronously."""
    await asyncio.sleep(delay)
    return f"async-value={value}"


@tool
async def delayed_echo_value(value: int, delay: float = 0.0) -> str:
    """Return the formatted value after a delay."""
    await asyncio.sleep(delay)
    return f"delayed-value={value}"


@tool(return_direct=True)
def direct_value(value: int) -> str:
    """Return the formatted value directly."""
    return f"direct-value={value}"


@tool(response_format="content_and_artifact")
def structured_value(value: int) -> tuple[str, dict[str, int]]:
    """Return content and artifact for testing."""
    return json.dumps({"value": value}), {"raw_value": value}


def make_tool_config() -> dict:
    return {
        "configurable": {"thread_id": "thread-tool-test"},
        "metadata": {"source": "unit-test"},
    }


def make_runtime() -> Runtime[None]:
    return Runtime(context=None)


def make_tool_runtime(
    state: dict | None = None,
    *,
    tool_call_id: str = "call-query",
    config: dict | None = None,
) -> ToolRuntime[None, dict]:
    return ToolRuntime(
        state=state or make_state([]),
        context=None,
        config=config or make_tool_config(),
        stream_writer=lambda _: None,
        tool_call_id=tool_call_id,
        store=None,
    )


def run_tool_node(
    graph: ModelCallGraph,
    state: dict,
    config: dict | None = None,
) -> dict:
    return asyncio.run(
        graph._tool_node(state, make_runtime(), config or make_tool_config())
    )


def make_state(messages: list, model: object | None = None) -> dict:
    return {
        "model": object() if model is None else model,
        "messages": messages,
    }


def test_model_call_graph_can_be_imported_and_initialized_without_tools() -> None:
    graph = ModelCallGraph(config=Config(), tools=None)

    assert callable(graph.tools)


def test_interrupt_tool_queue_is_instance_scoped() -> None:
    first_graph = ModelCallGraph(config=Config(), tools=[echo_value])
    second_graph = ModelCallGraph(config=Config(), tools=[echo_value])

    first_graph._add_interrupt_tool(
        "message-first",
        {"name": "echo_value", "args": {"value": 1}, "id": "call-first"},
        echo_value,
    )

    assert len(first_graph._interrupt_tools) == 1
    assert second_graph._interrupt_tools == []


def test_tool_node_returns_original_state_when_tools_are_missing() -> None:
    graph = ModelCallGraph(config=Config(), tools=None)
    state = make_state([AIMessage(content="hello")])

    assert run_tool_node(graph, state) is state


def test_tool_node_returns_original_state_when_messages_are_empty() -> None:
    graph = ModelCallGraph(config=Config(), tools=[echo_value])
    state = make_state([])

    assert run_tool_node(graph, state) is state


def test_tool_node_returns_original_state_when_last_message_is_not_ai() -> None:
    graph = ModelCallGraph(config=Config(), tools=[echo_value])
    state = make_state([HumanMessage(content="hello")])

    assert run_tool_node(graph, state) is state


def test_tool_node_returns_original_state_when_ai_message_has_no_tool_calls() -> None:
    graph = ModelCallGraph(config=Config(), tools=[echo_value])
    state = make_state([AIMessage(content="hello")])

    assert run_tool_node(graph, state) is state


def test_tool_node_returns_error_message_when_tool_is_missing() -> None:
    graph = ModelCallGraph(config=Config(), tools=[echo_value])
    state = make_state(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "missing_tool", "args": {"value": 1}, "id": "call-missing"}],
            )
        ]
    )

    result = run_tool_node(graph, state)
    message = result["messages"][0]

    assert isinstance(message, ToolMessage)
    assert message.status == "error"
    assert message.tool_call_id == "call-missing"
    assert "not found" in message.content.lower()


def test_tool_node_executes_tool_calls_and_returns_tool_message() -> None:
    graph = ModelCallGraph(config=Config(), tools=[echo_value])
    state = make_state(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "echo_value", "args": {"value": 3}, "id": "call-echo"}],
            )
        ]
    )

    result = run_tool_node(graph, state)
    message = result["messages"][0]

    assert isinstance(message, ToolMessage)
    assert message.tool_call_id == "call-echo"
    assert message.name == "echo_value"
    assert message.content == "value=3"


def test_tool_node_preserves_structured_tool_message() -> None:
    graph = ModelCallGraph(config=Config(), tools=[structured_value])
    state = make_state(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "structured_value", "args": {"value": 4}, "id": "call-structured"}],
            )
        ]
    )

    result = run_tool_node(graph, state)
    message = result["messages"][0]

    assert isinstance(message, ToolMessage)
    assert message.tool_call_id == "call-structured"
    assert json.loads(message.content) == {"value": 4}
    assert message.artifact == {"raw_value": 4}


def test_convert_tool_message_preserves_existing_tool_message_fields() -> None:
    tool_message = ToolMessage(
        content=json.dumps({"choice": "firstChoice"}),
        artifact={"question": "Choose next step."},
        tool_call_id="call-existing",
        name="structured_value",
        status="success",
    )

    result = ModelCallGraph._convert_tool_message(
        tool_message,
        {"name": "structured_value", "args": {}, "id": "call-existing"},
        "message-existing",
        direct_value,
    )

    assert result is tool_message
    assert result.id == "message-existing"
    assert result.content == json.dumps({"choice": "firstChoice"})
    assert result.artifact == {"question": "Choose next step."}
    assert result.status == "success"
    assert result.additional_kwargs["return_direct"] is True


def test_tool_node_returns_error_message_when_tool_raises() -> None:
    graph = ModelCallGraph(config=Config(), tools=[fail_value])
    state = make_state(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "fail_value", "args": {"value": 5}, "id": "call-fail"}],
            )
        ]
    )

    result = run_tool_node(graph, state)
    message = result["messages"][0]

    assert isinstance(message, ToolMessage)
    assert message.status == "error"
    assert message.tool_call_id == "call-fail"
    assert "boom: 5" in message.content


def test_tool_node_queues_graph_interrupt_tool_for_interrupt_node() -> None:
    graph = ModelCallGraph(config=Config(), tools=[interrupt_value])
    state = make_state(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "interrupt_value", "args": {"value": 7}, "id": "call-interrupt"}],
            )
        ]
    )

    result = run_tool_node(graph, state)
    message = result["messages"][0]

    assert message.content == "[INTERRUPT_TOOL_CALLED]"
    assert len(graph._interrupt_tools) == 1
    queued_message_id, queued_tool_call, queued_tool = graph._interrupt_tools[0]
    assert queued_message_id == message.id
    assert queued_tool_call["id"] == "call-interrupt"
    assert queued_tool.name == "interrupt_value"


async def test_query_tool_keeps_display_context_out_of_llm_visible_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_interrupt(value: object) -> dict[str, str]:
        return {"choice": "firstChoice", "note": "Use this."}

    query_module = importlib.import_module("agent.tools.query")
    monkeypatch.setattr(query_module, "interrupt", fake_interrupt)

    result = await query_tool.ainvoke(
        {
            "name": "query",
            "args": {
                "question": "Choose next step.",
                "firstChoice": "first",
                "firstChoiceDescription": "Use the first option.",
                "secondChoice": "second",
                "secondChoiceDescription": "Use the second option.",
                "thirdChoice": "third",
                "thirdChoiceDescription": "Use the third option.",
                "runtime": make_tool_runtime(),
            },
            "id": "call-query",
            "type": "tool_call",
        }
    )

    assert isinstance(result, ToolMessage)
    assert json.loads(result.content) == {
        "choice": "firstChoice",
        "note": "Use this.",
    }
    assert "question" not in result.content
    assert "Use the first option." not in result.content
    assert result.artifact == {
        "question": "Choose next step.",
        "firstChoice": "first",
        "firstChoiceDescription": "Use the first option.",
        "secondChoice": "second",
        "secondChoiceDescription": "Use the second option.",
        "thirdChoice": "third",
        "thirdChoiceDescription": "Use the third option.",
    }


def test_tool_node_executes_async_tool_calls_and_returns_tool_message() -> None:
    graph = ModelCallGraph(config=Config(), tools=[async_echo_value])
    state = make_state(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "async_echo_value", "args": {"value": 7}, "id": "call-async"}],
            )
        ]
    )

    result = run_tool_node(graph, state)
    message = result["messages"][0]

    assert isinstance(message, ToolMessage)
    assert message.tool_call_id == "call-async"
    assert message.name == "async_echo_value"
    assert message.content == "async-value=7"


def test_tool_node_injects_runtime_without_mutating_original_tool_call() -> None:
    seen: list[dict[str, object]] = []

    @tool
    async def runtime_echo(
        value: int,
        *,
        runtime: ToolRuntime[None, dict],
    ) -> str:
        """Return runtime details for testing."""
        seen.append(
            {
                "state": runtime.state,
                "tool_call_id": runtime.tool_call_id,
                "config": runtime.config,
            }
        )
        return f"runtime-value={value}"

    graph = ModelCallGraph(config=Config(), tools=[runtime_echo])
    tool_call = {
        "name": "runtime_echo",
        "args": {"value": 3},
        "id": "call-runtime",
    }
    state = make_state([AIMessage(content="", tool_calls=[tool_call])])
    config = make_tool_config()

    result = run_tool_node(graph, state, config)
    message = result["messages"][0]

    assert message.content == "runtime-value=3"
    assert seen == [
        {
            "state": state,
            "tool_call_id": "call-runtime",
            "config": config,
        }
    ]
    assert state["messages"][0].tool_calls[0]["args"] == {"value": 3}


def test_tool_node_does_not_mutate_args_when_runtime_tool_raises() -> None:
    @tool
    async def runtime_fail(
        value: int,
        *,
        runtime: ToolRuntime[None, dict],
    ) -> str:
        """Raise after receiving runtime for testing."""
        assert runtime.tool_call_id == "call-runtime-fail"
        raise RuntimeError(f"runtime boom: {value}")

    graph = ModelCallGraph(config=Config(), tools=[runtime_fail])
    state = make_state(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "runtime_fail",
                        "args": {"value": 5},
                        "id": "call-runtime-fail",
                    }
                ],
            )
        ]
    )

    result = run_tool_node(graph, state)
    message = result["messages"][0]

    assert message.status == "error"
    assert "runtime boom: 5" in message.content
    assert state["messages"][0].tool_calls[0]["args"] == {"value": 5}


def test_tool_node_does_not_mutate_args_when_runtime_tool_interrupts() -> None:
    @tool
    async def runtime_interrupt(
        value: int,
        *,
        runtime: ToolRuntime[None, dict],
    ) -> str:
        """Interrupt after receiving runtime for testing."""
        raise GraphInterrupt(
            (
                Interrupt(
                    value={"type": "query", "question": f"value={value}"},
                    id=f"interrupt-{runtime.tool_call_id}",
                ),
            )
        )

    graph = ModelCallGraph(config=Config(), tools=[runtime_interrupt])
    state = make_state(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "runtime_interrupt",
                        "args": {"value": 7},
                        "id": "call-runtime-interrupt",
                    }
                ],
            )
        ]
    )

    result = run_tool_node(graph, state)
    message = result["messages"][0]

    assert message.content == "[INTERRUPT_TOOL_CALLED]"
    assert len(graph._interrupt_tools) == 1
    assert state["messages"][0].tool_calls[0]["args"] == {"value": 7}


def test_tool_node_executes_multiple_tools_concurrently_and_preserves_order() -> None:
    graph = ModelCallGraph(config=Config(), tools=[delayed_echo_value])
    state = make_state(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "delayed_echo_value", "args": {"value": 1, "delay": 0.2}, "id": "call-1"},
                    {"name": "delayed_echo_value", "args": {"value": 2, "delay": 0.2}, "id": "call-2"},
                ],
            )
        ]
    )

    start = time.perf_counter()
    result = run_tool_node(graph, state)
    elapsed = time.perf_counter() - start

    messages = result["messages"]

    assert elapsed < 0.35
    assert [message.tool_call_id for message in messages] == ["call-1", "call-2"]
    assert [message.content for message in messages] == [
        "delayed-value=1",
        "delayed-value=2",
    ]


def test_tool_node_isolates_errors_when_running_multiple_tools() -> None:
    graph = ModelCallGraph(config=Config(), tools=[async_echo_value, fail_value])
    state = make_state(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "fail_value", "args": {"value": 5}, "id": "call-fail"},
                    {"name": "async_echo_value", "args": {"value": 9}, "id": "call-async"},
                ],
            )
        ]
    )

    result = run_tool_node(graph, state)
    messages = result["messages"]

    assert len(messages) == 2
    assert messages[0].status == "error"
    assert messages[0].tool_call_id == "call-fail"
    assert "boom: 5" in messages[0].content
    assert messages[1].status == "success"
    assert messages[1].tool_call_id == "call-async"
    assert messages[1].content == "async-value=9"


def test_tool_node_uses_dynamic_tools_callable() -> None:
    seen_messages: list[list] = []

    def build_tools(runtime) -> list:
        seen_messages.append(runtime.state["messages"])
        return [echo_value]

    graph = ModelCallGraph(config=Config(), tools=build_tools)
    state = make_state(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "echo_value", "args": {"value": 11}, "id": "call-dynamic"}],
            )
        ]
    )

    result = run_tool_node(graph, state)
    message = result["messages"][0]

    assert seen_messages == [state["messages"]]
    assert message.tool_call_id == "call-dynamic"
    assert message.content == "value=11"


def test_tool_node_returns_error_when_dynamic_tools_callable_fails() -> None:
    def build_tools(runtime) -> list:
        raise RuntimeError("builder failed")

    graph = ModelCallGraph(config=Config(), tools=build_tools)
    state = make_state(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "echo_value", "args": {"value": 11}, "id": "call-builder"}],
            )
        ]
    )

    result = run_tool_node(graph, state)
    message = result["messages"][0]

    assert isinstance(message, ToolMessage)
    assert message.status == "error"
    assert message.tool_call_id == "call-builder"
    assert "builder failed" in message.content


def test_dicide_next_action_returns_end_without_tool_calls() -> None:
    graph = ModelCallGraph(config=Config(), tools=[echo_value])

    result = graph._dicide_next_action(make_state([AIMessage(content="done")]))

    assert result == "end"


def test_dicide_next_action_returns_end_with_tool_message() -> None:
    graph = ModelCallGraph(config=Config(), tools=[echo_value])

    result = graph._dicide_next_action(
        make_state([ToolMessage(content="done", tool_call_id="call-done")])
    )

    assert result == "end"


def test_dicide_next_action_returns_tool_with_tool_calls() -> None:
    graph = ModelCallGraph(config=Config(), tools=[echo_value])

    result = graph._dicide_next_action(
        make_state(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "echo_value", "args": {"value": 1}, "id": "call-next"}],
                )
            ]
        )
    )

    assert result == "tool"


def test_dicide_after_tool_returns_end_for_return_direct_tool_message() -> None:
    graph = ModelCallGraph(config=Config(), tools=[direct_value])

    result = graph._dicide_after_tool(
        make_state(
            [
                ToolMessage(
                    content="done",
                    tool_call_id="call-direct",
                    additional_kwargs={"return_direct": True},
                )
            ]
        )
    )

    assert result == "end"


def test_dicide_after_tool_returns_model_for_regular_tool_message() -> None:
    graph = ModelCallGraph(config=Config(), tools=[echo_value])

    result = graph._dicide_after_tool(
        make_state([ToolMessage(content="done", tool_call_id="call-regular")])
    )

    assert result == "model"


@pytest.mark.parametrize(
    "state",
    [
        make_state([]),
        make_state([HumanMessage(content="hello")]),
    ],
)
def test_dicide_next_action_raises_for_invalid_state(state: dict) -> None:
    graph = ModelCallGraph(config=Config(), tools=[echo_value])

    with pytest.raises(AgentStateError):
        graph._dicide_next_action(state)


async def test_compiled_graph_ends_after_return_direct_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeModel:
        def __init__(self) -> None:
            self.calls = 0

        def bind_tools(self, tools: object) -> "FakeModel":
            return self

        async def ainvoke(self, messages: object) -> AIMessage:
            self.calls += 1
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "direct_value",
                        "args": {"value": 42},
                        "id": "call-direct",
                    }
                ],
            )

    fake_model = FakeModel()
    monkeypatch.setattr(
        "agent.graphs.model_call.load_chat_model",
        lambda model_selection: fake_model,
    )

    graph = ModelCallGraph(config=Config(), tools=[direct_value]).get_compiled_graph()
    result = await graph.ainvoke(make_state([HumanMessage(content="hello")]))
    message = result["messages"][-1]

    assert fake_model.calls == 1
    assert isinstance(message, ToolMessage)
    assert message.content == "direct-value=42"
    assert message.name == "direct_value"
    assert message.tool_call_id == "call-direct"
    assert message.additional_kwargs["return_direct"] is True


async def test_runtime_tool_start_event_does_not_expose_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @tool
    async def runtime_echo(
        value: int,
        *,
        runtime: ToolRuntime[None, dict],
    ) -> str:
        """Return runtime-aware value."""
        assert runtime.tool_call_id == "call-runtime-event"
        return f"runtime-value={value}"

    class FakeModel:
        def __init__(self) -> None:
            self.calls = 0

        def bind_tools(self, tools: object) -> "FakeModel":
            return self

        async def ainvoke(self, messages: object) -> AIMessage:
            self.calls += 1
            if self.calls == 1:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "runtime_echo",
                            "args": {"value": 8},
                            "id": "call-runtime-event",
                        }
                    ],
                )
            return AIMessage(content="done")

    fake_model = FakeModel()
    monkeypatch.setattr(
        "agent.graphs.model_call.load_chat_model",
        lambda model_selection: fake_model,
    )

    graph = ModelCallGraph(config=Config(), tools=[runtime_echo]).get_compiled_graph()
    tool_start_inputs: list[object] = []

    async for event in graph.astream_events(
        make_state([HumanMessage(content="hello")]),
        {"configurable": {"thread_id": "thread-runtime-event"}},
        version="v2",
    ):
        if event.get("event") == "on_tool_start":
            data = event.get("data")
            if isinstance(data, dict):
                tool_start_inputs.append(data.get("input"))

    assert tool_start_inputs == [{"value": 8}]


async def test_model_call_node_binds_tools_and_returns_response(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[tuple[str, object]] = []
    response = AIMessage(content="model-response")

    class FakeModel:
        def bind_tools(self, tools: object) -> "FakeModel":
            events.append(("bind_tools", tools))
            return self

        async def ainvoke(self, messages: object) -> AIMessage:
            events.append(("ainvoke", messages))
            return response

    loaded_models: list[object] = []

    def fake_load_chat_model(model_selection: object) -> FakeModel:
        loaded_models.append(model_selection)
        return FakeModel()

    monkeypatch.setattr("agent.graphs.model_call.load_chat_model", fake_load_chat_model)

    graph = ModelCallGraph(config=Config(model_call_retry_attempts=2), tools=[echo_value])
    selected_model = object()
    state = make_state([HumanMessage(content="hello")], model=selected_model)

    result = await graph._model_call_node(state)

    assert loaded_models == [selected_model]
    assert events == [
        ("bind_tools", (echo_value,)),
        ("ainvoke", state["messages"]),
    ]
    assert result["messages"] == [response]


async def test_model_call_node_binds_dynamic_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[tuple[str, object]] = []
    response = AIMessage(content="dynamic-model-response")

    class FakeModel:
        def bind_tools(self, tools: object) -> "FakeModel":
            events.append(("bind_tools", tools))
            return self

        async def ainvoke(self, messages: object) -> AIMessage:
            events.append(("ainvoke", messages))
            return response

    monkeypatch.setattr(
        "agent.graphs.model_call.load_chat_model",
        lambda model_selection: FakeModel(),
    )

    def build_tools(runtime) -> list:
        assert runtime.state["messages"][0].content == "hello"
        return [echo_value]

    graph = ModelCallGraph(config=Config(), tools=build_tools)
    state = make_state([HumanMessage(content="hello")])

    result = await graph._model_call_node(state)

    assert events == [
        ("bind_tools", (echo_value,)),
        ("ainvoke", state["messages"]),
    ]
    assert result["messages"] == [response]


async def test_model_call_node_resolves_prompt_composer_to_system_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_messages: list[object] = []
    response = AIMessage(content="composed-system-prompt")

    class FakeModel:
        def bind_tools(self, tools: object) -> "FakeModel":
            return self

        async def ainvoke(self, messages: object) -> AIMessage:
            seen_messages.append(messages)
            return response

    monkeypatch.setattr(
        "agent.graphs.model_call.load_chat_model",
        lambda model_selection: FakeModel(),
    )

    graph = ModelCallGraph(
        config=Config(),
        system_prompts=PromptComposer(
            [
                PromptFragment(name="Instructions", content="Use attachments."),
                PromptFragment(
                    name="Metadata",
                    content=lambda runtime: f"messages={len(runtime.state['messages'])}",
                ),
            ]
        ),
    )
    state = make_state([HumanMessage(content="hello")])

    result = await graph._model_call_node(state)

    assert result["messages"] == [response]
    messages = seen_messages[0]
    assert isinstance(messages, list)
    assert len(messages) == 2
    assert messages[0].type == "system"
    assert "Instructions:\nUse attachments." in messages[0].content
    assert "Metadata:\nmessages=1" in messages[0].content
    assert messages[1] == state["messages"][0]


async def test_model_call_node_resolves_dynamic_system_prompt_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_messages: list[object] = []
    response = AIMessage(content="dynamic-system-prompt")

    class FakeModel:
        def bind_tools(self, tools: object) -> "FakeModel":
            return self

        async def ainvoke(self, messages: object) -> AIMessage:
            seen_messages.append(messages)
            return response

    monkeypatch.setattr(
        "agent.graphs.model_call.load_chat_model",
        lambda model_selection: FakeModel(),
    )

    def build_system_prompts(runtime) -> list[str]:
        return ["dynamic one", f"message-count={len(runtime.state['messages'])}"]

    graph = ModelCallGraph(config=Config(), system_prompts=build_system_prompts)
    state = make_state([HumanMessage(content="hello")])

    result = await graph._model_call_node(state)

    assert result["messages"] == [response]
    messages = seen_messages[0]
    assert isinstance(messages, list)
    assert [message.type for message in messages] == ["system", "system", "human"]
    assert [message.content for message in messages[:2]] == [
        "dynamic one",
        "message-count=1",
    ]
    assert messages[2] == state["messages"][0]


async def test_model_call_node_accepts_awaitable_tools_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    bound_tools: list[object] = []
    response = AIMessage(content="awaitable-tools")

    class FakeModel:
        def bind_tools(self, tools: object) -> "FakeModel":
            bound_tools.append(tools)
            return self

        async def ainvoke(self, messages: object) -> AIMessage:
            return response

    monkeypatch.setattr(
        "agent.graphs.model_call.load_chat_model",
        lambda model_selection: FakeModel(),
    )

    async def build_tools(runtime) -> list:
        return [echo_value]

    graph = ModelCallGraph(config=Config(), tools=build_tools)
    result = await graph._model_call_node(make_state([HumanMessage(content="hello")]))

    assert bound_tools == [(echo_value,)]
    assert result["messages"] == [response]


async def test_model_call_node_accepts_async_iterable_tools_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    bound_tools: list[object] = []
    response = AIMessage(content="async-iterable-tools")

    class FakeModel:
        def bind_tools(self, tools: object) -> "FakeModel":
            bound_tools.append(tools)
            return self

        async def ainvoke(self, messages: object) -> AIMessage:
            return response

    monkeypatch.setattr(
        "agent.graphs.model_call.load_chat_model",
        lambda model_selection: FakeModel(),
    )

    async def iter_tools():
        yield echo_value

    def build_tools(runtime):
        return iter_tools()

    graph = ModelCallGraph(config=Config(), tools=build_tools)
    result = await graph._model_call_node(make_state([HumanMessage(content="hello")]))

    assert bound_tools == [(echo_value,)]
    assert result["messages"] == [response]


async def test_model_call_node_accepts_awaitable_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    bound_tools: list[object] = []
    response = AIMessage(content="awaitable-tools")

    class FakeModel:
        def bind_tools(self, tools: object) -> "FakeModel":
            bound_tools.append(tools)
            return self

        async def ainvoke(self, messages: object) -> AIMessage:
            return response

    monkeypatch.setattr(
        "agent.graphs.model_call.load_chat_model",
        lambda model_selection: FakeModel(),
    )

    async def load_tools() -> list:
        return [echo_value]

    graph = ModelCallGraph(config=Config(), tools=load_tools())
    result = await graph._model_call_node(make_state([HumanMessage(content="hello")]))

    assert bound_tools == [(echo_value,)]
    assert result["messages"] == [response]


async def test_model_call_node_accepts_async_iterable_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    bound_tools: list[object] = []
    response = AIMessage(content="async-iterable-tools")

    class FakeModel:
        def bind_tools(self, tools: object) -> "FakeModel":
            bound_tools.append(tools)
            return self

        async def ainvoke(self, messages: object) -> AIMessage:
            return response

    monkeypatch.setattr(
        "agent.graphs.model_call.load_chat_model",
        lambda model_selection: FakeModel(),
    )

    async def load_tools():
        yield echo_value

    graph = ModelCallGraph(config=Config(), tools=load_tools())
    result = await graph._model_call_node(make_state([HumanMessage(content="hello")]))

    assert bound_tools == [(echo_value,)]
    assert result["messages"] == [response]


async def test_model_call_node_records_reasoning_duration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = AIMessage(
        content="答案",
        additional_kwargs={"reasoning_content": "先分析问题。"},
    )
    custom_events: list[tuple[str, object]] = []
    ticks = iter([10.0, 12.345])

    class FakeModel:
        def bind_tools(self, tools: object) -> "FakeModel":
            return self

        async def ainvoke(self, messages: object) -> AIMessage:
            return response

    monkeypatch.setattr(
        "agent.graphs.model_call.load_chat_model",
        lambda model_selection: FakeModel(),
    )
    monkeypatch.setattr("agent.graphs.model_call.perf_counter", lambda: next(ticks))

    async def record_custom_event(name: str, data: object) -> None:
        custom_events.append((name, data))

    monkeypatch.setattr(
        "agent.graphs.model_call._adispatch_custom_event_safely",
        record_custom_event,
    )

    graph = ModelCallGraph(config=Config(), tools=[echo_value])
    result = await graph._model_call_node(make_state([HumanMessage(content="hello")]))
    message = result["messages"][0]

    assert message.additional_kwargs["reasoning_duration_ms"] == 2345
    assert custom_events == [("on_reasoning_done", {"duration_ms": 2345})]


async def test_model_call_node_retries_until_success(monkeypatch: pytest.MonkeyPatch) -> None:
    response = AIMessage(content="recovered")

    class FakeModel:
        def __init__(self) -> None:
            self.calls = 0

        def bind_tools(self, tools: object) -> "FakeModel":
            return self

        async def ainvoke(self, messages: object) -> AIMessage:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary failure")
            return response

    fake_model = FakeModel()

    def fake_load_chat_model(model_selection: object) -> FakeModel:
        return fake_model

    monkeypatch.setattr("agent.graphs.model_call.load_chat_model", fake_load_chat_model)

    graph = ModelCallGraph(config=Config(model_call_retry_attempts=2), tools=[echo_value])
    result = await graph._model_call_node(make_state([HumanMessage(content="hello")]))

    assert fake_model.calls == 2
    assert result["messages"] == [response]


async def test_model_call_node_resolves_callable_model_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = AIMessage(content="callable-model")
    resolved_model = object()
    seen_states: list[dict] = []
    loaded_models: list[object] = []

    class FakeModel:
        def bind_tools(self, tools: object) -> "FakeModel":
            return self

        async def ainvoke(self, messages: object) -> AIMessage:
            return response

    def fake_load_chat_model(model_selection: object) -> FakeModel:
        loaded_models.append(model_selection)
        return FakeModel()

    monkeypatch.setattr("agent.graphs.model_call.load_chat_model", fake_load_chat_model)

    def select_model(*, state: dict) -> object:
        seen_states.append(state)
        return resolved_model

    graph = ModelCallGraph(config=Config(), tools=[echo_value])
    state = make_state([HumanMessage(content="hello")], model=select_model)

    result = await graph._model_call_node(state)

    assert seen_states == [state]
    assert loaded_models == [resolved_model]
    assert result["messages"] == [response]


async def test_model_call_node_raises_domain_error_after_non_retry_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeModel:
        def bind_tools(self, tools: object) -> "FakeModel":
            return self

        async def ainvoke(self, messages: object) -> AIMessage:
            raise RuntimeError("permanent failure")

    monkeypatch.setattr(
        "agent.graphs.model_call.load_chat_model",
        lambda model_selection: FakeModel(),
    )
    monkeypatch.setattr(
        "agent.graphs.model_call.interrupt",
        lambda payload: {"type": "abort", "prompt": "stop"},
    )

    graph = ModelCallGraph(config=Config(model_call_retry_attempts=2), tools=[echo_value])

    with pytest.raises(ModelCallExecutionError, match="Model call failed after 2 retries"):
        await graph._model_call_node(make_state([HumanMessage(content="hello")]))


async def test_model_call_node_preserves_tool_resolution_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    custom_events: list[tuple[str, object]] = []
    selected_model = object()

    def build_tools(runtime) -> list:
        raise RuntimeError("tool resolution failed")

    async def record_custom_event(name: str, data: object) -> None:
        custom_events.append((name, data))

    monkeypatch.setattr(
        "agent.graphs.model_call._adispatch_custom_event_safely",
        record_custom_event,
    )
    monkeypatch.setattr(
        "agent.graphs.model_call.interrupt",
        lambda payload: {"type": "abort", "prompt": "stop"},
    )

    graph = ModelCallGraph(config=Config(), tools=build_tools)

    with pytest.raises(ModelCallExecutionError, match="tool resolution failed"):
        await graph._model_call_node(
            make_state([HumanMessage(content="hello")], model=selected_model)
    )

    assert custom_events[0][0] == "on_model_load_error"
    assert "tool resolution failed" in custom_events[0][1]["error"]
    assert custom_events[0][1]["model"] is selected_model


class FixedContextBudgetPolicy:
    def resolve(self, model_selection: object) -> ContextBudget:
        del model_selection
        return ContextBudget(
            max_context_tokens=10_000,
            reserved_output_tokens=100,
            safety_margin_tokens=0,
        )


class PersistedViewCompactor:
    def __init__(self) -> None:
        self.calls = 0

    async def acompact(self, request) -> CompactionResult:
        self.calls += 1
        raw_messages = request.runtime.state["messages"]
        view = HumanMessage(content="compact model view", id="compact-view")
        return CompactionResult(
            entries=(
                CompactedMessage(
                    rendered=view,
                    sources=(MessageRef(index=0, message_id="raw"),),
                    kind="identity",
                    layer="test",
                ),
            ),
            actions=(),
            original_tokens=100,
            compacted_tokens=20,
            applied_layers=("test",),
            source_message_count=len(raw_messages),
            source_message_ids=tuple(getattr(message, "id", None) for message in raw_messages),
            snapshot_status="complete",
            auto_compacted=True,
            auto_compacted_this_run=True,
            should_persist_snapshot=True,
        )


async def test_compaction_sidecar_is_checkpointed_before_business_model_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_model_inputs: list[object] = []

    class FakeModel:
        def bind_tools(self, tools: object) -> "FakeModel":
            del tools
            return self

        async def ainvoke(self, messages: object) -> AIMessage:
            seen_model_inputs.append(messages)
            return AIMessage(content="business response")

    monkeypatch.setattr(
        "agent.graphs.model_call.load_chat_model",
        lambda model_selection: FakeModel(),
    )
    compactor = PersistedViewCompactor()
    saver = InMemorySaver()
    graph = ModelCallGraph(
        config=Config(),
        tools=None,
        compactor=compactor,
        context_budget_policy=FixedContextBudgetPolicy(),
    ).get_compiled_graph(checkpointer=saver)
    config = {"configurable": {"thread_id": "sidecar-before-model"}}

    result = await graph.ainvoke(
        make_state([HumanMessage(content="raw history")], model="test-model"),
        config,
    )

    assert compactor.calls == 1
    assert seen_model_inputs == [[HumanMessage(content="compact model view", id="compact-view")]]
    assert result["messages"][0].content == "raw history"
    assert result["messages"][-1].content == "business response"
    checkpoint = saver.get_tuple(config)
    assert checkpoint is not None
    stored_snapshot = checkpoint.checkpoint["channel_values"]["context_compaction"]
    assert stored_snapshot["status"] == "complete"
    assert stored_snapshot["auto_compacted"] is True
    assert stored_snapshot["messages"][0].content == "compact model view"


async def test_successful_compaction_sidecar_survives_business_model_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingModel:
        def bind_tools(self, tools: object) -> "FailingModel":
            del tools
            return self

        async def ainvoke(self, messages: object) -> AIMessage:
            del messages
            raise RuntimeError("business model failed")

    monkeypatch.setattr(
        "agent.graphs.model_call.load_chat_model",
        lambda model_selection: FailingModel(),
    )
    monkeypatch.setattr(
        "agent.graphs.model_call.interrupt",
        lambda payload: {"type": "abort", "prompt": "stop"},
    )
    compactor = PersistedViewCompactor()
    saver = InMemorySaver()
    graph = ModelCallGraph(
        config=Config(model_call_retry_attempts=1),
        tools=None,
        compactor=compactor,
        context_budget_policy=FixedContextBudgetPolicy(),
    ).get_compiled_graph(checkpointer=saver)
    config = {"configurable": {"thread_id": "sidecar-model-failure"}}

    with pytest.raises(ModelCallExecutionError, match="Model call failed after 1 retries"):
        await graph.ainvoke(
            make_state([HumanMessage(content="raw history")], model="test-model"),
            config,
        )

    checkpoint = saver.get_tuple(config)
    assert checkpoint is not None
    stored_snapshot = checkpoint.checkpoint["channel_values"]["context_compaction"]
    assert stored_snapshot["status"] == "complete"
    assert stored_snapshot["messages"][0].content == "compact model view"
