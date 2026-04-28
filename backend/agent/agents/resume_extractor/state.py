
from langchain.messages import SystemMessage
from langchain_core.runnables import Runnable
from langchain_core.language_models import LanguageModelInput

from schemas.resume_profile import ResumeProfile
from schemas.resume_document import ResumeDocument
from ...base import BaseAgentState
from ...annotations.types import Displace

class State(BaseAgentState):
    """
    State for the ResumeExtractorAgent. Inherits from BaseAgentState.
    """

    resume_document: Displace[ResumeDocument] = None

    structured_output_model: Displace[Runnable[LanguageModelInput, ResumeDocument]] = None

    # If model supports image input, the first choice is to render images from the resume document and send them to the model for information extraction
    resume_images: Displace[list[str]] = None

    # Otherwise, the second choice is to extract text directly from the resume document to get information
    # If the extraction is bad, we should fall back to OCR on the rendered images to get the text, which is the third choice
    resume_text: Displace[str | None] = None

    # As a result
    resume_profile: Displace[ResumeProfile | None] = None