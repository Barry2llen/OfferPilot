from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from .models import CompactedMessage
from utils.logger import logger


def protect_entries(
    entries: Sequence[CompactedMessage],
    *,
    keep_recent_turns: int,
) -> tuple[CompactedMessage, ...]:
    """Mark messages that deterministic and summary layers must not rewrite."""

    if keep_recent_turns < 0:
        raise ValueError("keep_recent_turns must be non-negative.")

    protected_indexes = _protected_source_indexes(
        entries,
        keep_recent_turns=keep_recent_turns,
    )
    protected_entries = tuple(
        replace(
            entry,
            protected=entry.protected
            or any(source.index in protected_indexes for source in entry.sources),
        )
        for entry in entries
    )
    logger.debug(
        "Compaction protection applied: "
        f"entries={len(entries)}, protected_source_indexes={len(protected_indexes)}, "
        f"protected_entries={sum(entry.protected for entry in protected_entries)}, "
        f"keep_recent_turns={keep_recent_turns}."
    )
    return protected_entries


def _protected_source_indexes(
    entries: Sequence[CompactedMessage],
    *,
    keep_recent_turns: int,
) -> set[int]:
    human_indexes = [
        source.index
        for entry in entries
        if isinstance(entry.rendered, HumanMessage)
        for source in entry.sources
    ]
    protected_indexes: set[int] = set()

    if not human_indexes:
        protected_indexes.update(
            source.index
            for entry in entries
            for source in entry.sources
        )
    else:
        latest_human = human_indexes[-1]
        protected_indexes.add(latest_human)
        if keep_recent_turns:
            turn_start = human_indexes[max(0, len(human_indexes) - keep_recent_turns)]
            protected_indexes.update(
                source.index
                for entry in entries
                for source in entry.sources
                if source.index >= turn_start
            )

    exchanges, consumed_tool_indexes = _tool_exchanges(entries)
    for start, end, complete in exchanges:
        if not complete or (start, end) == exchanges[-1][:2]:
            protected_indexes.update(
                source.index
                for entry in entries[start:end]
                for source in entry.sources
            )

    for index, entry in enumerate(entries):
        if isinstance(entry.rendered, ToolMessage) and index not in consumed_tool_indexes:
            protected_indexes.update(source.index for source in entry.sources)

    incomplete_or_latest_exchanges = sum(
        not complete or (start, end) == exchanges[-1][:2]
        for start, end, complete in exchanges
    )
    orphan_tool_messages = sum(
        isinstance(entry.rendered, ToolMessage)
        and index not in consumed_tool_indexes
        for index, entry in enumerate(entries)
    )
    logger.debug(
        "Compaction protection scan: "
        f"entries={len(entries)}, human_messages={len(human_indexes)}, "
        f"tool_exchanges={len(exchanges)}, "
        f"incomplete_or_latest_exchanges={incomplete_or_latest_exchanges}, "
        f"orphan_tool_messages={orphan_tool_messages}, "
        f"protected_source_indexes={len(protected_indexes)}."
    )

    return protected_indexes


def _tool_exchanges(
    entries: Sequence[CompactedMessage],
) -> tuple[list[tuple[int, int, bool]], set[int]]:
    exchanges: list[tuple[int, int, bool]] = []
    consumed_tool_indexes: set[int] = set()

    index = 0
    while index < len(entries):
        message = entries[index].rendered
        if not isinstance(message, AIMessage) or not message.tool_calls:
            index += 1
            continue

        raw_ids = [call.get("id") for call in message.tool_calls]
        ids = [str(call_id) for call_id in raw_ids if call_id]
        valid_ids = (
            len(ids) == len(raw_ids)
            and len(ids) == len(set(ids))
        )
        expected = set(ids)
        seen: set[str] = set()
        duplicate = False
        next_index = index + 1

        if valid_ids:
            while next_index < len(entries):
                next_message = entries[next_index].rendered
                if not isinstance(next_message, ToolMessage):
                    break
                tool_call_id = str(next_message.tool_call_id or "")
                if tool_call_id not in expected:
                    break
                if tool_call_id in seen:
                    duplicate = True
                seen.add(tool_call_id)
                consumed_tool_indexes.add(next_index)
                next_index += 1

        complete = valid_ids and not duplicate and seen == expected
        exchanges.append((index, next_index, complete))
        index = next_index

    return exchanges, consumed_tool_indexes


__all__ = ["protect_entries"]
