
from typing import override
from langgraph.graph import StateGraph, START, END

from agent.graphs.model_call import ModelCallGraph
from schemas.config import Config
from .state import State, BaseAgentState
from ...prompts import PromptComposer, PromptFragment
from ...base import BaseAgent, GraphRuntime
from ...tools import Tools, ToolsBuilder

def _metadata(runtime: GraphRuntime[State]) -> str:

    def _get_model_name(state: BaseAgentState) -> str:
        model_selection = state.get("model")
        model = model_selection() if callable(model_selection) else model_selection
        return model.model_name if model else "unknown"

    return (
        f"Today is {__import__('datetime').datetime.now().strftime('%Y-%m-%d')}.\n"
        f"You are called as '{_get_model_name(runtime.state)}' in OfferPilot's agent framework."
    )

_system_prompt = PromptComposer([
    PromptFragment(
        name="Instructions",
        content="You are a helpful assistant.",
    ),
    PromptFragment(
        name="Metadata",
        content=_metadata,
    )
])

class SupervisorAgent(BaseAgent[State]):

    def __init__(
        self,
        *args,
        config: Config | None = None,
        tools: Tools | ToolsBuilder | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, config=config, **kwargs)
        self.tools = tools or tuple()
        self._model_call_node = ModelCallGraph(
            *args,
            **kwargs,
            system_prompts=_system_prompt,
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