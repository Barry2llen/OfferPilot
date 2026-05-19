
from schemas.job_description import JobDescription, JobDescriptionEx, JdRequirementBlockEx
from ...base import BaseAgentState
from ...annotations.types import Displace


class State(BaseAgentState, total=False):
    """State for the JD analyzer agent."""

    # Input (optional — jd_text may be populated by model_call node from URL/image)
    jd_text: str | None
    source_url: Displace[str | None]
    images: Displace[list[str]]

    # Intermediate
    jd_extracted: Displace[JobDescriptionEx]
    blocks: Displace[list[JdRequirementBlockEx]]

    # Output
    job_description: Displace[JobDescription | None]


__all__ = ["State"]
