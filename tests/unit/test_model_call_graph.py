import asyncio
import time

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from agent.graphs.model_call import ModelCallGraph
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
async def async_echo_value(value: int, delay: float = 0.0) -> str:
    """Return the formatted value asynchronously."""
    await asyncio.sleep(delay)
    return f"async-value={value}"


@tool
async def delayed_echo_value(value: int, delay: float = 0.0) -> str:
    """Return the formatted value after a delay."""
    await asyncio.sleep(delay)
    return f"delayed-value={value}"


def run_tool_node(graph: ModelCallGraph, state: dict) -> dict:
    return asyncio.run(graph._tool_node(state))


def make_state(messages: list, model: object | None = None) -> dict:
    return {
        "model": object() if model is None else model,
        "messages": messages,
    }


def test_model_call_graph_can_be_imported_and_initialized_without_tools() -> None:
    graph = ModelCallGraph(config=Config(), tools=None)

    assert graph.tools == ()
    assert graph.tools_dict == {}


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


def test_dicide_next_action_returns_end_without_tool_calls() -> None:
    graph = ModelCallGraph(config=Config(), tools=[echo_value])

    result = graph._dicide_next_action(make_state([AIMessage(content="done")]))

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


def test_model_call_node_binds_tools_and_returns_response(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[tuple[str, object]] = []
    response = AIMessage(content="model-response")

    class FakeModel:
        def bind_tools(self, tools: object) -> "FakeModel":
            events.append(("bind_tools", tools))
            return self

        def invoke(self, messages: object) -> AIMessage:
            events.append(("invoke", messages))
            return response

    loaded_models: list[object] = []

    def fake_load_chat_model(model_selection: object) -> FakeModel:
        loaded_models.append(model_selection)
        return FakeModel()

    monkeypatch.setattr("agent.graphs.model_call.load_chat_model", fake_load_chat_model)

    graph = ModelCallGraph(config=Config(model_call_retry_attempts=2), tools=[echo_value])
    selected_model = object()
    state = make_state([HumanMessage(content="hello")], model=selected_model)

    result = graph._model_call_node(state)

    assert loaded_models == [selected_model]
    assert events == [
        ("bind_tools", graph.tools),
        ("invoke", state["messages"]),
    ]
    assert result["messages"] == [response]


def test_model_call_node_retries_until_success(monkeypatch: pytest.MonkeyPatch) -> None:
    response = AIMessage(content="recovered")

    class FakeModel:
        def __init__(self) -> None:
            self.calls = 0

        def bind_tools(self, tools: object) -> "FakeModel":
            return self

        def invoke(self, messages: object) -> AIMessage:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary failure")
            return response

    fake_model = FakeModel()

    def fake_load_chat_model(model_selection: object) -> FakeModel:
        return fake_model

    monkeypatch.setattr("agent.graphs.model_call.load_chat_model", fake_load_chat_model)

    graph = ModelCallGraph(config=Config(model_call_retry_attempts=2), tools=[echo_value])
    result = graph._model_call_node(make_state([HumanMessage(content="hello")]))

    assert fake_model.calls == 2
    assert result["messages"] == [response]


def test_model_call_node_resolves_callable_model_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = AIMessage(content="callable-model")
    resolved_model = object()
    seen_states: list[dict] = []
    loaded_models: list[object] = []

    class FakeModel:
        def bind_tools(self, tools: object) -> "FakeModel":
            return self

        def invoke(self, messages: object) -> AIMessage:
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

    result = graph._model_call_node(state)

    assert seen_states == [state]
    assert loaded_models == [resolved_model]
    assert result["messages"] == [response]


def test_model_call_node_raises_domain_error_after_non_retry_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeModel:
        def bind_tools(self, tools: object) -> "FakeModel":
            return self

        def invoke(self, messages: object) -> AIMessage:
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
        graph._model_call_node(make_state([HumanMessage(content="hello")]))
