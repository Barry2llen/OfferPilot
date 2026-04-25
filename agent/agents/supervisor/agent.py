
from typing import override
from langgraph.graph import StateGraph, START, END
from langchain.messages import SystemMessage

from agent.graphs.model_call import ModelCallGraph
from .state import State
from ...tools import get_all_tools
from ...base import BaseAgent

class SupervisorAgent(BaseAgent[State]):
    
    system_prompt = SystemMessage(
        content="You are a helpful assistant."
    )

    tools = get_all_tools()

    _model_call_node = ModelCallGraph(
        system_prompts=[system_prompt],
        tools=tools
    ).get_compiled_graph()

    @override
    def get_graph(self) -> StateGraph[State]:
        graph = StateGraph[State](State)
        graph.add_node("model_call", self._model_call_node)
        graph.add_edge(START, "model_call")
        graph.add_edge("model_call", END)

        return graph