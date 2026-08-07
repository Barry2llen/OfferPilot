from typing import override

from langgraph.graph import END, START, StateGraph

from agent.compaction import (
    CompactionModelResolver,
    Compactor,
    ContextBudgetPolicy,
    build_supervisor_compactor,
)
from agent.graphs.model_call import ModelCallGraph
from schemas.config import Config

from ...base import BaseAgent, GraphRuntime
from ...prompts import PromptComposer, PromptFragment
from ...tools import Tools, ToolsBuilder
from .state import BaseAgentState, State


def _metadata(runtime: GraphRuntime[State]) -> str:

    def _get_model_name(state: BaseAgentState) -> str:
        model_selection = state.get("model")
        model = model_selection() if callable(model_selection) else model_selection
        return model.model_name if model else "unknown"

    return (
        f"Today is {__import__('datetime').datetime.now().strftime('%Y-%m-%d')}.\n"
        f"You are called as '{_get_model_name(runtime.state)}' in OfferPilot's agent framework."
    )


_system_prompt = PromptComposer(
    [
        PromptFragment(
            name="Instructions",
            content=(
                "You are a helpful assistant.\n\n"
                "When using resume or job-description analysis tools, call each tool only once "
                "for the current user request and wait for its structured result. If the source "
                "comes from an attached file, use the file ID shown in the attachment references "
                "with file_id or file_ids and do not copy the extracted or OCR text into the tool "
                "input. For a job description, use jd_text only for text directly pasted by the "
                "user, and use source_url only for an explicitly provided URL."
            ),
        ),
        PromptFragment(
            name="Metadata",
            content=_metadata,
        ),
    ]
)


class SupervisorAgent(BaseAgent[State]):
    def __init__(
        self,
        *args,
        config: Config | None = None,
        tools: Tools | ToolsBuilder | None = None,
        compactor: Compactor[State] | None = None,
        context_budget_policy: ContextBudgetPolicy | None = None,
        compaction_model_resolver: CompactionModelResolver | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, config=config, **kwargs)
        self.tools = tools or tuple()
        resolved_compactor = (
            compactor
            if compactor is not None
            else build_supervisor_compactor(
                self.config,
                model_resolver=compaction_model_resolver,
            )
        )
        self._model_call_node = ModelCallGraph(
            *args,
            **kwargs,
            system_prompts=_system_prompt,
            config=self.config,
            tools=self.tools,
            compactor=resolved_compactor,
            context_budget_policy=context_budget_policy,
        ).get_compiled_graph()

    @override
    def get_graph(self) -> StateGraph[State]:
        graph = StateGraph[State](State)
        graph.add_node("model_call", self._model_call_node)
        graph.add_edge(START, "model_call")
        graph.add_edge("model_call", END)

        return graph
