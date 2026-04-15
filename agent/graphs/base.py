
from abc import ABC, abstractmethod

from langgraph.graph import StateGraph

from ..state.base import BaseAgentState

class BaseGraph(ABC):
    @abstractmethod
    def get_graph(self) -> StateGraph[BaseAgentState]:
        pass


__all__ = [
    BaseGraph
]
