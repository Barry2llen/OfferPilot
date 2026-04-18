
from langgraph.constants import START, END
from langchain.messages import HumanMessage, SystemMessage
from langgraph.graph.state import CompiledStateGraph, StateGraph

from schemas.resume_document import ResumeDocument
from schemas.model_selection import ModelSelection
from ...graphs.model_call import ModelCallGraph
from ...state import MaybeCallable, BaseAgentState as State
    
system_prompt = (
    "You are a helpful assistant that provides advice on how to improve a resume. \n"
    "You will be given a resume and you need to provide advice on how to improve it. \n"
    "You should provide specific and actionable advice that the user can follow to improve their resume. \n"
    "You should also provide examples of how to improve the resume if possible."
)
    
def resume_advice(
        resume: ResumeDocument,
        model: MaybeCallable[ModelSelection],
        *,
        resume_images: list[str] | None = None,
        user_prompt: str | None = None,
        **kwargs
    ) -> CompiledStateGraph[State]:

    model_call_node = ModelCallGraph(system_prompts=[SystemMessage(content=system_prompt)], **kwargs).get_compiled_graph()

    def _set_up_node(state: State) -> State:
        """Set up the node with the resume content."""

        content = [
            {"type": "image_url", "image_url": {"url": image_uri}}
            for image_uri in (resume_images or resume.convert_resume_to_image_base64())
        ]

        if user_prompt:
            content = [{"type": "text", "text": user_prompt}] + content

        state = State(
            model=model,
            messages=[HumanMessage(content=content)]
        )

        return state
    
    def _resolve_response_node(state: State) -> State:
        """Resolve the response from the model call."""
        return State()

    graph = StateGraph[State](State)
    graph.add_node("setup", _set_up_node)
    graph.add_node("model_call", model_call_node)
    graph.add_node("after", _resolve_response_node)
    graph.add_edge(START, "setup")
    graph.add_edge("setup", "model_call")
    graph.add_edge("model_call", "after")
    graph.add_edge("after", END)
    return graph.compile()

__all__ = [
    resume_advice
]
