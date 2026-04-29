from pydantic import BaseModel, Field
from typing import override

from langgraph.constants import START, END
from langgraph.graph.state import StateGraph
from langchain.messages import HumanMessage, SystemMessage

from utils.logger import logger
from exceptions.resume import ResumePreviewConversionError
from schemas.resume_profile import ResumeProfile
from .state import State
from ...base import BaseAgent
from ...nodes.wrappers import require_fields
from ...models import load_chat_model

class ResumeExtractorAgent(BaseAgent[State]):
    """
    Agent for extracting structured information from resumes.
    The agent will first try to use a model that supports image input to extract information from the resume images.
    If the model does not support image input, it will fall back to using text extraction.
    If the text extraction fails, it will then try to use OCR on the resume images to extract text and then use that text for information extraction.
    """

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

    @require_fields('resume_document', 'model', index=1)
    def _set_up_node(self, state: State) -> State:
        """
        Set up the initial state for the ResumeExtractorAgent.
        """

        logger.debug("Setting up the ResumeExtractorAgent with the provided resume document and model selection.")

        model_selection = state['model'](state) if callable(state['model']) else state['model']
        state['structured_output_model'] = load_chat_model(model_selection).with_structured_output(ResumeProfile)

        resume_document = state["resume_document"]

        if model_selection.supports_image_input:
            try:
                state["resume_images"] = resume_document.convert_resume_to_image_base64()
                logger.debug(f"Converted resume document to images for image-based extraction. Number of images: {len(state['resume_images'])}")
            except Exception as e:
                raise ResumePreviewConversionError(f"Failed to convert resume to image: {e}")
        
        if not model_selection.supports_image_input:
            try:
                state["resume_text"] = resume_document.extract_text()
                logger.debug("Extracted text from resume for text-based extraction.")
            except Exception as e:
                raise ResumePreviewConversionError(f"Failed to extract text from resume: {e}")
            
        return state

    def _if_supports_image(self, state: State) -> bool:
        """
        Check if the selected model supports image input.
        """
        return state["model"].supports_image_input if state.get("model") else False

    def _extract_with_image_node(self, state: State) -> State:
        """
        Extract information from the resume using the model that supports image input.
        """
        model = state["structured_output_model"]
        resume_images = state["resume_images"]

        if not resume_images:
            raise ResumePreviewConversionError("No resume images available for extraction.")

        message_content = [
            {
                "type": "text",
                "text": "Please extract structured information from these resume images.",
            },
            *[
                {"type": "image_url", "image_url": {"url": image}}
                for image in resume_images
            ],
        ]

        # Call the model with the system message and the resume images
        logger.debug(f"Invoking model for image-based extraction.")
        response = model.invoke([
            self.structured_output_system_prompt,
            HumanMessage(content=message_content),
        ])
        
        return State(resume_profile=response)

    def _image_not_support_node(self, state: State) -> State:
        """
        Handle the case when the model does not support image input.
        """
        # do nothing here, just a placeholder node to make the graph complete
        return {}

    def _if_extraction_succeeded(self, state: State) -> bool:
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
        logger.debug(f"Invoking model for validation of the extracted resume profile.")
        validation: Validation = validator.invoke([self.validation_system_prompt, HumanMessage(content=f"{state['resume_text']}")])

        if not isinstance(validation, Validation):
            # TODO: Later we can retry a few times before giving up.
            logger.error(f"Validation result is not in the expected format: {validation}")
            raise ValueError(f"Validation result is not in the expected format: {validation}")
        
        if not validation.is_valid:
            logger.debug("Extracted resume profile is not valid. Reason: " + (validation.reason or "No reason provided."))
        else:
            logger.debug("Extracted resume profile is valid.")

        return validation.is_valid

    def _extract_with_text_node(self, state: State) -> State:
        """
        Extract information from the resume using the model that supports text input.
        """
        model = state["structured_output_model"]
        resume_text = state["resume_text"]

        if not resume_text:
            raise ResumePreviewConversionError("No resume text available for extraction.")

        # Call the model with the system message and the resume text
        logger.debug(f"Invoking model for text-based extraction.")
        response = model.invoke([self.structured_output_system_prompt, HumanMessage(content=resume_text)])

        return State(resume_profile=response)

    def _extract_text_ocr_node(self, state: State) -> State:
        """
        Extract information from the resume using OCR on the resume images.
        """
        
        resume_document = state["resume_document"]
        logger.debug("Attempting to extract text from resume using OCR as a fallback.")
        resume_text = resume_document.extract_text_ocr()

        return State(resume_text=resume_text)
    
    @override
    def get_graph(self) -> StateGraph[State]:
        graph = StateGraph[State](State)

        graph.add_node("set_up", self._set_up_node)
        graph.add_node("extract_with_image", self._extract_with_image_node)
        graph.add_node("extract_with_text", self._extract_with_text_node)
        graph.add_node("extract_text_ocr", self._extract_text_ocr_node)
        graph.add_node("image_not_support", self._image_not_support_node)

        graph.add_edge(START, "set_up")
        graph.add_conditional_edges(
            "set_up",
            self._if_supports_image,
            {
                True: "extract_with_image",
                False: "image_not_support"  
            }
        )
        graph.add_conditional_edges(
            "image_not_support",
            self._if_extraction_succeeded,
            {
                True: "extract_with_text",
                False: "extract_text_ocr"
            }
        )
        graph.add_edge("extract_text_ocr", "extract_with_text")

        graph.add_edge("extract_with_image", END)
        graph.add_edge("extract_with_text", END)

        return graph
