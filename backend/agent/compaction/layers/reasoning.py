from __future__ import annotations

from langchain_core.messages import AIMessage

from ..models import CompactedMessage, CompactionAction, CompactionContext


class HistoricalReasoningPruner:
    name = "historical_reasoning"

    def __init__(self, *, keep_recent_reasoning_messages: int = 1) -> None:
        if keep_recent_reasoning_messages < 0:
            raise ValueError("keep_recent_reasoning_messages must be non-negative.")
        self.keep_recent_reasoning_messages = keep_recent_reasoning_messages

    async def apply(self, context: CompactionContext) -> CompactionContext:
        reasoning_entries = [
            entry
            for entry in context.entries
            if isinstance(entry.rendered, AIMessage)
            and self._has_reasoning(entry.rendered)
        ]
        keep_sources = {
            source
            for entry in reasoning_entries[-self.keep_recent_reasoning_messages :]
            for source in entry.sources
        } if self.keep_recent_reasoning_messages else set()

        actions: list[CompactionAction] = []

        def rewrite(entry: CompactedMessage) -> CompactedMessage:
            message = entry.rendered
            if not isinstance(message, AIMessage) or not self._has_reasoning(message):
                return entry
            if any(source in keep_sources for source in entry.sources):
                return entry

            additional_kwargs = dict(message.additional_kwargs)
            additional_kwargs.pop("reasoning_content", None)
            additional_kwargs.pop("reasoning_duration_ms", None)
            rewritten = message.model_copy(
                update={"additional_kwargs": additional_kwargs}
            )
            actions.append(
                CompactionAction(
                    layer=self.name,
                    kind="rewrite",
                    sources=entry.sources,
                    reason="Removed historical reasoning metadata while preserving the AI response.",
                )
            )
            return CompactedMessage(
                rendered=rewritten,
                sources=entry.sources,
                kind="rewrite",
                layer=self.name,
            )

        return context.map_entries(rewrite).add_actions(*actions)

    @staticmethod
    def _has_reasoning(message: AIMessage) -> bool:
        reasoning_content = message.additional_kwargs.get("reasoning_content")
        return isinstance(reasoning_content, str) and bool(reasoning_content.strip())


__all__ = ["HistoricalReasoningPruner"]
