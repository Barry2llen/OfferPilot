from typing import (
    override,
    cast
)

from schemas.config import Config
from schemas.job_description import JobDescription
from schemas.model_selection import ModelSelection
from ...base import BaseWorkflow
from ...annotations.types import MaybeCallable
from ...nodes.wrappers import require_fields
from ...agents.jd_analyzer import (
    State,
    JdAnalyzerAgent
)

class JdAnalysisWorkflow(BaseWorkflow[JobDescription, State]):
    
    def __init__(self, config: Config | None = None):
        super().__init__(JdAnalyzerAgent(config=config))

    @override
    def _construct_initial_state(
        self,
        model: MaybeCallable[ModelSelection],
        jd_text: str | None = None,
        source_url: str | None = None,
        images: list[str] | None = None
    ) -> State:
        return State(
            model=model,
            messages=[],
            jd_text=jd_text,
            source_url=source_url,
            images=images
        )
    
    @override
    @require_fields('job_description', index=1)
    def _get_result(self, state: State) -> JobDescription:
        job_description = state.get("job_description")
        return cast(JobDescription, job_description)
    
__all__ = [
    "JdAnalysisWorkflow"
]