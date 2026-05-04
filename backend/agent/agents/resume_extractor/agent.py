
import asyncio
from typing import override

from langgraph.types import interrupt
from langgraph.constants import START, END
from langgraph.graph.state import StateGraph
from langchain.messages import HumanMessage, SystemMessage
from langchain_core.callbacks.manager import adispatch_custom_event, dispatch_custom_event

from backend.exceptions.agent import ModelCallExecutionError
from utils.logger import logger
from schemas.command import BaseCommand
from exceptions.resume import ResumePreviewConversionError
from exceptions.validation import ValidationError
from schemas.resume import (
    Resume,
    ResumeFacts,
    ResumeFact,
    ResumeSectionEx,
    ResumeSections,
    ResumeSection
)
from backend.schemas.command import BaseCommand
from .prompt import (
    validation_system_prompt,
    section_extraction_system_prompt,
    facts_extraction_system_prompt
)
from .state import State
from .model import TextValidation
from ...events import ModelCallErrorEvent, ProgressUpdateEvent
from ...base import BaseAgent, BaseInterupt
from ...nodes.wrappers import require_fields
from ...models import load_chat_model

class ResumeExtractorAgent(BaseAgent[State]):

    @require_fields('resume_document', 'model', index=1)
    def _set_up_node(self, state: State) -> State:
        """
        Set up the initial state for the ResumeExtractorAgent.
        """

        dispatch_custom_event("on_progress_update", ProgressUpdateEvent(
            progress=0.0,
        ))

        model_selection = state['model'](state) if callable(state['model']) else state['model']
        resume_document = state["resume_document"]

        try:
            resume_text = resume_document.extract_text()
            logger.debug("Extracted text from resume for text-based extraction.")
        except Exception as e:
            raise ResumePreviewConversionError(f"Failed to extract text from resume: {e}")
        
        try:
            resume_images = resume_document.convert_resume_to_image_base64()
            logger.debug(f"Converted resume document to images for image-based extraction. Number of images: {len(resume_images)}")
        except Exception as e:
            raise ResumePreviewConversionError(f"Failed to convert resume to image: {e}")
        
        # Check text extraction result.
        validator = load_chat_model(model_selection).with_structured_output(TextValidation)
        while True:
            flag = False
            max_retries = self.config.model_call_retry_attempts
            for _ in range(max_retries):
                try:
                    logger.debug(f"Invoking model for validation of the extracted resume text.")
                    validation = validator.invoke([
                        SystemMessage(content=validation_system_prompt),
                        HumanMessage(content=resume_text)
                    ])

                    if not isinstance(validation, TextValidation):
                        logger.debug(f"Validation result is not in the expected format, result: {validation}")
                        raise ValidationError(f"Validation result is not in the expected format.")
                    
                    if validation.is_valid:
                        logger.debug(f"Extracted resume text seems to be valid, reason: {validation.reason or 'No reason provided.'}")
                    else:
                        logger.debug(f"Extracted resume text seems to be invalid, reason: {validation.reason or 'No reason provided.'}")

                    flag = True
                    break
                except Exception as e:
                    logger.error(f"Error calling model, retries in progress {_+1}/{max_retries}:\n{e}")
                    dispatch_custom_event("on_model_call_error", ModelCallErrorEvent(
                        error=str(e),
                        attempt=_+1,
                        max_attempts=max_retries
                    ))

            if flag:
                break

            logger.error(f"Model call failed after {max_retries} retries.")
            
            resp: BaseCommand = interrupt(BaseInterupt(type='error', message=f"Model call failed after {max_retries} retries for extracting sections from the resume text."))

            match resp['type']:
                case 'retry':
                    continue
                case _:
                    raise ModelCallExecutionError(
                        "Model call failed after "
                        f"{max_retries} retries and code received interrupt with type "
                        f"{resp['type']} and message {resp.get('prompt', '')}"
                    )
                
        # fall back to OCR-based extraction if text-based extraction is invalid
        if not validation.is_valid:
            logger.debug("Falling back to OCR-based extraction due to invalid text-based extraction.")
            try:
                resume_text = resume_document.extract_text_ocr()
            except Exception as e:
                logger.error(f"Failed to extract text from resume using OCR: {e}")
                raise ResumePreviewConversionError(f"Failed to extract text from resume using OCR: {e}")
            
        return State(
            resume_images=resume_images,
            resume_text=resume_text,
        )
    
    def _extract_section_node(self, state: State) -> State:
        """
        Extract sections from the resume text.
        """

        model_selection = state['model'](state) if callable(state['model']) else state['model']
        resume_text = state['resume_text']

        logger.debug("Extracting sections from the resume text.")

        extractor = load_chat_model(model_selection).with_structured_output(ResumeSections)
        while True:
            flag = False
            max_retries = self.config.model_call_retry_attempts
            for _ in range(max_retries):
                try:
                    logger.debug(f"Invoking model for extracting sections from the resume text.")
                    sections: ResumeSections = extractor.invoke([
                        SystemMessage(content=section_extraction_system_prompt),
                        HumanMessage(content=resume_text)
                    ])

                    if not isinstance(sections, ResumeSections):
                        logger.debug(f"Sections result is not in the expected format, result: {sections}")
                        raise ValidationError(f"Sections result is not in the expected format.")

                    flag = True
                    break
                except Exception as e:
                    logger.error(f"Error calling model, retries in progress {_+1}/{max_retries}:\n{e}")
                    dispatch_custom_event("on_model_call_error", ModelCallErrorEvent(
                        error=str(e),
                        attempt=_+1,
                        max_attempts=max_retries
                    ))

            if flag:
                break

            logger.error(f"Model call failed after {max_retries} retries.")
            
            resp: BaseCommand = interrupt(BaseInterupt(type='error', message=f"Model call failed after {max_retries} retries for extracting sections from the resume text."))

            match resp['type']:
                case 'retry':
                    continue
                case _:
                    raise ModelCallExecutionError(
                        "Model call failed after "
                        f"{max_retries} retries and code received interrupt with type "
                        f"{resp['type']} and message {resp.get('prompt', '')}"
                    )
                
        return State(
            sections=sections.sections
        ) 
    
    async def _extract_facts_node(self, state: State) -> State:
        """
        Extract facts from each resume section.
        """

        logger.debug("Extracting facts from each resume section.")

        model_selection = state['model'](state) if callable(state['model']) else state['model']
        sections = state['sections']
        sections_with_facts = []
        extractor = load_chat_model(model_selection).with_structured_output(ResumeFacts)

        async def _extract_facts_for_section(section: ResumeSectionEx) -> ResumeSection:
            section_text = str(section)
            while True:
                try:
                    logger.debug(f"Invoking model for extracting facts from section: {section.title}")
                    facts: ResumeFacts = await extractor.ainvoke([
                        SystemMessage(content=facts_extraction_system_prompt),
                        HumanMessage(content=section_text)
                    ])

                    if not isinstance(facts, ResumeFacts):
                        logger.debug(f"Facts result is not in the expected format, result: {facts}")
                        raise ValidationError(f"Facts result is not in the expected format.")

                    return ResumeSection(
                        title=section.title,
                        content=section.content,
                        facts=facts.facts
                    )
                except Exception as e:
                    logger.error(f"Error calling model for section {section.title}:\n{e}")
                    await adispatch_custom_event("on_model_call_error", ModelCallErrorEvent(
                        error=str(e),
                        attempt=1,
                        max_attempts=1,
                        additional_data={"section_title": section.title}
                    ))
                    return None

        while True:
            max_retries = self.config.model_call_retry_attempts
            for _ in range(max_retries):
                results = await asyncio.gather(*(_extract_facts_for_section(section) for section in sections))

                sections_with_facts.extend([result for result in results if result is not None])
                if all(result is not None for result in results):
                    return State(
                        resume=Resume(
                            raw_text=state['resume_text'],
                            document=state['resume_document'],
                            sections=sections_with_facts
                        )
                    )

                error_indexes = [i for i, result in enumerate(results) if result is None]
                sections = [sections[i] for i in error_indexes]

                logger.debug(f"Error occurred while extracting facts for some sections: {[section.title for section in sections]}. Retrying for these sections, attempt {_+1}/{max_retries}.")

            resp: BaseCommand = interrupt(BaseInterupt(type='error', message=f"Model call failed after {max_retries} retries for extracting facts from some sections of the resume."))

            match resp['type']:
                case 'retry':
                    continue
                case _:
                    raise ModelCallExecutionError(
                        "Model call failed after "
                        f"{max_retries} retries and code received interrupt with type "
                        f"{resp['type']} and message {resp.get('prompt', '')}"
                    )

    @override
    def get_graph(self) -> StateGraph[State]:
        graph = StateGraph[State](State)
        # TODO: complete the graph construction with proper edges and nodes
        return graph
