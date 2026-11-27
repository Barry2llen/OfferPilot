from langchain.tools import ToolRuntime, tool
from pydantic import Field

from agent.async_tools import AsyncToolCall, NotifyMode
from agent.interactions import InteractionContext


@tool
async def run_async_tools(
    runtime: ToolRuntime[InteractionContext | None],
    calls: list[AsyncToolCall] = Field(
        description="Independent tool calls to start concurrently.",
        examples=[[{"name": "analyze_resume", "args": {"resume_id": 1}}]],
        min_length=1,
    ),
    notify: NotifyMode = Field(
        description="all delivers the whole batch when it finishes; any delivers each finished call.",
        examples=["all", "any"],
    ),
) -> str:
    """Start tools in the background and immediately return their batch and call IDs.

    Continue other work or yield while they run. Results, including errors, will
    arrive as tool messages in this conversation. Choose all if you need the
    entire batch, or any if you can use individual results as they finish.
    """
    submit = runtime.context.submit_async_tools if runtime.context else None
    if submit is None:
        raise ValueError("Background tools are unavailable in this execution.")
    return submit(calls, notify)
