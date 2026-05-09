
from typing import (
    Any,
    Sequence,
    NamedTuple
)

from langchain_core.tools import BaseTool
from langchain_core.messages import SystemMessage

from ..base import BaseAgentState

class Runtime(NamedTuple):
    state: BaseAgentState
    tools: Sequence[BaseTool]
    additional_context: dict[str, Any]

__all__ = [
    "Runtime",
]