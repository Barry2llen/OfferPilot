
from schemas.job_description import (
    JobDescription,
    JobDescriptionEx,
    JdRequirementBlockEx
)
from ...base import BaseAgentState
from ...annotations.types import Displace


class State(BaseAgentState, total=False):
    """State for the JD analyzer agent."""

    # Input (optional — jd_text may be populated by model_call node from URL/image)
    jd_text: str | None
    source_url: Displace[str | None]
    # images are represented as data URLs (e.g. "data:image/png;base64,...") or pure texts (e.g. OCR results)
    images: Displace[list[str] | None]

    # Intermediate
    jd_extracted: Displace[JobDescriptionEx]
    blocks: Displace[list[JdRequirementBlockEx]]
    jd_error: Displace[str | None]

    # Output
    job_description: Displace[JobDescription | None]


__all__ = ["State"]
