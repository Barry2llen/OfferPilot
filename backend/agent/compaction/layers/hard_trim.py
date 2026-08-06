from __future__ import annotations

from ..models import (
    CompactionAction,
    CompactionContext,
    ContextUnit,
)
from ..protocols import TokenCounter


class HardTrimLayer:
    name = "hard_trim"

    def __init__(self, *, token_counter: TokenCounter) -> None:
        self.token_counter = token_counter

    async def apply(self, context: CompactionContext) -> CompactionContext:
        units = list(context.units)
        actions: list[CompactionAction] = []
        reference_unit_count = sum(
            1
            for unit in units
            if any(
                entry.layer == "historical_attachments"
                for entry in unit.entries
            )
        )

        current_tokens = await self._count(context, units)
        if current_tokens <= context.request.budget.target_input_tokens:
            return context

        index = 0
        while index < len(units):
            unit = units[index]
            if unit.protected or self._is_undeletable(unit):
                index += 1
                continue
            if reference_unit_count <= 1 and self._is_attachment_reference(unit):
                index += 1
                continue

            units.pop(index)
            reference_unit_count -= int(self._is_attachment_reference(unit))
            actions.append(
                CompactionAction(
                    layer=self.name,
                    kind="drop",
                    sources=tuple(
                        source
                        for entry in unit.entries
                        for source in entry.sources
                    ),
                    reason="Removed the oldest non-protected context unit to meet the input budget.",
                )
            )
            current_tokens = await self._count(context, units)
            if current_tokens <= context.request.budget.target_input_tokens:
                break

        result = context.with_units(tuple(units)).add_actions(*actions)
        if current_tokens > context.request.budget.target_input_tokens:
            return result.add_warnings(
                "hard_trim_target_unreachable_without_dropping_protected_context"
            )
        return result

    async def _count(self, context: CompactionContext, units: list[ContextUnit]) -> int:
        messages = [entry.rendered for unit in units for entry in unit.entries]
        return await self.token_counter.acount(
            system_prompts=context.request.system_prompts,
            messages=messages,
            tools=context.request.tools,
        )

    @staticmethod
    def _is_undeletable(unit: ContextUnit) -> bool:
        return any(entry.kind == "summary" for entry in unit.entries)

    @staticmethod
    def _is_attachment_reference(unit: ContextUnit) -> bool:
        return any(entry.layer == "historical_attachments" for entry in unit.entries)


__all__ = ["HardTrimLayer"]
