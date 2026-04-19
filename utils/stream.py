
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