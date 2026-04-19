
import asyncio

from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient({
    "exa": {
      "transport": "http",
      "url": "https://mcp.exa.ai/mcp"
    }
})

# blobs = asyncio.run(client.get_resources("exa"))
# web_search_tools_resources = "\n\n".join(blob.as_string() for blob in blobs if blob.mimetype.startswith("application/json"))
web_search_tools = asyncio.run(client.get_tools())


__all__ = [
    web_search_tools,
]