
import asyncio
from typing import override

from langgraph.types import interrupt
from langgraph.constants import START, END
from langgraph.graph.state import StateGraph
from langchain.messages import HumanMessage, SystemMessage

from schemas.resume_document import ResumeDocument
from exceptions.agent import ModelCallExecutionError
from utils.logger import logger
from utils.custom_events import (
    _adispatch_custom_event_safely,
    _dispatch_custom_event_safely,
)
from schemas.command import BaseCommand
from exceptions.resume import ResumePreviewConversionError
from schemas.model_selection import ModelSelection
from schemas.resume import (
    Resume,
    ResumeFact,
    ResumeFacts,
    ResumeSectionEx,
    ResumeSections,
    ResumeSection
)
from .prompt import (
    validation_system_prompt,
    section_extraction_system_prompt,
    facts_extraction_system_prompt
)
from .state import State
from .model import TextValidation
from ...models.structured import load_structured_model
from ...annotations.types import MaybeCallable
from ...events import ModelCallErrorEvent, ProgressUpdateEvent
from ...base import BaseAgent, BaseInterupt
from ...nodes.wrappers import require_fields


RESUME_STRUCTURED_OUTPUT_METHOD = "function_calling"
class ResumeExtractorAgent(BaseAgent[State]):

    @require_fields('resume_document', 'model', index=1)
    async def _set_up_node(self, state: State) -> State:
        """
        Set up the initial state for the ResumeExtractorAgent.
        """

        _dispatch_custom_event_safely("on_progress_update", ProgressUpdateEvent(
            progress=0.0,
            message="Starting resume extraction.",
        ))

        model: MaybeCallable[ModelSelection] = state.get('model') # type: ignore
        model_selection = model(state) if callable(model) else model
        resume_document: ResumeDocument = state.get('resume_document') # type: ignore

        try:
            resume_text = resume_document.extract_text()
            logger.debug("Extracted text from resume for text-based extraction.")
            _dispatch_custom_event_safely("on_progress_update", ProgressUpdateEvent(
                progress=0.1,
                message="Extracted resume text.",
                additional_data={"text_length": len(resume_text)}
            ))
        except Exception as e:
            raise ResumePreviewConversionError(f"Failed to extract text from resume: {e}")
        
        try:
            resume_images = resume_document.convert_resume_to_image_base64()
            logger.debug(f"Converted resume document to images for image-based extraction. Number of images: {len(resume_images)}")
            _dispatch_custom_event_safely("on_progress_update", ProgressUpdateEvent(
                progress=0.18,
                message="Converted resume document to preview images.",
                additional_data={"image_count": len(resume_images)}
            ))
        except Exception as e:
            raise ResumePreviewConversionError(f"Failed to convert resume to image: {e}")
        
        # Check text extraction result.
        validator = load_structured_model(
            model_selection,
            TextValidation,
            method=RESUME_STRUCTURED_OUTPUT_METHOD,
        )
        
        while True:
            max_retries = self.config.model_call_retry_attempts
            repair_attempts = max(0, max_retries - 1)
            try:
                logger.debug(f"Invoking model for validation of the extracted resume text.")
                validation = await validator.ainvoke(
                    [
                        SystemMessage(content=validation_system_prompt),
                        HumanMessage(content=resume_text)
                    ],
                    max_repair_attempts=repair_attempts,
                )
                
                if validation.is_valid:
                    logger.debug(f"Extracted resume text seems to be valid, reason: {validation.reason or 'No reason provided.'}")
                else:
                    logger.debug(f"Extracted resume text seems to be invalid, reason: {validation.reason or 'No reason provided.'}")

                break
            except Exception as e:
                logger.error(f"Error calling model after {max_retries} attempts:\n{e}")
                _dispatch_custom_event_safely("on_model_call_error", ModelCallErrorEvent(
                    error=str(e),
                    attempt=max_retries,
                    max_attempts=max_retries
                ))

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
                
        _dispatch_custom_event_safely("on_progress_update", ProgressUpdateEvent(
            progress=0.28,
            message="Validated extracted resume text.",
            additional_data={
                "is_valid": validation.is_valid,
                "reason": validation.reason
            }
        ))

        # fall back to OCR-based extraction if text-based extraction is invalid
        if not validation.is_valid:
            logger.debug("Falling back to OCR-based extraction due to invalid text-based extraction.")
            _dispatch_custom_event_safely("on_progress_update", ProgressUpdateEvent(
                progress=0.3,
                message="Falling back to OCR text extraction.",
                additional_data={"reason": validation.reason}
            ))
            try:
                resume_text = resume_document.extract_text_ocr()
                _dispatch_custom_event_safely("on_progress_update", ProgressUpdateEvent(
                    progress=0.36,
                    message="Extracted resume text with OCR.",
                    additional_data={"text_length": len(resume_text)}
                ))
            except Exception as e:
                logger.error(f"Failed to extract text from resume using OCR: {e}")
                raise ResumePreviewConversionError(f"Failed to extract text from resume using OCR: {e}")
            
        return State(
            resume_images=resume_images,
            resume_text=resume_text,
        )
    
    async def _extract_section_node(self, state: State) -> State:
        """
        Extract sections from the resume text.
        """

        model: MaybeCallable[ModelSelection] = state.get('model') # type: ignore
        model_selection = model(state) if callable(model) else model
        resume_text: str = state.get('resume_text') # type: ignore

        logger.debug("Extracting sections from the resume text.")
        _dispatch_custom_event_safely("on_progress_update", ProgressUpdateEvent(
            progress=0.4,
            message="Extracting resume sections.",
        ))  

        extractor = load_structured_model(
            model_selection,
            ResumeSections,
            method=RESUME_STRUCTURED_OUTPUT_METHOD,
        )

        while True:
            max_retries = self.config.model_call_retry_attempts
            repair_attempts = max(0, max_retries - 1)
            try:
                logger.debug(f"Invoking model for extracting sections from the resume text.")
                sections: ResumeSections = await extractor.ainvoke(
                    [
                        SystemMessage(content=section_extraction_system_prompt),
                        HumanMessage(content=resume_text)
                    ],
                    max_repair_attempts=repair_attempts,
                )
                break
            except Exception as e:
                logger.error(f"Error calling model after {max_retries} attempts:\n{e}")
                _dispatch_custom_event_safely("on_model_call_error", ModelCallErrorEvent(
                    error=str(e),
                    attempt=max_retries,
                    max_attempts=max_retries
                ))

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
                
        _dispatch_custom_event_safely("on_progress_update", ProgressUpdateEvent(
            progress=0.55,
            message="Extracted resume sections.",
            additional_data={"section_count": len(sections.sections)}
        ))

        return State(
            sections=sections.sections
        ) 
    
    async def _extract_facts_node(self, state: State) -> State:
        """
        Extract facts from each resume section.
        """

        logger.debug("Extracting facts from each resume section.")

        model: MaybeCallable[ModelSelection] = state.get('model') # type: ignore
        model_selection = model(state) if callable(model) else model
        sections: list[ResumeSectionEx] = state.get('sections') # type: ignore
        total_sections = len(sections)
        sections_with_facts = []
        extractor = load_structured_model(
            model_selection,
            ResumeFacts,
            method=RESUME_STRUCTURED_OUTPUT_METHOD,
        )
        await _adispatch_custom_event_safely("on_progress_update", ProgressUpdateEvent(
            progress=0.6,
            message="Extracting facts from resume sections.",
            additional_data={"section_count": total_sections}
        ))

        async def _extract_facts_for_section(section: ResumeSectionEx) -> ResumeSection | None:
            section_text = (
                f"[section_id]\n{section.section_id}\n\n"
                f"[title]\n{section.title}\n\n"
                f"[content]\n{section.content}"
            )
            while True:
                try:
                    logger.debug(f"Invoking model for extracting facts from section: {section.title}")
                    await _adispatch_custom_event_safely("on_progress_update", ProgressUpdateEvent(
                        progress=0.65,
                        message=f"Extracting facts from section: {section.title}",
                        additional_data={"section_title": section.title}
                    ))
                    facts: ResumeFacts = await extractor.ainvoke([
                        SystemMessage(content=facts_extraction_system_prompt),
                        HumanMessage(content=section_text)
                    ], max_repair_attempts=max(0, self.config.model_call_retry_attempts - 1))

                    await _adispatch_custom_event_safely("on_progress_update", ProgressUpdateEvent(
                        progress=0.65,
                        message=f"Extracted facts from section: {section.title}",
                        additional_data={
                            "section_title": section.title,
                            "fact_count": len(
                                [
                                    fact
                                    for fact in facts.facts
                                    if fact.section_id == section.section_id
                                ]
                            )
                        }
                    ))
                    return ResumeSection(
                        title=section.title,
                        content=section.content,
                        facts=[
                            ResumeFact(
                                fact_type=fact.fact_type,
                                text=fact.text,
                                evidence=fact.evidence,
                                keywords=fact.keywords,
                            )
                            for fact in facts.facts
                            if fact.section_id == section.section_id
                        ]
                    )
                except Exception as e:
                    logger.error(f"Error calling model for section {section.title}:\n{e}")
                    await _adispatch_custom_event_safely("on_model_call_error", ModelCallErrorEvent(
                        error=str(e),
                        attempt=1,
                        max_attempts=1,
                        additional_data={"section_title": section.title}
                    ))
                    await _adispatch_custom_event_safely("on_progress_update", ProgressUpdateEvent(
                        progress=0.65,
                        message=f"Failed to extract facts from section: {section.title}",
                        additional_data={"section_title": section.title}
                    ))
                    return None

        while True:
            max_retries = self.config.model_call_retry_attempts
            for _ in range(max_retries):
                results = await asyncio.gather(*(_extract_facts_for_section(section) for section in sections))

                sections_with_facts.extend([result for result in results if result is not None])
                completed_sections = len(sections_with_facts)
                failed_sections = sum(1 for result in results if result is None)
                progress = 0.65 + (0.3 * completed_sections / total_sections) if total_sections else 0.95
                await _adispatch_custom_event_safely("on_progress_update", ProgressUpdateEvent(
                    progress=min(progress, 0.95),
                    message="Updated resume fact extraction progress.",
                    additional_data={
                        "completed_section_count": completed_sections,
                        "failed_section_count": failed_sections,
                        "total_section_count": total_sections
                    }
                ))
                if all(result is not None for result in results):
                    await _adispatch_custom_event_safely("on_progress_update", ProgressUpdateEvent(
                        progress=1.0,
                        message="Completed resume extraction.",
                        additional_data={
                            "section_count": len(sections_with_facts),
                            "fact_count": sum(len(section.facts) for section in sections_with_facts)
                        }
                    ))
                    return State(
                        resume=Resume(
                            raw_text=state.get('resume_text'), # type: ignore
                            document=state.get('resume_document'), # type: ignore
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
        graph.add_node("set_up", self._set_up_node)
        graph.add_node("extract_section", self._extract_section_node)
        graph.add_node("extract_facts", self._extract_facts_node)

        graph.add_edge(START, "set_up")
        graph.add_edge("set_up", "extract_section")
        graph.add_edge("extract_section", "extract_facts")
        graph.add_edge("extract_facts", END)

        return graph
