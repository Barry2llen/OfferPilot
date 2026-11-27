from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from schemas.config.base import Config, ContextCompactionConfig
from utils.chat_attachment_content import attachment_content
from utils.custom_events import _adispatch_custom_event_safely
from utils.logger import logger

from ..base import ContextCompactionSnapshot, ContextCompactionStatus
from .budget import DefaultContextBudgetPolicy
from .errors import ContextCompactionError
from .layers import (
    AutoCompactLayer,
    HistoricalAttachmentCompactor,
    ToolResultCompactor,
)
from .models import (
    CompactedMessage,
    CompactionContext,
    CompactionRequest,
    CompactionResult,
    MessageRef,
)
from .protection import has_indispensable_payload, message_groups, protect_entries
from .protocols import (
    CompactionLayer,
    CompactionModelResolver,
    Compactor,
    TokenCounter,
)
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
        logger.debug(
            lambda: "Compaction snapshot ignored: persisted sidecar failed validation."
        )
        return None

    for index, expected_id in enumerate(source_ids):
        if expected_id is not None and _message_id(messages[index]) != expected_id:
            logger.debug(
                lambda: (
                    "Compaction snapshot ignored: source message identity mismatch "
                    f"at index={index}."
                )
            )
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
    snapshot: ContextCompactionSnapshot, raw_messages: Sequence[BaseMessage]
) -> tuple[CompactedMessage, ...]:
    raw_indexes = {
        message.id: index
        for index, message in enumerate(raw_messages)
        if message.id is not None
    }
    entries = []
    for view_index, message in enumerate(snapshot["messages"]):
        raw_index = raw_indexes.get(message.id) if message.id is not None else None
        is_summary = raw_index is None and _is_summary_message(message)
        if is_summary and message in raw_messages:
            # A real user can type the same prefix as a legacy summary.
            is_summary = False
        entries.append(
            CompactedMessage(
                rendered=message,
                sources=()
                if is_summary
                else (
                    _message_ref(
                        raw_index if raw_index is not None else view_index, message
                    ),
                ),
                kind="summary" if is_summary else "identity",
                layer="persisted_snapshot",
                protected=is_summary,
            )
        )
    return tuple(entries)


def _snapshot_preserves_required_content(
    snapshot: ContextCompactionSnapshot, raw_messages: Sequence[BaseMessage]
) -> bool:
    """Check legacy views for evidence older compaction layers could discard."""
    prefix_count = snapshot["source_message_count"]
    view = (*snapshot["messages"], *raw_messages[prefix_count:])
    by_id = {message.id: message for message in view if message.id is not None}
    current = next(
        (
            message
            for message in reversed(raw_messages)
            if isinstance(message, HumanMessage)
        ),
        None,
    )
    payloads: dict[tuple[str, str], list[list[str | dict]]] | None = None

    for raw in raw_messages[:prefix_count]:
        saved = by_id.get(raw.id) if raw.id is not None else None
        if isinstance(raw, ToolMessage) and isinstance(saved, ToolMessage):
            if (
                isinstance(saved.content, str)
                and saved.content in {"0", "null", "false", "{}", "[]"}
                and raw.content != saved.content
            ):
                return False
        if raw is not current and not (
            isinstance(raw, SystemMessage) or has_indispensable_payload(raw)
        ):
            continue
        if saved == raw or (raw.id is None and raw in view):
            continue
        layout = attachment_content(raw) if isinstance(raw, HumanMessage) else None
        if layout is None:
            return False
        if saved is not None or raw is current:
            saved_layout = (
                attachment_content(saved) if isinstance(saved, HumanMessage) else None
            )
            if (
                saved_layout is None
                or saved_layout.prompt != layout.prompt
                or saved_layout.visible_block != layout.visible_block
            ):
                return False
        # A historical message may be summarized after deduplication only if
        # every original payload still has an exact copy in the view.
        if not layout.spans:
            continue
        if payloads is None:
            payloads = {}
            for candidate in view:
                candidate_layout = (
                    attachment_content(candidate)
                    if isinstance(candidate, HumanMessage)
                    else None
                )
                if candidate_layout is not None:
                    for span in candidate_layout.spans:
                        identity = span["file_id"], span["injection_mode"]
                        payloads.setdefault(identity, []).append(
                            candidate_layout.payload(span)
                        )
        if any(
            layout.payload(span)
            not in payloads.get((span["file_id"], span["injection_mode"]), ())
            for span in layout.spans
        ):
            return False
    return True


def _view_entries(
    raw_messages: Sequence[BaseMessage],
    snapshot: ContextCompactionSnapshot | None,
) -> tuple[tuple[CompactedMessage, ...], bool]:
    if snapshot is None:
        return _identity_entries(raw_messages), False
    if not _snapshot_preserves_required_content(snapshot, raw_messages):
        logger.debug(
            "Rebuilt a legacy compaction view from raw history to preserve required content."
        )
        return _identity_entries(raw_messages), True
    count = snapshot["source_message_count"]
    return (
        *_snapshot_entries(snapshot, raw_messages),
        *_identity_entries(raw_messages[count:], start_index=count),
    ), False


def model_messages_for_state(state: Mapping[str, Any]) -> list[BaseMessage]:
    """Build the reusable model view without mutating the raw graph messages."""
    raw = tuple(
        message
        for message in (state.get("messages") or ())
        if isinstance(message, BaseMessage)
    )
    entries, _ = _view_entries(raw, _read_snapshot(state, raw))
    return [entry.rendered for entry in entries]


class PipelineCompactor(Compactor):
    """Build and verify a temporary model view before it can enter the sidecar."""

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
        entries, rebuilt = _view_entries(raw_messages, snapshot)
        context = CompactionContext(
            request=request,
            entries=protect_entries(entries, keep_recent_turns=self.keep_recent_turns),
            current_tokens=0,
            snapshot=snapshot,
        )
        original_tokens = await self._count(context)
        context = context.with_current_tokens(original_tokens)
        pending = bool(snapshot and snapshot["status"] == "pending_auto_compact")
        logger.debug(
            "Compaction view: raw={}, view={}, tokens={}, pending={}, hard={}, trigger={}, target={}.",
            len(raw_messages),
            len(entries),
            original_tokens,
            pending,
            request.budget.available_input_tokens,
            request.budget.trigger_input_tokens,
            request.budget.target_input_tokens,
        )

        def block(error: ContextCompactionError) -> ContextCompactionError:
            return error.with_partial_result(
                self._result(
                    context,
                    raw_messages,
                    original_tokens,
                    status="pending_auto_compact",
                    force_persist=True,
                )
            )

        for layer in self.layers:
            try:
                candidate = await self._apply_layer(layer, context, pending=pending)
            except ContextCompactionError as error:
                raise block(error)
            context = candidate

        if context.current_tokens > request.budget.available_input_tokens:
            raise block(
                ContextCompactionError(
                    "Model input exceeds the hard limit with required content preserved."
                )
            )
        if pending and not any(
            layer.name == AutoCompactLayer.name for layer in self.layers
        ):
            raise block(
                ContextCompactionError(
                    "Pending auto-compaction requires a summary layer."
                )
            )

        diagnostics = [
            ("WARNING", warning)
            for warning in context.warnings
            if warning.startswith("soft_degraded: ")
        ]
        budget = request.budget
        if (
            diagnostics or AutoCompactLayer.name in context.applied_layers
        ) and context.current_tokens > budget.target_input_tokens:
            reason = (
                "Kept the verified view after the summary failed."
                if diagnostics
                else "The accepted summary left the assembled input above the target."
            )
            warning = f"target_unmet: {reason}"
            context = context.add_warnings(warning)
            diagnostics.append(("INFO", warning))

        for level, diagnostic in diagnostics:
            event, _, reason = diagnostic.partition(": ")
            logger.log(
                level,
                "Context compaction {}: reason={} B={} H={} L={} "
                "before_tokens={} after_tokens={} continue_inference=True",
                event,
                reason,
                budget.available_input_tokens,
                budget.trigger_input_tokens,
                budget.target_input_tokens,
                original_tokens,
                context.current_tokens,
            )
        return self._result(
            context,
            raw_messages,
            original_tokens,
            status="complete",
            force_persist=rebuilt or pending,
        )

    async def _apply_layer(
        self,
        layer: CompactionLayer,
        context: CompactionContext,
        *,
        pending: bool,
    ) -> CompactionContext:
        is_summary_layer = layer.name == AutoCompactLayer.name
        verify_summary = False
        try:
            candidate = await layer.apply(context)
            if candidate.entries == context.entries:
                return candidate
            # Verify the assembled view before treating an edit as a saving.
            verify_summary = is_summary_layer
            if layer.name == HistoricalAttachmentCompactor.name:
                candidate = candidate.with_entries(
                    protect_entries(
                        candidate.entries, keep_recent_turns=self.keep_recent_turns
                    )
                )
            else:
                message_groups(candidate.model_messages)
            tokens = await self._count(candidate)
            if (
                is_summary_layer
                and tokens > context.request.budget.available_input_tokens
            ):
                raise ContextCompactionError(
                    "Auto-compaction produced input above the hard limit."
                )
            if tokens >= context.current_tokens and not (is_summary_layer and pending):
                if is_summary_layer:
                    raise ContextCompactionError(
                        "Auto-compaction did not reduce estimated model input."
                    )
                return context.add_warnings(
                    f"{layer.name}: no estimated token savings."
                )
        except Exception as error:
            detail = f"{layer.name} failed ({type(error).__name__})."
            if is_summary_layer:
                if (
                    not pending
                    and context.current_tokens
                    <= context.request.budget.available_input_tokens
                ):
                    if verify_summary:
                        await _adispatch_custom_event_safely(
                            "on_context_compaction", {"phase": "failed"}
                        )
                    reason = (
                        str(error)
                        if isinstance(error, ContextCompactionError)
                        else detail
                    )
                    return context.add_warnings(f"soft_degraded: {reason}")
                if isinstance(error, ContextCompactionError):
                    raise
                raise ContextCompactionError(detail) from error
            # Keep the last verified view and allow the following layers to try.
            return context.add_warnings(detail)

        logger.debug(
            "Compaction layer {}: before={}, after={}, actions={}.",
            layer.name,
            context.current_tokens,
            tokens,
            len(candidate.actions) - len(context.actions),
        )
        return candidate.with_current_tokens(tokens).mark_layer(layer.name)

    @staticmethod
    def _result(
        context: CompactionContext,
        raw_messages: Sequence[BaseMessage],
        original_tokens: int,
        *,
        status: ContextCompactionStatus,
        force_persist: bool = False,
    ) -> CompactionResult:
        accepted_summary = status == "complete" and any(
            action.layer == AutoCompactLayer.name and action.kind == "summarize"
            for action in context.actions
        )
        return CompactionResult(
            entries=context.entries,
            actions=context.actions,
            original_tokens=original_tokens,
            compacted_tokens=context.current_tokens,
            applied_layers=context.applied_layers,
            warnings=context.warnings,
            source_message_count=len(raw_messages),
            source_message_ids=tuple(_message_id(message) for message in raw_messages),
            snapshot_status=status,
            auto_compacted=accepted_summary
            or bool(context.snapshot and context.snapshot["auto_compacted"]),
            auto_compacted_this_run=accepted_summary,
            should_persist_snapshot=force_persist or bool(context.applied_layers),
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
