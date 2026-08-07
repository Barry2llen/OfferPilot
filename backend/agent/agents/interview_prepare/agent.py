from langchain.messages import SystemMessage
from langgraph.constants import END, START
from langgraph.graph.state import StateGraph

from ...graphs.model_call import ModelCallGraph
from ...tools.web_search import get_web_search_tools
from .state import State

_model_call_node = ModelCallGraph(
    system_prompts=[
        SystemMessage(
            content=(
                # TODO: Add more detailed system prompt
                ""
            )
        )
    ],
    tools=get_web_search_tools(),
).get_compiled_graph()

graph = StateGraph[State](State)
graph.add_node("model_call", _model_call_node)
graph.add_edge(START, "model_call")
graph.add_edge("model_call", END)
agent = graph.compile()

__all__ = ["agent"]
