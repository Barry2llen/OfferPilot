
from langgraph.graph import StateGraph

from .state import State
from ...graphs.model_call import ModelCallGraph
from ...graphs.base import BaseGraph

class Graph(BaseGraph):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._model_call_node = ModelCallGraph(*args, **kwargs).get_graph()

    def _set_up_node(self, state: State) -> State:
        """
        Prepare system prompt and other necessary information for the model call node.
        """

        
    
    def get_graph(self) -> StateGraph[State]:
        pass

__all__ = [
    Graph
]