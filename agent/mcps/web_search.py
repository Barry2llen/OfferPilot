
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any, AsyncIterator

import httpx
from langchain.tools import BaseTool
import langchain_mcp_adapters.sessions as mcp_sessions
from langchain_mcp_adapters.client import MultiServerMCPClient
from mcp.client.streamable_http import (
    create_mcp_http_client,
    streamable_http_client,
)


@asynccontextmanager
async def _streamable_http_client(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float | timedelta = 30,
    sse_read_timeout: float | timedelta = 60 * 5,
    terminate_on_close: bool = True,
    httpx_client_factory: Any = create_mcp_http_client,
    auth: httpx.Auth | None = None,
) -> AsyncIterator[tuple[Any, Any, Any]]:
    timeout_seconds = timeout.total_seconds() if isinstance(timeout, timedelta) else timeout
    read_timeout_seconds = (
        sse_read_timeout.total_seconds()
        if isinstance(sse_read_timeout, timedelta)
        else sse_read_timeout
    )
    client = httpx_client_factory(
        headers=headers,
        timeout=httpx.Timeout(timeout_seconds, read=read_timeout_seconds),
        auth=auth,
    )
    async with client:
        async with streamable_http_client(
            url,
            http_client=client,
            terminate_on_close=terminate_on_close,
        ) as streams:
            yield streams


# langchain-mcp-adapters 0.2.2 still calls the deprecated MCP alias.
mcp_sessions.streamablehttp_client = _streamable_http_client

client = MultiServerMCPClient({
    "exa": {
      "transport": "http",
      "url": "https://mcp.exa.ai/mcp"
    }
})

web_search_mcp_tools: list[BaseTool] = []


async def get_web_search_mcp_tools():
    if web_search_mcp_tools:
        return web_search_mcp_tools
    tools = await client.get_tools()
    web_search_mcp_tools.extend(tools)
    return web_search_mcp_tools

__all__ = [
    "get_web_search_mcp_tools"
]
