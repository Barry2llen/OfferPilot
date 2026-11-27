from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from langchain_core.messages import ToolMessage

from ..models import CompactedMessage, CompactionAction, CompactionContext

_TOOL_TRUNCATED_KEY = "_offerpilot_tool_result_truncated"
_PREFERRED_KEYS = {
    "query",
    "url",
    "title",
    "name",
    "status",
    "error",
    "message",
    "key findings",
}
_SOURCE_KEYS = (
    "source_ref",
    "file_id",
    "resource_type",
    "resource_id",
    "job_id",
    "artifact_id",
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _preview(value: Any, string_limit: int, item_limit: int, depth: int = 0) -> Any:
    if isinstance(value, str):
        return value if len(value) <= string_limit else value[:string_limit] + "…"
    if isinstance(value, dict):
        if depth >= 4:
            return "[nested fields omitted]"
        keys = sorted(
            value, key=lambda key: key.lower().replace("_", " ") not in _PREFERRED_KEYS
        )
        return {
            key: _preview(value[key], string_limit, item_limit, depth + 1)
            for key in keys[:item_limit]
        }
    if isinstance(value, list):
        if depth >= 4:
            return "[nested items omitted]"
        return [
            _preview(item, string_limit, item_limit, depth + 1)
            for item in value[:item_limit]
        ]
    return value


def _reject_non_json_constant(value: str) -> None:
    raise ValueError("Invalid JSON constant.")


def _compact_content(message: ToolMessage, content: str, limit: int) -> str | None:
    source_ref = message.additional_kwargs.get("source_ref")
    try:
        parsed = json.loads(content, parse_constant=_reject_non_json_constant)
    except (ValueError, RecursionError):
        marker = f"[Tool result truncated, status={message.status}]"
        if source_ref is not None:
            marker += f"\nSource: {_json(source_ref)}"
        if len(marker) > limit:
            return None
        preview_length = limit - len(marker) - 1
        return f"{marker}\n{content[:preview_length]}" if preview_length > 0 else marker

    if isinstance(parsed, dict):
        source_ref = parsed.get("source_ref", source_ref)
    envelope: dict[str, Any] = {"truncated": True, "tool_status": message.status}
    if source_ref is not None:
        envelope["source_ref"] = source_ref
    if isinstance(parsed, dict):
        for key in (*_SOURCE_KEYS[1:], "status"):
            if key in parsed:
                envelope[key] = parsed[key]
    if len(_json(envelope)) > limit:
        return None
    if isinstance(parsed, dict):
        if (
            "error" in parsed
            and len(_json({**envelope, "error": parsed["error"]})) <= limit
        ):
            envelope["error"] = parsed["error"]
        parsed = {key: value for key, value in parsed.items() if key not in envelope}
    for string_limit, item_limit in ((320, 8), (160, 5), (80, 3), (24, 1)):
        try:
            candidate = _json(
                {**envelope, "preview": _preview(parsed, string_limit, item_limit)}
            )
        except ValueError:
            break
        if len(candidate) <= limit:
            return candidate
    return _json(envelope)


def is_truncated_tool_result(message: ToolMessage) -> bool:
    return (
        message.additional_kwargs.get(_TOOL_TRUNCATED_KEY) is True
        or isinstance(message.content, str)
        and message.content.startswith("[Historical tool result compacted]")
    )


class ToolResultCompactor:
    name = "historical_tool_results"

    def __init__(self, *, max_characters: int = 6_000) -> None:
        if max_characters < 1:
            raise ValueError("max_characters must be positive.")
        self.max_characters = max_characters

    async def apply(self, context: CompactionContext) -> CompactionContext:
        actions: list[CompactionAction] = []
        rewritten: list[CompactedMessage] = []
        too_small = 0
        for entry in context.entries:
            message = entry.rendered
            if (
                entry.protected
                or not isinstance(message, ToolMessage)
                or not isinstance(message.content, str)
                or is_truncated_tool_result(message)
                or len(message.content) <= self.max_characters
            ):
                rewritten.append(entry)
                continue

            content = _compact_content(message, message.content, self.max_characters)
            if content is None:
                too_small += 1
                rewritten.append(entry)
                continue

            rewritten.append(
                replace(
                    entry,
                    rendered=message.model_copy(
                        update={
                            "content": content,
                            "additional_kwargs": {
                                **message.additional_kwargs,
                                _TOOL_TRUNCATED_KEY: True,
                            },
                        }
                    ),
                    kind="rewrite",
                    layer=self.name,
                )
            )
            actions.append(
                CompactionAction(
                    layer=self.name,
                    kind="rewrite",
                    sources=entry.sources,
                    reason="Shortened a completed tool result with an explicit omission notice.",
                )
            )

        result = context.with_entries(tuple(rewritten)).add_actions(*actions)
        if too_small:
            result = result.add_warnings(
                f"tool_result_limit_too_small: {too_small} results left intact."
            )
        return result
