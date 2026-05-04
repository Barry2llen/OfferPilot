
from schemas.resume import Resume, ResumeSectionEx
from schemas.resume_document import ResumeDocument
from ...base import BaseAgentState
from ...annotations.types import Displace

class State(BaseAgentState, total=False):
    """
    State for the ResumeExtractorAgent. Inherits from BaseAgentState.
    """

    resume_document: Displace[ResumeDocument]

    resume_images: Displace[list[str]]

    resume_text: Displace[str]

    sections: Displace[list[ResumeSectionEx]]

    # As a result
    resume: Displace[Resume]