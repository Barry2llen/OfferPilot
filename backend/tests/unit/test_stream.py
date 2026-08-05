import json

from langchain_core.messages import AIMessage, ToolMessage
from pydantic import BaseModel

from utils.stream import render_sse_event, to_jsonable


class _Payload(BaseModel):
    name: str
    count: int


def test_to_jsonable_preserves_base_message_fields() -> None:
    message = ToolMessage(
        content="工具输出",
        tool_call_id="call-1",
        name="search",
        status="success",
    )

    assert to_jsonable(message) == {
        "type": "tool",
        "content": "工具输出",
        "name": "search",
        "tool_call_id": "call-1",
        "status": "success",
    }


def test_to_jsonable_recurses_models_messages_and_tuples() -> None:
    value = {
        "model": _Payload(name="示例", count=2),
        "messages": (AIMessage(content="hello"),),
    }

    assert to_jsonable(value) == {
        "model": {"name": "示例", "count": 2},
        "messages": [{"type": "ai", "content": "hello"}],
    }


def test_render_sse_event_keeps_event_and_json_wire_format() -> None:
    rendered = render_sse_event("final", {"content": "你好"})

    assert rendered.startswith("event: final\ndata: ")
    assert rendered.endswith("\n\n")
    data_line = rendered.splitlines()[1]
    assert json.loads(data_line.removeprefix("data: ")) == {"content": "你好"}
