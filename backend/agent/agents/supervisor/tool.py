from langchain.tools import BaseTool

from schemas.config import Config

from ...tools.analysis import AnalysisToolDependencies, get_analysis_tools


async def get_all_tools(
    config: Config | None = None,
) -> list[BaseTool]:
    from ...tools import get_all_tools as get_agent_tools

    return await get_agent_tools(config=config)


def get_analysis_tools_for_supervisor(
    dependencies: AnalysisToolDependencies,
) -> list[BaseTool]:
    return get_analysis_tools(dependencies)


__all__ = [
    "get_all_tools",
    "get_analysis_tools_for_supervisor",
]
