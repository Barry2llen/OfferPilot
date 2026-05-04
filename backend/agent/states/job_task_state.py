
from schemas.resume import Resume

from ..base import BaseAgentState

class JobTaskState(BaseAgentState):
    """
    State for a complete job task. This state is used for the entire duration of a job task, from the moment it is created until it is completed.
    """

    resume_id: str | None
    resume: Resume | None
