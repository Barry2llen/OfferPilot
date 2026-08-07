from typing import override

from langchain.messages import SystemMessage
from langgraph.constants import END, START
from langgraph.graph.state import StateGraph

from ...base import BaseAgent
from ...graphs.model_call import ModelCallGraph
from .state import State


class ResumeAdviceAgent(BaseAgent[State]):
    _model_call_node = ModelCallGraph(
        system_prompts=[SystemMessage(content=(""))]
    ).get_compiled_graph()

    @override
    def get_graph(self) -> StateGraph[State]:

        graph = StateGraph[State](State)
        graph.add_node("model_call", self._model_call_node)
        graph.add_edge(START, "model_call")
        graph.add_edge("model_call", END)

        return graph


__all__ = ["ResumeAdviceAgent"]
