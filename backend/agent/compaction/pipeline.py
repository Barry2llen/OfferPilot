from __future__ import annotations

from collections.abc import Sequence

from langchain_core.messages import BaseMessage

from schemas.config.base import Config, ContextCompactionConfig

from .budget import DefaultContextBudgetPolicy
from .layers import (
    AutoCompactLayer,
    HistoricalAttachmentCompactor,
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
from .protocols import (
    CompactionLayer,
    CompactionModelResolver,
    Compactor,
    TokenCounter,
)
from .protection import protect_entries
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


class PipelineCompactor(Compactor):
    """Deep orchestration module for a flat, temporary model context view."""

    def __init__(
        self,
        *,
        token_counter: TokenCounter,
        keep_recent_turns: int,
        layers: Sequence[CompactionLayer],
    ) -> None:
        if keep_recent_turns < 0:
            raise ValueError("keep_recent_turns must be non-negative.")
        self.token_counter = token_counter
        self.keep_recent_turns = keep_recent_turns
        self.layers = tuple(layers)

    async def acompact(self, request: CompactionRequest) -> CompactionResult:
        messages = tuple(request.runtime.state.get("messages", ()))
        entries = protect_entries(
            _identity_entries(messages),
            keep_recent_turns=self.keep_recent_turns,
        )
        context = CompactionContext(
            request=request,
            entries=entries,
            current_tokens=0,
        )
        original_tokens = await self._count(context)
        context = context.with_current_tokens(original_tokens)

        for layer in self.layers:
            before_entries = context.entries
            before_actions = len(context.actions)
            context = await layer.apply(context)
            compacted_tokens = await self._count(context)
            context = context.with_current_tokens(compacted_tokens)

            changed = (
                context.entries != before_entries
                or len(context.actions) > before_actions
            )
            if changed:
                context = context.mark_layer(layer.name)

        return CompactionResult(
            entries=context.entries,
            actions=context.actions,
            original_tokens=original_tokens,
            compacted_tokens=context.current_tokens,
            applied_layers=context.applied_layers,
            reached_target=(
                context.current_tokens <= request.budget.target_input_tokens
            ),
            warnings=context.warnings,
        )

    async def _count(self, context: CompactionContext) -> int:
        return await self.token_counter.acount(
            system_prompts=context.request.system_prompts,
            messages=context.model_messages,
            tools=context.request.tools,
        )


def build_supervisor_compactor(
    config: Config,
    *,
    model_resolver: CompactionModelResolver | None = None,
    token_counter: TokenCounter | None = None,
) -> Compactor | None:
    settings: ContextCompactionConfig = config.context_compaction
    if not settings.enabled:
        return None

    counter = token_counter if token_counter is not None else ApproximateTokenCounter()
    budget_policy = DefaultContextBudgetPolicy(settings)
    return PipelineCompactor(
        token_counter=counter,
        keep_recent_turns=settings.keep_recent_turns,
        layers=(
            ToolResultCompactor(
                max_characters=settings.tool_result_max_characters,
            ),
            HistoricalAttachmentCompactor(
                enabled=settings.compact_historical_attachments,
            ),
            AutoCompactLayer(
                model_resolver=model_resolver,
                budget_policy=budget_policy,
                token_counter=counter,
            ),
        ),
    )


__all__ = ["PipelineCompactor", "build_supervisor_compactor"]
