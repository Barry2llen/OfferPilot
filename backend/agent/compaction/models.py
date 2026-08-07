from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Literal

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from langgraph._internal._typing import StateLike

from ..base import (
    BaseAgentState,
    ContextCompactionSnapshot,
    ContextCompactionStatus,
    GraphRuntime,
)

CompactionEntryKind = Literal["identity", "rewrite", "summary"]
CompactionActionKind = Literal["keep", "rewrite", "drop", "summarize"]


@dataclass(frozen=True, slots=True)
class MessageRef:
    """A stable reference to an original message in the graph state."""

    index: int
    message_id: str | None

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("MessageRef.index must be non-negative.")


@dataclass(frozen=True, slots=True)
class CompactedMessage:
    """A traceable model-view message, never written back to graph state."""

    rendered: BaseMessage
    sources: tuple[MessageRef, ...]
    kind: CompactionEntryKind
    layer: str
    protected: bool = False


@dataclass(frozen=True, slots=True)
class ContextBudget:
    max_context_tokens: int
    reserved_output_tokens: int
    safety_margin_tokens: int

    @property
    def available_input_tokens(self) -> int:
        return (
            self.max_context_tokens
            - self.reserved_output_tokens
            - self.safety_margin_tokens
        )

    def __post_init__(self) -> None:
        if self.max_context_tokens <= 0:
            raise ValueError("max_context_tokens must be positive.")
        if self.reserved_output_tokens < 0:
            raise ValueError("reserved_output_tokens must be non-negative.")
        if self.safety_margin_tokens < 0:
            raise ValueError("safety_margin_tokens must be non-negative.")
        if (
            self.reserved_output_tokens + self.safety_margin_tokens
            >= self.max_context_tokens
        ):
            raise ValueError(
                "reserved_output_tokens and safety_margin_tokens must leave input capacity."
            )


@dataclass(frozen=True, slots=True)
class CompactionAction:
    layer: str
    kind: CompactionActionKind
    sources: tuple[MessageRef, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class CompactionRequest[State: StateLike = BaseAgentState]:
    """Inputs resolved by ModelCallGraph and runtime-visible state."""

    runtime: GraphRuntime[State]
    system_prompts: tuple[BaseMessage, ...]
    tools: tuple[BaseTool, ...]
    budget: ContextBudget


@dataclass(frozen=True, slots=True)
class CompactionContext[State: StateLike = BaseAgentState]:
    """The immutable temporary model view passed through all layers."""

    request: CompactionRequest[State]
    entries: tuple[CompactedMessage, ...]
    current_tokens: int
    actions: tuple[CompactionAction, ...] = ()
    applied_layers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    raw_message_count: int = 0
    snapshot: ContextCompactionSnapshot | None = None

    @property
    def model_messages(self) -> list[BaseMessage]:
        return [entry.rendered for entry in self.entries]

    @property
    def protected_entries(self) -> tuple[CompactedMessage, ...]:
        return tuple(entry for entry in self.entries if entry.protected)

    @property
    def has_new_messages_since_snapshot(self) -> bool:
        if self.snapshot is None:
            return True
        return self.raw_message_count > self.snapshot["source_message_count"]

    def map_entries(
        self,
        transform: Callable[[CompactedMessage], CompactedMessage],
    ) -> CompactionContext[State]:
        return replace(self, entries=tuple(transform(entry) for entry in self.entries))

    def with_entries(
        self,
        entries: tuple[CompactedMessage, ...],
    ) -> CompactionContext[State]:
        return replace(self, entries=entries)

    def with_current_tokens(self, current_tokens: int) -> CompactionContext[State]:
        if current_tokens < 0:
            raise ValueError("current_tokens must be non-negative.")
        return replace(self, current_tokens=current_tokens)

    def add_actions(
        self,
        *actions: CompactionAction,
    ) -> CompactionContext[State]:
        return replace(self, actions=(*self.actions, *actions))

    def mark_layer(self, name: str) -> CompactionContext[State]:
        if name in self.applied_layers:
            return self
        return replace(self, applied_layers=(*self.applied_layers, name))

    def add_warnings(self, *warnings: str) -> CompactionContext[State]:
        new_warnings = tuple(warning for warning in warnings if warning)
        if not new_warnings:
            return self
        return replace(self, warnings=(*self.warnings, *new_warnings))


@dataclass(frozen=True, slots=True)
class CompactionResult:
    entries: tuple[CompactedMessage, ...]
    actions: tuple[CompactionAction, ...]
    original_tokens: int
    compacted_tokens: int
    applied_layers: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    source_message_count: int = 0
    source_message_ids: tuple[str | None, ...] = ()
    snapshot_status: ContextCompactionStatus = "complete"
    auto_compacted: bool = False
    auto_compacted_this_run: bool = False
    should_persist_snapshot: bool = False

    @property
    def model_messages(self) -> list[BaseMessage]:
        return [entry.rendered for entry in self.entries]

    def build_snapshot(self) -> ContextCompactionSnapshot:
        return {
            "messages": list(self.model_messages),
            "source_message_count": self.source_message_count,
            "source_message_ids": list(self.source_message_ids),
            "status": self.snapshot_status,
            "auto_compacted": self.auto_compacted,
        }


__all__ = [
    "CompactionAction",
    "CompactionActionKind",
    "CompactionContext",
    "CompactionEntryKind",
    "CompactionRequest",
    "CompactionResult",
    "ContextCompactionSnapshot",
    "ContextCompactionStatus",
    "ContextBudget",
    "CompactedMessage",
    "MessageRef",
]
