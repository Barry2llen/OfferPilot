
from abc import ABC, abstractmethod

from langgraph.graph import StateGraph

from ..state.base import BaseAgentState

class BaseGraph(ABC):
    """Base graph for agent workflows. This class is responsible for defining the structure of the graph and the nodes in the graph. It also provides a method to get the graph object that can be used to execute the graph."""
    @abstractmethod
    def get_graph(self) -> StateGraph[BaseAgentState]:
        pass


__all__ = [
    BaseGraph
]
