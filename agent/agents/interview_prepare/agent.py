
from langgraph.constants import START, END
from langgraph.graph.state import StateGraph
from langchain.messages import SystemMessage

from .state import State
from ...graphs.model_call import ModelCallGraph
from ...tools.web_search import web_search_tools

_model_call_node = ModelCallGraph(
    system_prompts=[
        SystemMessage(content=(
            # TODO: Add more detailed system prompt
            ""
        ))
    ],
    tools=web_search_tools
).get_compiled_graph()
    
graph = StateGraph[State](State)
graph.add_node("model_call", _model_call_node)
graph.add_edge(START, "model_call")
graph.add_edge("model_call", END)
agent = graph.compile()

__all__ = [
    "agent"
]
