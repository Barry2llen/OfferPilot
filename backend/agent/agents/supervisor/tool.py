
from langchain.tools import BaseTool

from schemas.config import Config

async def get_all_tools(
    config: Config | None = None,
) -> list[BaseTool]:
    from ...tools import get_all_tools as get_agent_tools

    return await get_agent_tools(config=config)

__all__ = [
    "get_all_tools",
]
