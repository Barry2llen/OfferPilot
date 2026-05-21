
from langchain.tools import BaseTool

from schemas.config import Config

async def get_all_tools(
    config: Config | None = None,
) -> list[BaseTool]:
    from ...tools import get_web_search_tools

    tools = []
    tools.extend(await get_web_search_tools(config=config))

    return tools

__all__ = [
    "get_all_tools",
]