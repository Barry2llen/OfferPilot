from langchain_core.tools import BaseTool, tool
from pydantic import Field

from schemas.config import Config, load_config
from utils.logger import logger


async def get_web_search_tools(
    config: Config | None = None,
    *,
    allow_mcp_fallback: bool = False,
) -> list[BaseTool]:
    target_config = config or load_config()
    if not target_config.exa_api_key:
        if not allow_mcp_fallback:
            logger.warning("No Exa API key configured; web search tools are disabled.")
            return []

        try:
            from ..mcps.web_search import get_web_search_mcp_tools
        except Exception as error:
            logger.warning(f"Failed to load MCP web search tools: {error}")
            return []
        return list(await get_web_search_mcp_tools())

    from exa_py import AsyncExa

    exa = AsyncExa(target_config.exa_api_key)

    @tool
    async def web_search_exa(
        query: str = Field(
            description=(
                "Natural language search query. Should be a semantically rich "
                "description of the ideal page, not just keywords."
            )
        ),
        num_results: int = Field(
            default=10,
            gt=1,
            lt=100,
            description="The number of search results to return",
        ),
        include_domains: list[str] = Field(
            default=None,
            description="Domains to include in the search.",
        ),
        exclude_domains: list[str] = Field(
            default=None,
            description="Domains to exclude from the search.",
        ),
    ) -> str:
        """
        Search the web for current information and return ready-to-use content.
        """

        return await exa.search(
            query,
            num_results=num_results,
            type=target_config.web_search.type,
            stream=False,
            user_location="CN",
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            contents={
                "highlights": {
                    "max_characters": target_config.web_search.max_characters,
                    "guiding_query": target_config.web_search.guiding_query,
                }
            },
        )

    @tool
    async def web_fetch_exa(
        urls: list[str] = Field(description="The list of URLs to fetch content from"),
    ) -> str:
        """
        Read webpage content as clean markdown.
        """

        return await exa.get_contents(urls)

    @tool
    async def find_similar_exa(
        url: str = Field(description="The URL to find similar pages for."),
        num_results: int = Field(
            default=None,
            description="Number of results to return. Default is None.",
        ),
        include_domains: list[str] = Field(
            default=None,
            description="Domains to include in the search.",
        ),
        exclude_domains: list[str] = Field(
            default=None,
            description="Domains to exclude from the search.",
        ),
        exclude_source_domain: bool = Field(
            default=False,
            description="Whether to exclude the source domain.",
        ),
    ) -> str:
        """
        Find pages similar to a known URL.
        """

        return await exa.find_similar(
            url,
            num_results=num_results,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            exclude_source_domain=exclude_source_domain,
        )

    return [web_search_exa, web_fetch_exa, find_similar_exa]


web_search_tools: list[BaseTool] = []

__all__ = [
    "get_web_search_tools",
    "web_search_tools",
]
