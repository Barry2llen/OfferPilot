from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from langgraph._internal._typing import StateLike

from schemas.model_selection import ModelSelection

from ..base import BaseAgentState, GraphRuntime
from .models import (
    CompactionContext,
    CompactionRequest,
    CompactionResult,
    ContextBudget,
)


class Compactor[State: StateLike = BaseAgentState](Protocol):
    async def acompact(self, request: CompactionRequest[State]) -> CompactionResult: ...


class CompactionLayer[State: StateLike = BaseAgentState](Protocol):
    name: str

    async def apply(
        self,
        context: CompactionContext[State],
    ) -> CompactionContext[State]: ...


class TokenCounter(Protocol):
    async def acount(
        self,
        *,
        system_prompts: Sequence[BaseMessage],
        messages: Sequence[BaseMessage],
        tools: Sequence[BaseTool],
    ) -> int: ...


class ContextBudgetPolicy(Protocol):
    def resolve(self, model_selection: ModelSelection) -> ContextBudget: ...


class CompactionModelResolver[State: StateLike = BaseAgentState](Protocol):
    async def aresolve(self, runtime: "GraphRuntime[State]") -> ModelSelection: ...


__all__ = [
    "CompactionLayer",
    "Compactor",
    "CompactionModelResolver",
    "ContextBudgetPolicy",
    "TokenCounter",
]
