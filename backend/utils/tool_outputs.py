import json
import re
from typing import Any

from langchain_core.messages import BaseMessage


SEARCH_RESULT_TOOL_NAMES = {
    "web_search",
    "web_search_exa",
    "find_similar_exa",
    "web_fetch",
    "web_fetch_exa",
}
SEARCH_RESULTS_EMPTY_MESSAGE = "未提取到可展示的搜索链接"

_SEARCH_RESULT_FRONTEND_FIELDS = ("url", "title", "favicon")
_SEARCH_RESULT_TEXT_FIELD_MAP = {
    "URL": "url",
    "Title": "title",
    "Favicon": "favicon",
}
_REPR_FIELD_PATTERN = re.compile(
    r"(?P<key>url|title|favicon)=['\"](?P<value>[^'\"]+)['\"]",
    re.IGNORECASE,
)


def summarize_tool_output(tool_name: str, output: Any) -> Any:
    if tool_name not in SEARCH_RESULT_TOOL_NAMES:
        return output

    summaries = summarize_search_tool_output(output)
    return summaries if summaries else {"message": SEARCH_RESULTS_EMPTY_MESSAGE}


def summarize_search_tool_output(output: Any) -> list[dict[str, Any]]:
    results = _extract_search_results(output)
    if results is None:
        return []

    summaries: list[dict[str, Any]] = []
    for result in results:
        summary = {
            field: _get_field_value(result, field)
            for field in _SEARCH_RESULT_FRONTEND_FIELDS
        }
        clean_summary = {
            field: value
            for field, value in summary.items()
            if value is not None
        }
        if "url" in clean_summary:
            summaries.append(clean_summary)
    return summaries


def _get_field_value(value: Any, field: str) -> Any:
    if isinstance(value, dict):
        return value.get(field)
    return getattr(value, field, None)


def _extract_text_blocks(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return text
        content = value.get("content")
        if content is not None:
            return _extract_text_blocks(content)
        return ""
    if isinstance(value, list | tuple):
        return "\n\n".join(
            text for item in value if (text := _extract_text_blocks(item))
        )
    return ""


def _has_url_field(value: Any) -> bool:
    return _get_field_value(value, "url") is not None


def _extract_search_results(output: Any) -> list[Any] | None:
    if isinstance(output, BaseMessage):
        output = output.content

    if isinstance(output, str):
        try:
            output = json.loads(output)
        except json.JSONDecodeError:
            parsed_results = _parse_search_result_text(output)
            return parsed_results if parsed_results else None

    if isinstance(output, dict):
        if _has_url_field(output):
            return [output]
        results = output.get("results")
        if not isinstance(results, list | tuple):
            parsed_results = _parse_search_result_text(_extract_text_blocks(output))
            return parsed_results if parsed_results else None
    elif isinstance(output, list | tuple):
        if any(_has_url_field(item) for item in output):
            results = output
        else:
            parsed_results = _parse_search_result_text(_extract_text_blocks(output))
            return parsed_results if parsed_results else None
    else:
        results = getattr(output, "results", None)

    return list(results) if isinstance(results, list | tuple) else None


def _parse_search_result_text(output: str) -> list[dict[str, str]]:
    colon_results = _parse_colon_search_result_text(output)
    if colon_results:
        return colon_results
    return _parse_repr_search_result_text(output)


def _parse_colon_search_result_text(output: str) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for block in output.split("\n\n"):
        result: dict[str, str] = {}
        for line in block.splitlines():
            key, separator, value = line.partition(":")
            if not separator:
                continue

            field = _SEARCH_RESULT_TEXT_FIELD_MAP.get(key.strip())
            if field is None:
                continue

            cleaned_value = value.strip()
            if cleaned_value and cleaned_value != "None":
                result[field] = cleaned_value

        if "url" in result:
            results.append(result)

    return results


def _parse_repr_search_result_text(output: str) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for block in re.split(r"(?=SearchResult\(|Result\()", output):
        result = {
            match.group("key").lower(): match.group("value")
            for match in _REPR_FIELD_PATTERN.finditer(block)
            if match.group("value") != "None"
        }
        if "url" in result:
            results.append(
                {
                    key: value
                    for key, value in result.items()
                    if key in _SEARCH_RESULT_FRONTEND_FIELDS
                }
            )
    return results


__all__ = [
    "SEARCH_RESULT_TOOL_NAMES",
    "SEARCH_RESULTS_EMPTY_MESSAGE",
    "summarize_search_tool_output",
    "summarize_tool_output",
]
