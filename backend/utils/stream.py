
from typing import (
    AsyncIterator,
    Awaitable,
    Callable,
    Any
)
import json
from pydantic import BaseModel
from langchain_core.runnables.schema import StreamEvent

"""
        | event                  | name                 | chunk                               | input                                             | output                                              |
        | ---------------------- | -------------------- | ----------------------------------- | ------------------------------------------------- | --------------------------------------------------- |
        | `on_chat_model_start`  | `'[model name]'`     |                                     | `{"messages": [[SystemMessage, HumanMessage]]}`   |                                                     |
        | `on_chat_model_stream` | `'[model name]'`     | `AIMessageChunk(content="hello")`   |                                                   |                                                     |
        | `on_chat_model_end`    | `'[model name]'`     |                                     | `{"messages": [[SystemMessage, HumanMessage]]}`   | `AIMessageChunk(content="hello world")`             |
        | `on_llm_start`         | `'[model name]'`     |                                     | `{'input': 'hello'}`                              |                                                     |
        | `on_llm_stream`        | `'[model name]'`     | `'Hello' `                          |                                                   |                                                     |
        | `on_llm_end`           | `'[model name]'`     |                                     | `'Hello human!'`                                  |                                                     |
        | `on_chain_start`       | `'format_docs'`      |                                     |                                                   |                                                     |
        | `on_chain_stream`      | `'format_docs'`      | `'hello world!, goodbye world!'`    |                                                   |                                                     |
        | `on_chain_end`         | `'format_docs'`      |                                     | `[Document(...)]`                                 | `'hello world!, goodbye world!'`                    |
        | `on_tool_start`        | `'some_tool'`        |                                     | `{"x": 1, "y": "2"}`                              |                                                     |
        | `on_tool_end`          | `'some_tool'`        |                                     |                                                   | `{"x": 1, "y": "2"}`                                |
        | `on_retriever_start`   | `'[retriever name]'` |                                     | `{"query": "hello"}`                              |                                                     |
        | `on_retriever_end`     | `'[retriever name]'` |                                     | `{"query": "hello"}`                              | `[Document(...), ..]`                               |
        | `on_prompt_start`      | `'[template_name]'`  |                                     | `{"question": "hello"}`                           |                                                     |
        | `on_prompt_end`        | `'[template_name]'`  |                                     | `{"question": "hello"}`                           | `ChatPromptValue(messages: [SystemMessage, ...])`   |
"""

type StreamEventName = str

type StreamEventHandler = Callable[[StreamEvent], Any] | Callable[[StreamEvent], Awaitable[Any]]

async def render_stream_events(
        events: AsyncIterator[StreamEvent],
        *,
        handlers: dict[StreamEventName, StreamEventHandler] | None = None,
        returns: StreamEventHandler | None = None
    ) -> Any:
    result: Any = None
    async for event in events:
        event_name = event["event"]
        if handlers and event_name in handlers:
            handler = handlers[event_name]
            res = handler(event)
            if isinstance(res, Awaitable):
                await res
        if returns and event_name == "on_chain_end":
            res = returns(event)
            if isinstance(res, Awaitable):
                result = await res
            else:
                result = res
    return result

def _to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_to_jsonable(item) for item in value]

    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value

def render_sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(_to_jsonable(data), ensure_ascii=False)}\n\n"

__all__ = [
    "render_sse_event",
    "render_stream_events",
    "StreamEventHandler",
    "StreamEventName"
]
