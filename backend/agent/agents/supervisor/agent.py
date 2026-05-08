
from typing import override
from collections.abc import Sequence
from langgraph.graph import StateGraph, START, END
from langchain.messages import SystemMessage
from langchain_core.tools import BaseTool

from agent.graphs.model_call import ModelCallGraph
from schemas.config import Config
from .state import State, BaseAgentState
from ...base import BaseAgent
from ...graphs.model_call import Runtime

def _dynamic_system_prompt(runtime: Runtime) -> list[SystemMessage]:

    import datetime

    def _get_model_name(state: BaseAgentState) -> str:
        model_selection = state.get("model")
        model = model_selection() if callable(model_selection) else model_selection
        return model.model_name if model else "unknown"


    return [
        SystemMessage(
            content = (
                "You are a helpful assistant."
                "\n"
                "Metadata:"
                f"Today is {datetime.datetime.now().strftime('%Y-%m-%d')}."
                f"You are called as '{_get_model_name(runtime.state)}' in OfferPilot's agent framework."
                f"You have access to the following tools: {', '.join(tool.name for tool in runtime.tools)}."
            )
        )
    ]

class SupervisorAgent(BaseAgent[State]):

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
            system_prompts=_dynamic_system_prompt,
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
