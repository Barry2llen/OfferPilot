
from langchain_core.tools import BaseTool

from .web_search import web_search_tools

def get_all_tools() -> list[BaseTool]:
    return web_search_tools

__all__ = [
    get_all_tools
]