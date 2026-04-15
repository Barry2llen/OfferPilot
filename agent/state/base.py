
from typing import (
    TypedDict,
    Sequence,
    Annotated,
    Callable
)

from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage

from schemas.model_selection import ModelSelection

class BaseAgentState(TypedDict):
    """
    Base class for agent state. All agent states should inherit from this class.
    """
    model: ModelSelection | Callable[..., ModelSelection]
    messages: Annotated[Sequence[BaseMessage], add_messages]