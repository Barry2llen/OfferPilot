
from typing import override
from collections.abc import Sequence
from langgraph.graph import StateGraph, START, END
from langchain.messages import SystemMessage
from langchain_core.tools import BaseTool

from agent.graphs.model_call import ModelCallGraph
from schemas.config import Config
from .state import State
from ...base import BaseAgent

class SupervisorAgent(BaseAgent[State]):
    
    system_prompt = SystemMessage(
        content = (
            "You are a helpful assistant.\n" \
            f"Today is {__import__('datetime').datetime.now().strftime('%Y-%m-%d')}."
        )
    )

    def __init__(
        self,
        *args,
        config: Config | None = None,
        tools: Sequence[BaseTool] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.tools = tuple(tools or ())
        self._model_call_node = ModelCallGraph(
            system_prompts=[self.system_prompt],
            config=config,
            tools=self.tools,
        ).get_compiled_graph()

    @override
    def get_graph(self) -> StateGraph[State]:
        graph = StateGraph[State](State)
        graph.add_node("model_call", self._model_call_node)
        graph.add_edge(START, "model_call")
        graph.add_edge("model_call", END)

        return graph
