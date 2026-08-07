from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from langchain_core.messages import ToolMessage

from ..models import CompactedMessage, CompactionAction, CompactionContext
from utils.logger import logger


_PREFERRED_KEYS = (
    "query",
    "url",
    "title",
    "name",
    "status",
    "error",
    "message",
    "key findings",
    "key_findings",
)


def _shorten_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    if limit <= 12:
        return value[: max(1, limit)]
    omitted = len(value) - limit
    marker = f"...[omitted {omitted} characters]..."
    if len(marker) >= limit:
        return value[:limit]
    remaining = limit - len(marker)
    head = max(1, round(remaining * 0.62))
    tail = max(1, remaining - head)
    return f"{value[:head]}{marker}{value[-tail:]}"


def _compact_json_value(
    value: Any,
    *,
    string_limit: int = 320,
    array_limit: int = 5,
) -> Any:
    if isinstance(value, str):
        return _shorten_text(value, string_limit)
    if isinstance(value, list):
        compacted = [
            _compact_json_value(item, string_limit=string_limit, array_limit=array_limit)
            for item in value[:array_limit]
        ]
        omitted = len(value) - len(compacted)
        if omitted > 0:
            compacted.append({"_omitted_items": omitted})
        return compacted
    if isinstance(value, dict):
        preferred: list[tuple[str, Any]] = []
        remaining: list[tuple[str, Any]] = []
        normalized_preferred = {key.lower().replace("_", " ") for key in _PREFERRED_KEYS}
        for key, item in value.items():
            target = (
                preferred
                if str(key).lower().replace("_", " ") in normalized_preferred
                else remaining
            )
            target.append((str(key), item))

        selected = [*preferred, *remaining[:4]]
        result = {
            key: _compact_json_value(
                item,
                string_limit=string_limit,
                array_limit=array_limit,
            )
            for key, item in selected
        }
        omitted = len(value) - len(selected)
        if omitted > 0:
            result["_omitted_keys"] = omitted
        return result
    if isinstance(value, tuple):
        return _compact_json_value(
            list(value),
            string_limit=string_limit,
            array_limit=array_limit,
        )
    return value


def _compact_json_content(content: str, max_characters: int) -> str | None:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None

    for string_limit, array_limit in (
        (320, 5),
        (160, 3),
        (80, 2),
        (32, 1),
    ):
        compacted = _compact_json_value(
            parsed,
            string_limit=string_limit,
            array_limit=array_limit,
        )
        rendered = json.dumps(
            compacted,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if len(rendered) < len(content) and len(rendered) <= max_characters:
            return rendered

    for fallback in ("0", "null", "false", "{}", "[]"):
        if len(fallback) < len(content) and len(fallback) <= max_characters:
            return fallback
    return None


def _content_as_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_blocks = [
            str(block.get("text"))
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        ]
        if text_blocks:
            return "\n".join(text_blocks)
    if isinstance(content, Mapping):
        return json.dumps(content, ensure_ascii=False, sort_keys=True, default=str)
    return str(content)


def _compact_text_content(content: str, *, tool_name: str, max_characters: int) -> str:
    header = (
        "[Historical tool result compacted]\n"
        f"Tool: {tool_name}\n"
        f"Original characters: {len(content)}\n\n"
    )
    footer_template = "\n\n...[omitted {omitted} characters]...\n\n"
    available = max_characters - len(header) - len(footer_template.format(omitted=0))
    if available > 2:
        head_limit = max(1, round(available * 0.62))
        tail_limit = max(1, available - head_limit)
        for _ in range(3):
            omitted = max(0, len(content) - head_limit - tail_limit)
            suffix = footer_template.format(omitted=omitted)
            content_budget = max_characters - len(header) - len(suffix)
            if content_budget <= 2:
                break
            head_limit = max(1, round(content_budget * 0.62))
            tail_limit = max(1, content_budget - head_limit)
        omitted = max(0, len(content) - head_limit - tail_limit)
        suffix = footer_template.format(omitted=omitted)
        candidate = f"{header}{content[:head_limit]}{suffix}{content[-tail_limit:]}"
        if len(candidate) > max_characters:
            candidate = candidate[:max_characters]
    else:
        candidate = "[Historical tool result compacted]"[:max_characters]

    if len(candidate) < len(content):
        return candidate
    return "[Historical tool result compacted]"[:max_characters]


class ToolResultCompactor:
    name = "historical_tool_results"

    def __init__(self, *, max_characters: int = 6_000) -> None:
        if max_characters < 1:
            raise ValueError("max_characters must be positive.")
        self.max_characters = max_characters

    async def apply(self, context: CompactionContext) -> CompactionContext:
        actions: list[CompactionAction] = []
        rewritten_entries: list[CompactedMessage] = []
        tool_entries = 0
        protected_skips = 0
        already_compacted_skips = 0
        within_limit_skips = 0
        no_reduction_skips = 0

        logger.debug(
            lambda: (
                "Tool result compaction started: "
                f"entries={len(context.entries)}, max_characters={self.max_characters}."
            )
        )

        for entry in context.entries:
            message = entry.rendered
            if not isinstance(message, ToolMessage):
                rewritten_entries.append(entry)
                continue
            tool_entries += 1
            if entry.protected:
                protected_skips += 1
                rewritten_entries.append(entry)
                continue

            content = _content_as_text(message.content)
            if content.startswith("[Historical tool result compacted]"):
                already_compacted_skips += 1
                rewritten_entries.append(entry)
                continue
            if len(content) <= self.max_characters:
                within_limit_skips += 1
                rewritten_entries.append(entry)
                continue

            compacted_json = _compact_json_content(content, self.max_characters)
            compacted_mode = "json" if compacted_json is not None else "text"
            compacted = compacted_json or _compact_text_content(
                content,
                tool_name=str(message.name or "unknown"),
                max_characters=self.max_characters,
            )
            if len(compacted) >= len(content):
                no_reduction_skips += 1
                rewritten_entries.append(entry)
                continue

            rewritten_entries.append(
                CompactedMessage(
                    rendered=message.model_copy(update={"content": compacted}),
                    sources=entry.sources,
                    kind="rewrite",
                    layer=self.name,
                    protected=entry.protected,
                )
            )
            actions.append(
                CompactionAction(
                    layer=self.name,
                    kind="rewrite",
                    sources=entry.sources,
                    reason=(
                        "Compacted an old tool result without changing its tool-call identity."
                    ),
                )
            )
            logger.debug(
                lambda: (
                    "Tool result compacted: "
                    f"source_indexes={[source.index for source in entry.sources]}, "
                    f"mode={compacted_mode}, original_characters={len(content)}, "
                    f"compacted_characters={len(compacted)}."
                )
            )

        logger.debug(
            lambda: (
                "Tool result compaction finished: "
                f"tool_entries={tool_entries}, rewritten={len(actions)}, "
                f"protected_skips={protected_skips}, "
                f"already_compacted_skips={already_compacted_skips}, "
                f"within_limit_skips={within_limit_skips}, "
                f"no_reduction_skips={no_reduction_skips}."
            )
        )
        return context.with_entries(tuple(rewritten_entries)).add_actions(*actions)


__all__ = ["ToolResultCompactor"]
