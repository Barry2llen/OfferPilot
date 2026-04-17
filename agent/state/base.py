from __future__ import annotations

from typing import (
    TypedDict,
    Annotated,
    Callable
)

from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage

from schemas.model_selection import ModelSelection
from .type import Displace, MaybeCallable

class BaseAgentState(TypedDict):
    """
    Base class for agent state. All agent states should inherit from this class.
    """

    model: Displace[MaybeCallable[ModelSelection]]
    messages: Annotated[list[BaseMessage], add_messages]

    def _to_base(self) -> BaseAgentState:
        """
        Convert the state to a BaseAgentState. This is useful for converting from a subclass to the base class.
        """
        return BaseAgentState(
            model=self['model'],
            messages=self['messages']
        )
