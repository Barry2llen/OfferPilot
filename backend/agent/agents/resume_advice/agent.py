
from typing import override

from langgraph.constants import START, END
from langgraph.graph.state import StateGraph
from langchain.messages import SystemMessage

from .state import State
from ...base import BaseAgent
from ...graphs.model_call import ModelCallGraph

class ResumeAdviceAgent(BaseAgent[State]):

    _model_call_node = ModelCallGraph(
        system_prompts=[
            SystemMessage(content=(
                ""
            ))
        ]
    ).get_compiled_graph()

    @override
    def get_graph(self) -> StateGraph[State]:
    
        graph = StateGraph[State](State)
        graph.add_node("model_call", self._model_call_node)
        graph.add_edge(START, "model_call")
        graph.add_edge("model_call", END)

        return graph
    
__all__ = [
    "ResumeAdviceAgent"
]