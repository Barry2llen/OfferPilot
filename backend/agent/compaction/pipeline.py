from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from langchain_core.messages import BaseMessage, SystemMessage

from schemas.config.base import Config, ContextCompactionConfig

from .budget import DefaultContextBudgetPolicy
from .layers import (
    AutoCompactLayer,
    HistoricalAttachmentCompactor,
    ToolResultCompactor,
)
from ..base import ContextCompactionSnapshot, ContextCompactionStatus
from .errors import ContextCompactionError
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


def _message_id(message: BaseMessage) -> str | None:
    value = getattr(message, "id", None)
    return value if isinstance(value, str) else None


def _identity_entries(
    messages: Sequence[BaseMessage],
    *,
    start_index: int = 0,
) -> tuple[CompactedMessage, ...]:
    return tuple(
        CompactedMessage(
            rendered=message,
            sources=(_message_ref(start_index + index, message),),
            kind="identity",
            layer="identity",
        )
        for index, message in enumerate(messages)
    )


def _is_summary_message(message: BaseMessage) -> bool:
    if not isinstance(message, SystemMessage):
        return False

    additional_kwargs = getattr(message, "additional_kwargs", {})
    if isinstance(additional_kwargs, Mapping):
        if additional_kwargs.get("_offerpilot_context_compaction") == "summary":
            return True
    return isinstance(message.content, str) and message.content.startswith(
        "[Historical context summary]"
    )


def _read_snapshot(
    state: Mapping[str, Any],
    messages: Sequence[BaseMessage],
) -> ContextCompactionSnapshot | None:
    raw_snapshot = state.get("context_compaction")
    if not isinstance(raw_snapshot, Mapping):
        return None

    snapshot_messages = raw_snapshot.get("messages")
    source_count = raw_snapshot.get("source_message_count")
    source_ids = raw_snapshot.get("source_message_ids")
    status = raw_snapshot.get("status")
    auto_compacted = raw_snapshot.get("auto_compacted")
    if (
        not isinstance(snapshot_messages, list)
        or not all(isinstance(message, BaseMessage) for message in snapshot_messages)
        or isinstance(source_count, bool)
        or not isinstance(source_count, int)
        or source_count < 0
        or source_count > len(messages)
        or not isinstance(source_ids, list)
        or len(source_ids) != source_count
        or any(item is not None and not isinstance(item, str) for item in source_ids)
        or status not in {"complete", "pending_auto_compact"}
        or not isinstance(auto_compacted, bool)
    ):
        return None

    for index, expected_id in enumerate(source_ids):
        if expected_id is not None and _message_id(messages[index]) != expected_id:
            return None

    return cast(
        ContextCompactionSnapshot,
        {
            "messages": list(snapshot_messages),
            "source_message_count": source_count,
            "source_message_ids": list(source_ids),
            "status": status,
            "auto_compacted": auto_compacted,
        },
    )


def _snapshot_entries(
    snapshot: ContextCompactionSnapshot,
) -> tuple[CompactedMessage, ...]:
    entries: list[CompactedMessage] = []
    for index, message in enumerate(snapshot["messages"]):
        is_summary = _is_summary_message(message)
        entries.append(
            CompactedMessage(
                rendered=message,
                sources=(
                    MessageRef(
                        index=index,
                        message_id=_message_id(message),
                    ),
                ),
                kind="summary" if is_summary else "identity",
                layer="persisted_snapshot",
                protected=is_summary,
            )
        )
    return tuple(entries)


def model_messages_for_state(state: Mapping[str, Any]) -> list[BaseMessage]:
    """Build the reusable model view without mutating the raw graph messages."""

    messages = state.get("messages", ())
    if not isinstance(messages, Sequence):
        return []
    raw_messages = tuple(message for message in messages if isinstance(message, BaseMessage))
    snapshot = _read_snapshot(state, raw_messages)
    if snapshot is None:
        return list(raw_messages)
    return [
        *snapshot["messages"],
        *raw_messages[snapshot["source_message_count"] :],
    ]


class PipelineCompactor(Compactor):
    """Deep orchestration module for a persisted, reusable model context view."""

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
        raw_messages = tuple(
            message
            for message in request.runtime.state.get("messages", ())
            if isinstance(message, BaseMessage)
        )
        snapshot = _read_snapshot(request.runtime.state, raw_messages)
        if snapshot is None:
            entries = _identity_entries(raw_messages)
        else:
            entries = (
                *_snapshot_entries(snapshot),
                *_identity_entries(
                    raw_messages[snapshot["source_message_count"] :],
                    start_index=len(snapshot["messages"]),
                ),
            )
        entries = protect_entries(entries, keep_recent_turns=self.keep_recent_turns)
        context = CompactionContext(
            request=request,
            entries=entries,
            current_tokens=0,
            raw_message_count=len(raw_messages),
            snapshot=snapshot,
        )
        try:
            original_tokens = await self._count(context)
        except Exception as error:
            raise ContextCompactionError(
                f"Initial context token counting failed: {error}"
            ) from error
        context = context.with_current_tokens(original_tokens)

        for layer in self.layers:
            before_entries = context.entries
            before_actions = len(context.actions)
            try:
                context = await layer.apply(context)
                compacted_tokens = await self._count(context)
            except ContextCompactionError as error:
                partial = self._result(
                    context,
                    original_tokens=original_tokens,
                    raw_messages=raw_messages,
                    snapshot_status="pending_auto_compact",
                    force_persist=True,
                )
                raise error.with_partial_result(partial) from error
            except Exception as error:
                partial = self._result(
                    context,
                    original_tokens=original_tokens,
                    raw_messages=raw_messages,
                    snapshot_status="pending_auto_compact",
                    force_persist=True,
                )
                raise ContextCompactionError(
                    f"Compaction layer {layer.name} failed: {error}",
                    partial_result=partial,
                ) from error
            context = context.with_current_tokens(compacted_tokens)

            changed = (
                context.entries != before_entries
                or len(context.actions) > before_actions
            )
            if changed:
                context = context.mark_layer(layer.name)

        if context.current_tokens > request.budget.available_input_tokens:
            partial = self._result(
                context,
                original_tokens=original_tokens,
                raw_messages=raw_messages,
                snapshot_status="pending_auto_compact",
                force_persist=True,
            )
            raise ContextCompactionError(
                "Compaction produced a model context above the configured "
                "available input capacity.",
                partial_result=partial,
            )

        return self._result(
            context,
            original_tokens=original_tokens,
            raw_messages=raw_messages,
            snapshot_status="complete",
        )

    @staticmethod
    def _message_ids(messages: Sequence[BaseMessage]) -> tuple[str | None, ...]:
        return tuple(_message_id(message) for message in messages)

    def _result(
        self,
        context: CompactionContext,
        *,
        original_tokens: int,
        raw_messages: Sequence[BaseMessage],
        snapshot_status: ContextCompactionStatus,
        force_persist: bool = False,
    ) -> CompactionResult:
        auto_compacted_this_run = any(
            action.layer == "auto_compact" and action.kind == "summarize"
            for action in context.actions
        )
        auto_compacted = bool(
            context.snapshot and context.snapshot.get("auto_compacted")
        ) or auto_compacted_this_run
        return CompactionResult(
            entries=context.entries,
            actions=context.actions,
            original_tokens=original_tokens,
            compacted_tokens=context.current_tokens,
            applied_layers=context.applied_layers,
            reached_target=(
                context.current_tokens <= context.request.budget.target_input_tokens
            ),
            warnings=context.warnings,
            source_message_count=len(raw_messages),
            source_message_ids=self._message_ids(raw_messages),
            snapshot_status=snapshot_status,
            auto_compacted=auto_compacted,
            auto_compacted_this_run=auto_compacted_this_run,
            should_persist_snapshot=(
                force_persist
                or bool(context.applied_layers)
                or bool(
                    context.snapshot
                    and context.snapshot["status"] == "pending_auto_compact"
                )
            ),
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


__all__ = [
    "PipelineCompactor",
    "build_supervisor_compactor",
    "model_messages_for_state",
]
