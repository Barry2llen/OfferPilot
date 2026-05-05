
from typing import override, cast

from schemas.model_selection import ModelSelection
from schemas.resume import Resume
from schemas.resume_document import ResumeDocument
from schemas.config import Config
from ...base import BaseWorkflow
from ...annotations.types import MaybeCallable
from ...nodes.wrappers import require_fields
from ...agents.resume_extractor import State
from ...agents.resume_extractor import ResumeExtractorAgent

class ResumeExtractWorkflow(BaseWorkflow[Resume, State]):
    
    def __init__(self, config: Config | None = None):
        super().__init__(ResumeExtractorAgent(config=config))

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
    @require_fields('resume', index=1)
    def _get_result(self, state: State) -> Resume:
        resume = state.get("resume")
        return cast(Resume, resume)
    
__all__ = [
    "ResumeExtractWorkflow"
]
