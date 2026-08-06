from __future__ import annotations

from dataclasses import replace
from collections.abc import Sequence

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from .models import (
    CompactedMessage,
    ContextUnit,
    SingleMessageUnit,
    ToolExchangeUnit,
)


class ContextGrouper:
    """Turn a message view into deletion-safe conversation units."""

    def __init__(self, *, keep_recent_turns: int = 4) -> None:
        if keep_recent_turns < 0:
            raise ValueError("keep_recent_turns must be non-negative.")
        self.keep_recent_turns = keep_recent_turns

    def group(self, entries: Sequence[CompactedMessage]) -> tuple[ContextUnit, ...]:
        raw_units: list[ContextUnit] = []
        index = 0
        while index < len(entries):
            message = entries[index].rendered
            if isinstance(message, AIMessage) and message.tool_calls:
                unit, next_index = self._group_tool_exchange(entries, index)
                raw_units.append(unit)
                index = next_index
                continue

            # A ToolMessage without a safely identifiable preceding call cannot be
            # deleted without risking an invalid provider request.
            raw_units.append(
                SingleMessageUnit(
                    entries=(entries[index],),
                    protected=isinstance(message, ToolMessage),
                )
            )
            index += 1

        return self._apply_protection(tuple(raw_units))

    def _group_tool_exchange(
        self,
        entries: Sequence[CompactedMessage],
        start: int,
    ) -> tuple[ToolExchangeUnit, int]:
        message = entries[start].rendered
        assert isinstance(message, AIMessage)

        raw_ids = [call.get("id") for call in message.tool_calls]
        tool_call_ids = tuple(str(call_id) for call_id in raw_ids if call_id)
        valid_ids = (
            len(tool_call_ids) == len(raw_ids)
            and len(set(tool_call_ids)) == len(tool_call_ids)
        )

        exchange_entries = [entries[start]]
        seen_ids: set[str] = set()
        next_index = start + 1

        if valid_ids:
            expected_ids = set(tool_call_ids)
            while next_index < len(entries):
                next_message = entries[next_index].rendered
                if not isinstance(next_message, ToolMessage):
                    break
                tool_call_id = str(next_message.tool_call_id or "")
                if tool_call_id not in expected_ids:
                    break
                exchange_entries.append(entries[next_index])
                seen_ids.add(tool_call_id)
                next_index += 1

        complete = valid_ids and seen_ids == set(tool_call_ids)
        return (
            ToolExchangeUnit(
                entries=tuple(exchange_entries),
                tool_call_ids=tool_call_ids,
                complete=complete,
                protected=not complete,
            ),
            next_index,
        )

    def _apply_protection(self, units: tuple[ContextUnit, ...]) -> tuple[ContextUnit, ...]:
        human_indexes = [
            source.index
            for unit in units
            for entry in unit.entries
            if isinstance(entry.rendered, HumanMessage)
            for source in entry.sources
        ]
        protected_indexes: set[int] = set()

        if human_indexes:
            protected_indexes.add(human_indexes[-1])
            if self.keep_recent_turns:
                turn_start = human_indexes[max(0, len(human_indexes) - self.keep_recent_turns)]
                protected_indexes.update(
                    source.index
                    for unit in units
                    for entry in unit.entries
                    for source in entry.sources
                    if source.index >= turn_start
                )
        else:
            # Without a HumanMessage boundary the structure is not safe to infer.
            protected_indexes.update(
                source.index
                for unit in units
                for entry in unit.entries
                for source in entry.sources
            )

        tool_units = [unit for unit in units if isinstance(unit, ToolExchangeUnit)]
        if tool_units:
            protected_indexes.update(
                source.index
                for entry in tool_units[-1].entries
                for source in entry.sources
            )

        for unit in reversed(units):
            if any(
                isinstance(entry.rendered, ToolMessage)
                and bool(entry.rendered.additional_kwargs.get("return_direct"))
                for entry in unit.entries
            ):
                protected_indexes.update(
                    source.index
                    for entry in unit.entries
                    for source in entry.sources
                )
                break

        protected_units: list[ContextUnit] = []
        for unit in units:
            is_protected = unit.protected or any(
                source.index in protected_indexes
                for entry in unit.entries
                for source in entry.sources
            )
            protected_units.append(replace(unit, protected=is_protected))
        return tuple(protected_units)


__all__ = ["ContextGrouper"]
