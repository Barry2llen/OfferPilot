
from typing import override

from schemas.model_selection import ModelSelection
from schemas.resume_profile import ResumeProfile
from schemas.resume_document import ResumeDocument
from ...state import MaybeCallable
from ..base import BaseWorkflow
from ...agents.resume_extractor import State
from ...agents.resume_extractor import agent as RESUME_EXTRACTOR

class ResumeExtractWorkflow(BaseWorkflow[ResumeProfile, State]):
    
    def __init__(self):
        super().__init__(RESUME_EXTRACTOR)

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
    def _get_result(self, state: State) -> ResumeProfile:
        return state["resume_profile"]