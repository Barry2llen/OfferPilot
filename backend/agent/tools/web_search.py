
from typing import cast

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

    import re
    import json
    from exa_py import AsyncExa
    from exa_py.api import ContentsOptions, SearchResponse, Result

    exa = AsyncExa(target_config.exa_api_key)

    def _convert_search_result(result: Result) -> dict:
        """
        Convert a single search result into a dict.
        """
        
        # Remove None values and any keys that are non-primitive types with empty values to reduce noise
        # Additionally, remove 'id' and 'image' fields which are duplicative with field 'url' or useless for non-multimodal tools (just for now, can be made optional in the future)
        return {k: v for k, v in result.__dict__.items() if v is not None and k not in ("id", "image") and (isinstance(v, int|float|bool) or v)}

    def _optimize_search_response(
            target: str | list[str],
            resp: SearchResponse[Result],
            *,
            target_name: str = "query",
            index_name: str | None = None,
        ) -> str:
        """
        Convert the search response into a LLM-optimized json format.
        """

        results = [_convert_search_result(resp.results[i]) for i in range(len(resp.results))]

        if index_name:
            results = [{index_name: i+1 if index_name == "rank" else i, **result} for i, result in enumerate(results)]

        res = {
            target_name: target,
            'results': results,
        }
        
        return json.dumps(res, indent=2, ensure_ascii=False)

    # TODO: Cut down web_search tool response tokens by limiting characters per result.
    # Refer to Exa's highlights option for guidance
    @tool
    async def web_search_exa(
        query: str = Field(
            description=(
                "Precise natural-language search query. Include topic, entity, "
                "time window, location, or source preference when relevant."
            )
        ),
        num_results: int = Field(
            default=10,
            gt=1,
            lt=100,
            description=(
                "Number of search results. Use 5-10 normally; increase only for "
                "broader coverage."
            ),
        ),
        max_age_hours: int | None = Field(
            default=None,
            description=(
                "Max cache age in hours before fresh crawl. Use 0 for always "
                "fresh, -1 for cache only, or None for Exa default."
            ),
        ),
        include_domains: list[str] | None = Field(
            default=None,
            description=(
                "Optional domains to search within, such as ['sec.gov', "
                "'openai.com']."
            ),
        ),
        exclude_domains: list[str] | None = Field(
            default=None,
            description=(
                "Optional domains to exclude from results."
            ),
        ),
    ) -> str:
        """
        Search the live web with Exa for current or source-verifiable
        information. Use for discovery when the exact URL is unknown; use
        web_fetch_exa when you already have URLs to read.
        """

        contents = cast(ContentsOptions, {
            "highlights": {
                "max_characters": target_config.web_search.max_characters,
                "guiding_query": target_config.web_search.guiding_query,
            }
        })
        if max_age_hours is not None:
            contents["max_age_hours"] = max_age_hours

        response = await exa.search(
            query,
            num_results=num_results,
            type=target_config.web_search.type,
            stream=False,
            user_location="CN",
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            contents=contents,
        )
        return _optimize_search_response(query, response, target_name="query", index_name="rank")

    @tool
    async def web_fetch_exa(
        urls: list[str] = Field(
            description=(
                "Exact URLs to read, including webpages or PDF URLs from search "
                "results or user input."
            )
        ),
        livecrawl: bool = Field(
            default=False,
            description=(
                "Set true to force fresh page content. Useful for rapidly "
                "changing pages, newly found URLs, or stale search snippets."
            ),
        ),
        links: int = Field(
            default=0,
            description=(
                "Number of outgoing page links to include. Use this to discover "
                "attachment/download links; 0 reads content only, -1 includes all."
            ),
        ),
        link_regex: str | None = Field(
            default=None,
            description=(
                "Optional regex to keep matching outgoing URLs, such as "
                "'\\.pdf$' or '/download/'."
            ),
        ),
    ) -> str:
        """
        Fetch known URLs with Exa and return extracted content, metadata, and
        optional outgoing links. Use after search, when the user provides URLs,
        or to inspect PDF URLs.
        """

        kwagrs = {
            "max_age_hours": 0 if livecrawl else -1,
            "text": {
                "verbosity": "compact"
            },
            "extras": {
                "links": links if links >= 0 else 1000
            }
        }

        response = await exa.get_contents(urls, **kwagrs)

        if link_regex:
            pattern = re.compile(link_regex)
            for result in response.results:
                if result.extras:
                    searched_links: list[str] = result.extras.get("links", [])
                    filtered_links = [link for link in searched_links if pattern.search(link)]
                    result.extras = {**result.extras, "links": filtered_links}

        return _optimize_search_response(
            urls,
            response, target_name="fetch",
            index_name="index"
        )

    @tool
    async def find_similar_exa(
        url: str = Field(
            description=(
                "Known reference URL used to discover similar pages."
            )
        ),
        num_results: int | None = Field(
            gt=2,
            default=None,
            description=(
                "Number of similar pages. Leave unset for Exa's default; use "
                "5-10 when a specific amount is needed."
            ),
        ),
        include_domains: list[str] | None = Field(
            default=None,
            description=(
                "Optional list of domains to restrict similar-page discovery to."
            ),
        ),
        exclude_domains: list[str] | None = Field(
            default=None,
            description=(
                "Optional list of domains to exclude from similar-page results."
            ),
        ),
        exclude_source_domain: bool = Field(
            default=False,
            description=(
                "Exclude the reference URL's domain when independent sources or "
                "competitors are needed."
            ),
        ),
    ) -> str:
        """
        Find pages similar to a known URL with Exa. Use for related coverage,
        alternatives, competitors, or corroborating sources.
        """

        response = await exa.find_similar(
            url,
            num_results=num_results,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            exclude_source_domain=exclude_source_domain,
        )
        return _optimize_search_response(url, response, target_name="url", index_name="rank")

    return [web_search_exa, web_fetch_exa, find_similar_exa]

__all__ = [
    "get_web_search_tools",
]
