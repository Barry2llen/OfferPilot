
from langchain.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph

from schemas.resume_document import ResumeDocument
from schemas.model_selection import ModelSelection
from ...agents.resume_advice import (
    State,
    agent as RESUME_ADVICE_AGENT,
)
from ..base import agent2workflow
from ...state import MaybeCallable
    
def resume_advice(
        resume: ResumeDocument,
        model: MaybeCallable[ModelSelection],
        *,
        resume_images: list[str] | None = None,
        user_prompt: str | None = None,
        **kwargs
    ) -> CompiledStateGraph[State]:

    content = [
        {"type": "image_url", "image_url": {"url": image_uri}}
        for image_uri in (resume_images or resume.convert_resume_to_image_base64())
    ]

    if user_prompt:
        content = [{"type": "text", "text": user_prompt}] + content

    return agent2workflow(
        State,
        RESUME_ADVICE_AGENT,
        State(
            model=model,
            messages=[HumanMessage(content=content)]
        ),
        **kwargs
    )

__all__ = [
    resume_advice
]
