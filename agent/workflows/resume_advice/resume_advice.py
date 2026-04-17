
from langchain.messages import SystemMessage
from langgraph.graph import StateGraph

from .state import State
from ...graphs.model_call import ModelCallGraph
from ...graphs.base import BaseGraph

class Graph(BaseGraph):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        system_prompt = (
            "You are a helpful assistant that provides advice on how to improve a resume. \n"
            "You will be given a resume and you need to provide advice on how to improve it. \n"
            "You should provide specific and actionable advice that the user can follow to improve their resume. \n"
            "You should also provide examples of how to improve the resume if possible."
        )

        self._model_call_node = ModelCallGraph(*args, system_prompts=[SystemMessage(content=system_prompt)], **kwargs).get_graph()

    def _set_up_node(self, state: State) -> State:
        """
        For possiple set-ups.
        """

        return State()
    
    def _construct_prompt(self, state: State) -> State:
        pass
    

    
    def get_graph(self) -> StateGraph[State]:
        pass

__all__ = [
    Graph
]