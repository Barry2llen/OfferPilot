
from pydantic import Field
from langchain_core.tools import BaseTool, tool

from schemas.config import load_config

config = load_config()

web_search_tools: list[BaseTool]
if config.exa_api_key:
    from ..mcp.web_search import web_search_mcp_tools
    web_search_tools = web_search_mcp_tools
else:

    from exa_py import AsyncExa
    exa = AsyncExa(config.exa_api_key)

    @tool
    async def web_search(
        query: str = Field(description="Natural language search query. Should be a semantically rich description of the ideal page, not just keywords."),
        num_results: int = Field(default=10, gt=1, lt=100, description="The number of search results to return"),
        include_domains: list[str] = Field(default=None, description="Domains to include in the search."),
        exclude_domains: list[str] = Field(default=None, description="Domains to exclude from the search."),
        # start_published_date: str = Field(default=None, description="Optional ISO 8601 date string to only include results published after this date.Example: '2026-04-11T16:00:00.000Z'"),
        # end_published_date: str = Field(default=None, description="Optional ISO 8601 date string to only include results published before this date."),
    ) -> str:
        """
        Search the web for any topic and get clean, ready-to-use content. 
        Best for: Finding current information, news, facts, people, companies, or answering questions about any topic. 
        Returns: Clean text content from top search results. 
        Query tips: describe the ideal page, not keywords. "blog post comparing React and Vue performance" not "React vs Vue".
        If highlights are insufficient, follow up with web_fetch_exa on the best URLs.
        """

        return await exa.search(
            query,
            num_results = num_results,
            type = "auto",
            stream = False,
            user_location = "CN",
            include_domains = include_domains,
            exclude_domains = exclude_domains,
            # start_published_date = start_published_date,
            # end_published_date = end_published_date,
            contents = {
                "highlights": {
                    "max_characters": config.web_search.max_characters,
                    "guiding_query": config.web_search.guiding_query,
                }
            }
        )

    @tool
    async def web_fetch(
        urls: list[str] = Field(description="The list of URLs to fetch content from"),
    ) -> str:
        """
        Read a webpage's full content as clean markdown. 
        Use after web_search_exa when highlights are insufficient or to read any URL. 
        Best for: Extracting full content from known URLs. Batch multiple URLs in one call. 
        Returns: Clean text content and metadata from the page(s).
        """
        return await exa.get_contents(urls)
    
    @tool
    async def find_similar(
        url: str = Field(description="The URL to find similar pages for."),
        num_results: int = Field(default=None, description="Number of results to return. Default is None (server default)."),
        include_domains: list[str] = Field(default=None, description="Domains to include in the search."),
        exclude_domains: list[str] = Field(default=None, description="Domains to exclude from the search."),
        exclude_source_domain: bool = Field(default=False, description="Whether to exclude the source domain.")
    ) -> str:
        
        return await exa.find_similar(
            url,
            num_results = num_results,
            include_domains = include_domains,
            exclude_domains = exclude_domains,
            exclude_source_domain = exclude_source_domain
        )

    web_search_tools = [web_search, web_fetch, find_similar]

__all__ = [
    web_search_tools
]