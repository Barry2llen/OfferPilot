
from typing import AsyncIterator, Callable
from langchain_core.runnables.schema import StreamEvent

async def render_stream_events(
        events: AsyncIterator[StreamEvent],
        *,
        on_event: Callable[[StreamEvent], None] | None = None,
        on_chat_model_stream: Callable[[StreamEvent], None] | None = None,
        on_tool_start: Callable[[StreamEvent], None] | None = None,
        on_tool_end: Callable[[StreamEvent], None] | None = None,
    ) -> None:
    async for event in events:
        if on_event:
            on_event(event)
        match kind := event["event"]:
            case "on_chat_model_stream":
                if on_chat_model_stream:
                    on_chat_model_stream(event)
                # event["data"]["chunk"].content 的类型是 list[dict] | str，取决于你的输入格式
                # 例如，如果你输入的是 
                #   [
                #       {"type": "text", "text": "hello"}, 
                #       {"type": "image_url", "image_url": {"url": "http://example.com/image.png"}}
                #   ]
                # 那么 content 就是list[dict]，如果你输入的是 "hello"，那么 content 就是 str。
                # 每个 dict 都有一个 "type" 字段，表示内容的类型，可以是 "text" 或 "image_url"。
                # 如果是 "text"，则有一个 "text" 字段，表示文本内容；如果是 "image_url"，则有一个 "image_url" 字段，表示图片的 URL。
            case "on_tool_start":
                if on_tool_start:
                    on_tool_start(event)
                # f'CALLED {event["name"]}({", ".join(f"{k}={v}" for k, v in event["data"]["input"].items())})'
            case "on_tool_end":
                if on_tool_end:
                    on_tool_end(event)
                # tool_msg: ToolMessage = event["data"]["output"]
            case _:
                pass