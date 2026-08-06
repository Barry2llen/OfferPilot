from __future__ import annotations

from collections.abc import Sequence

from langchain_core.messages import BaseMessage

from schemas.config.base import Config, ContextCompactionConfig

from .budget import DefaultContextBudgetPolicy
from .grouping import ContextGrouper
from .layers import (
    HardTrimLayer,
    HistoricalAttachmentCompactor,
    HistoricalReasoningPruner,
    ToolResultCompactor,
)
from .models import (
    CompactedMessage,
    CompactionAction,
    CompactionContext,
    CompactionRequest,
    CompactionResult,
    MessageRef,
)
from .protocols import CompactionLayer, Compactor, TokenCounter
from .token_counter import ApproximateTokenCounter


def _message_ref(index: int, message: BaseMessage) -> MessageRef:
    message_id = getattr(message, "id", None)
    return MessageRef(
        index=index,
        message_id=message_id if isinstance(message_id, str) else None,
    )


def _identity_entries(messages: Sequence[BaseMessage]) -> tuple[CompactedMessage, ...]:
    return tuple(
        CompactedMessage(
            rendered=message,
            sources=(_message_ref(index, message),),
            kind="identity",
            layer="identity",
        )
        for index, message in enumerate(messages)
    )


def _identity_actions(
    entries: Sequence[CompactedMessage],
) -> tuple[CompactionAction, ...]:
    return tuple(
        CompactionAction(
            layer="identity",
            kind="keep",
            sources=entry.sources,
            reason="Preserved the original message in the model view.",
        )
        for entry in entries
    )


class IdentityCompactor(Compactor):
    def __init__(self, *, token_counter: TokenCounter | None = None) -> None:
        self.token_counter = (
            token_counter
            if token_counter is not None
            else ApproximateTokenCounter()
        )

    async def acompact(self, request: CompactionRequest) -> CompactionResult:
        entries = _identity_entries(request.messages)
        tokens = await self.token_counter.acount(
            system_prompts=request.system_prompts,
            messages=[entry.rendered for entry in entries],
            tools=request.tools,
        )
        return CompactionResult(
            entries=entries,
            actions=_identity_actions(entries),
            original_tokens=tokens,
            compacted_tokens=tokens,
            applied_layers=(),
            reached_target=tokens <= request.budget.target_input_tokens,
        )


class PipelineCompactor(Compactor):
    """Run deterministic compaction layers over deletion-safe context units."""

    def __init__(
        self,
        *,
        token_counter: TokenCounter,
        grouper: ContextGrouper,
        layers: Sequence[CompactionLayer],
    ) -> None:
        self.token_counter = token_counter
        self.grouper = grouper
        self.layers = tuple(layers)

    async def acompact(self, request: CompactionRequest) -> CompactionResult:
        entries = _identity_entries(request.messages)
        context = CompactionContext(
            request=request,
            units=self.grouper.group(entries),
            actions=_identity_actions(entries),
        )
        original_tokens = await self._count(context)

        if original_tokens <= request.budget.trigger_input_tokens:
            return self._result(
                context,
                original_tokens=original_tokens,
                compacted_tokens=original_tokens,
            )

        compacted_tokens = original_tokens
        for layer in self.layers:
            context = await layer.apply(context)
            context = context.mark_layer(layer.name)
            compacted_tokens = await self._count(context)
            if compacted_tokens <= request.budget.target_input_tokens:
                break

        return self._result(
            context,
            original_tokens=original_tokens,
            compacted_tokens=compacted_tokens,
        )

    async def _count(self, context: CompactionContext) -> int:
        return await self.token_counter.acount(
            system_prompts=context.request.system_prompts,
            messages=context.model_messages,
            tools=context.request.tools,
        )

    @staticmethod
    def _result(
        context: CompactionContext,
        *,
        original_tokens: int,
        compacted_tokens: int,
    ) -> CompactionResult:
        return CompactionResult(
            entries=context.entries,
            actions=context.actions,
            original_tokens=original_tokens,
            compacted_tokens=compacted_tokens,
            applied_layers=context.applied_layers,
            reached_target=compacted_tokens <= context.request.budget.target_input_tokens,
            warnings=context.warnings,
        )


def build_default_compactor(config: Config) -> Compactor:
    settings: ContextCompactionConfig = config.context_compaction
    token_counter = ApproximateTokenCounter()
    if not settings.enabled:
        return IdentityCompactor(token_counter=token_counter)

    return PipelineCompactor(
        token_counter=token_counter,
        grouper=ContextGrouper(keep_recent_turns=settings.keep_recent_turns),
        layers=(
            HistoricalReasoningPruner(
                keep_recent_reasoning_messages=settings.keep_recent_reasoning_messages
            ),
            ToolResultCompactor(
                max_characters=settings.tool_result_max_characters,
            ),
            HistoricalAttachmentCompactor(
                enabled=settings.compact_historical_attachments,
            ),
            HardTrimLayer(token_counter=token_counter),
        ),
    )


__all__ = [
    "IdentityCompactor",
    "PipelineCompactor",
    "build_default_compactor",
]
