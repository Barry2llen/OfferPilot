from langgraph.constants import START, END
from langgraph.graph.state import StateGraph
from langchain.messages import SystemMessage

from exceptions.resume import NotAResumeError, ResumePreviewConversionError
from schemas.resume_document import ResumeDocument
from schemas.resume_profile import ResumeProfile
from .state import State
from ...models import load_chat_model
from ...graphs.model_call import ModelCallGraph


def _set_up_node(state: State) -> State:
    """
    Set up the initial state for the ResumeExtractorAgent.
    """

    if not state["resume_document"] or not isinstance(state["resume_document"], ResumeDocument):
        raise NotAResumeError(f"The provided document is not recognized as a resume: {state['resume_document']}")

    model_selection = state['model'](state) if callable(state['model']) else state['model']
    state['structured_output_model'] = load_chat_model(model_selection).with_structured_output(ResumeProfile)

    resume_document = state["resume_document"]

    try:
        state["resume_images"] = resume_document.convert_resume_to_image_base64()
    except Exception as e:
        raise ResumePreviewConversionError(f"Failed to convert resume to image: {e}")
    
    if not model_selection.supports_image_input:
        try:
            state["resume_text"] = resume_document.extract_text()
        except Exception as e:
            raise ResumePreviewConversionError(f"Failed to extract text from resume: {e}")