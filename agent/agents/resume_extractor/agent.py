from pydantic import BaseModel, Field

from langgraph.constants import START, END
from langgraph.graph.state import StateGraph
from langchain.messages import HumanMessage, SystemMessage

from utils.logger import logger
from exceptions.resume import ResumePreviewConversionError
from schemas.resume_profile import ResumeProfile
from .state import State
from ...nodes.wrappers import require_fields
from ...models import load_chat_model

structured_output_system_prompt: SystemMessage = (
        SystemMessage(
            content = 
                "You are a helpful assistant that extracts structured information from resumes." \
                "Please extract the relevant information from the provided resume and return it in a structured format." \
                "Here follows the resume information that needs to be extracted: "
        )
    )

validation_system_prompt: SystemMessage = (
        SystemMessage(
            content = 
                "You are a helpful assistant that validates the extracted resume profile. " \
                "Your only task is to determine if the resume profile contains amount of garbled text or other forms of corruption. " \
                "Please validate the extracted resume profile and return whether it's valid or not, along with the reason for the validation result." \
                "Here follows the extracted resume profile that needs to be validated: "
        )
    )

@require_fields('resume_document')
def _set_up_node(state: State) -> State:
    """
    Set up the initial state for the ResumeExtractorAgent.
    """

    model_selection = state['model'](state) if callable(state['model']) else state['model']
    state['structured_output_model'] = load_chat_model(model_selection).with_structured_output(ResumeProfile)

    resume_document = state["resume_document"]

    if model_selection.supports_image_input:
        try:
            state["resume_images"] = resume_document.convert_resume_to_image_base64()
        except Exception as e:
            raise ResumePreviewConversionError(f"Failed to convert resume to image: {e}")
    
    if not model_selection.supports_image_input:
        try:
            state["resume_text"] = resume_document.extract_text()
        except Exception as e:
            raise ResumePreviewConversionError(f"Failed to extract text from resume: {e}")
        
    return state

def _if_supports_image(state: State) -> bool:
    """
    Check if the selected model supports image input.
    """
    return state["model"].supports_image_input if state.get("model") else False

def _extract_with_image_node(state: State) -> State:
    """
    Extract information from the resume using the model that supports image input.
    """
    model = state["structured_output_model"]
    resume_images = state["resume_images"]

    if not resume_images:
        raise ResumePreviewConversionError("No resume images available for extraction.")

    # Call the model with the system message and the resume images
    response = model.invoke([structured_output_system_prompt] + [
        {"type": "image_url", "image_url": image} for image in resume_images
    ])
    
    return State(resume_profile=response)

def _image_not_support_node(state: State) -> State:
    """
    Handle the case when the model does not support image input.
    """
    # do nothing here, just a placeholder node to make the graph complete
    return {}

def _if_extraction_succeeded(state: State) -> bool:
    """
    Check if the information extraction was successful by using llm to validate the extracted profile.
    """

    class Validation(BaseModel):
        """
        Validation schema for the extracted resume profile.
        """
        is_valid: bool = Field(description="Whether the extracted resume profile is valid or not.")
        reason: str | None = Field(default=None, description="The reason for the validation result.")
    
    validator = load_chat_model(state["model"]).with_structured_output(Validation)
    validation: Validation = validator.invoke([validation_system_prompt, HumanMessage(content=f"{state['resume_profile']}")])

    return validation.is_valid

def _extract_with_text_node(state: State) -> State:
    """
    Extract information from the resume using the model that supports text input.
    """
    model = state["structured_output_model"]
    resume_text = state["resume_text"]

    if not resume_text:
        raise ResumePreviewConversionError("No resume text available for extraction.")

    # Call the model with the system message and the resume text
    response = model.invoke([structured_output_system_prompt, HumanMessage(content=resume_text)])

    return State(resume_profile=response)

def _extract_text_ocr_node(state: State) -> State:
    """
    Extract information from the resume using OCR on the resume images.
    """
    
    resume_document = state["resume_document"]
    resume_text = resume_document.extract_text_ocr()

    return State(resume_text=resume_text)

graph = StateGraph[State](State)

graph.add_node("set_up", _set_up_node)
graph.add_node("extract_with_image", _extract_with_image_node)
graph.add_node("extract_with_text", _extract_with_text_node)
graph.add_node("extract_text_ocr", _extract_text_ocr_node)
graph.add_node("image_not_support", _image_not_support_node)

graph.add_edge(START, "set_up")
graph.add_conditional_edges(
    "set_up",
    _if_supports_image,
    {
        True: "extract_with_image",
        False: "image_not_support"
    }
)
graph.add_conditional_edges(
    "image_not_support",
    _if_extraction_succeeded,
    {
        True: "extract_with_text",
        False: "extract_text_ocr"
    }
)
graph.add_edge("extract_text_ocr", "extract_with_text")

graph.add_edge("extract_with_image", END)
graph.add_edge("extract_with_text", END)

agent = graph.compile()

__all__ = [
    agent
]