
from schemas.resume_document import ResumeDocument
from ...state import BaseAgentState

class State(BaseAgentState):
    """State for resume advice workflow."""
    resume: ResumeDocument

__all__ = [
    State
]