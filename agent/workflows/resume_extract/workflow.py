
from typing import override

from schemas.model_selection import ModelSelection
from schemas.resume_profile import ResumeProfile
from schemas.resume_document import ResumeDocument
from ...base import BaseWorkflow
from ...annotations.types import MaybeCallable
from ...nodes.wrappers import require_fields
from ...agents.resume_extractor import State
from ...agents.resume_extractor import ResumeExtractorAgent

class ResumeExtractWorkflow(BaseWorkflow[ResumeProfile, State]):
    
    def __init__(self):
        super().__init__(ResumeExtractorAgent())

    @override
    def _construct_initial_state(
        self,
        model: MaybeCallable[ModelSelection],
        resume_document: ResumeDocument
    ) -> State:
        return State(
            model=model,
            messages=[],
            resume_document=resume_document
        )
    
    @override
    @require_fields('resume_document', index=1)
    def _get_result(self, state: State) -> ResumeProfile:
        return state["resume_profile"]
    
__all__ = [
    "ResumeExtractWorkflow"
]