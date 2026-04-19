
import asyncio

from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient({
    "exa": {
      "transport": "http",
      "url": "https://mcp.exa.ai/mcp"
    }
})

web_search_mcp_tools = asyncio.run(client.get_tools())

__all__ = [
    web_search_mcp_tools,
]