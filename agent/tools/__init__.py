
from langchain_core.tools import BaseTool

from schemas.config import Config

from .web_search import get_web_search_tools, web_search_tools


def get_all_tools(
    config: Config | None = None,
    *,
    allow_mcp_fallback: bool = False,
) -> list[BaseTool]:
    return get_web_search_tools(
        config,
        allow_mcp_fallback=allow_mcp_fallback,
    )

__all__ = [
    "get_all_tools",
    "get_web_search_tools",
    "web_search_tools",
]
