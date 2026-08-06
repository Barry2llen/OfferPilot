from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Literal, TypeAlias

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from langgraph._internal._typing import StateLike

from ..base import BaseAgentState, GraphRuntime
from schemas.model_selection import ModelSelection


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
    """A traceable rendered message, not a message sent to LangGraph state."""

    rendered: BaseMessage
    sources: tuple[MessageRef, ...]
    kind: CompactionEntryKind
    layer: str


@dataclass(frozen=True, slots=True)
class ContextBudget:
    max_context_tokens: int
    reserved_output_tokens: int
    safety_margin_tokens: int
    trigger_input_tokens: int
    target_input_tokens: int

    def __post_init__(self) -> None:
        if self.max_context_tokens <= 0:
            raise ValueError("max_context_tokens must be positive.")
        if self.reserved_output_tokens < 0:
            raise ValueError("reserved_output_tokens must be non-negative.")
        if self.safety_margin_tokens < 0:
            raise ValueError("safety_margin_tokens must be non-negative.")
        if self.reserved_output_tokens + self.safety_margin_tokens >= self.max_context_tokens:
            raise ValueError(
                "reserved_output_tokens and safety_margin_tokens must leave input capacity."
            )
        if self.trigger_input_tokens <= self.target_input_tokens:
            raise ValueError("trigger_input_tokens must be greater than target_input_tokens.")
        if self.target_input_tokens < 0:
            raise ValueError("target_input_tokens must be non-negative.")
        if self.trigger_input_tokens > self.max_context_tokens:
            raise ValueError("trigger_input_tokens cannot exceed max_context_tokens.")


@dataclass(frozen=True, slots=True)
class CompactionAction:
    layer: str
    kind: CompactionActionKind
    sources: tuple[MessageRef, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class CompactionRequest[State: StateLike = BaseAgentState]:
    runtime: GraphRuntime[State]
    messages: tuple[BaseMessage, ...]
    system_prompts: tuple[BaseMessage, ...]
    tools: tuple[BaseTool, ...]
    model_selection: ModelSelection
    budget: ContextBudget


@dataclass(frozen=True, slots=True)
class SingleMessageUnit:
    entries: tuple[CompactedMessage, ...]
    protected: bool = False


@dataclass(frozen=True, slots=True)
class ToolExchangeUnit:
    entries: tuple[CompactedMessage, ...]
    tool_call_ids: tuple[str, ...]
    complete: bool
    protected: bool = False


ContextUnit: TypeAlias = SingleMessageUnit | ToolExchangeUnit


@dataclass(frozen=True, slots=True)
class CompactionContext[State: StateLike = BaseAgentState]:
    request: CompactionRequest[State]
    units: tuple[ContextUnit, ...]
    actions: tuple[CompactionAction, ...] = ()
    applied_layers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def entries(self) -> tuple[CompactedMessage, ...]:
        return tuple(entry for unit in self.units for entry in unit.entries)

    @property
    def model_messages(self) -> list[BaseMessage]:
        return [entry.rendered for entry in self.entries]

    def map_entries(
        self,
        transform: Callable[[CompactedMessage], CompactedMessage],
    ) -> CompactionContext[State]:
        return replace(
            self,
            units=tuple(
                replace(unit, entries=tuple(transform(entry) for entry in unit.entries))
                for unit in self.units
            ),
        )

    def with_units(self, units: tuple[ContextUnit, ...]) -> CompactionContext[State]:
        return replace(self, units=units)

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
        return replace(self, warnings=(*self.warnings, *warnings))


@dataclass(frozen=True, slots=True)
class CompactionResult:
    entries: tuple[CompactedMessage, ...]
    actions: tuple[CompactionAction, ...]
    original_tokens: int
    compacted_tokens: int
    applied_layers: tuple[str, ...]
    reached_target: bool
    warnings: tuple[str, ...] = ()

    @property
    def model_messages(self) -> list[BaseMessage]:
        return [entry.rendered for entry in self.entries]


__all__ = [
    "CompactionAction",
    "CompactionActionKind",
    "CompactionContext",
    "CompactionEntryKind",
    "CompactionRequest",
    "CompactionResult",
    "ContextBudget",
    "ContextUnit",
    "MessageRef",
    "SingleMessageUnit",
    "ToolExchangeUnit",
]
