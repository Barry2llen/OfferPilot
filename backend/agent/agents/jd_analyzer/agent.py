
import asyncio
from typing import Sequence, override

from langgraph.types import interrupt
from langgraph.constants import START, END
from langgraph.graph.state import StateGraph
from langchain_core.runnables import Runnable
from langchain.messages import HumanMessage, SystemMessage
from langchain_core.language_models import LanguageModelInput

from exceptions.agent import ModelCallExecutionError
from utils import document_parser
from utils.logger import logger
from utils.custom_events import (
    _adispatch_custom_event_safely,
    _dispatch_custom_event_safely,
)
from schemas.config import Config
from ...compaction import Compactor, ContextBudgetPolicy
from schemas.command import BaseCommand
from schemas.model_selection import ModelSelection
from schemas.job_description import (
    JobDescription,
    JobDescriptionEx,
    JdFact,
    JdFactsEx,
    JdRequirementBlock,
    JdRequirementBlockEx,
    JdSalary,
)
from .state import State
from .prompt import (
    jd_web_search_system_prompt,
    jd_extraction_system_prompt,
    jd_facts_extraction_system_prompt,
)
from .tool import mark_jd_extraction_failure, mark_jd_extraction_success
from ...graphs.model_call import ModelCallGraph
from ...tools import get_tools
from ...annotations.types import MaybeCallable
from ...events import ModelCallErrorEvent, ProgressUpdateEvent
from ...base import BaseAgent, BaseInterupt
from ...models import load_structured_model


_FACT_EXTRACTION_CONCURRENCY = 5
JD_STRUCTURED_OUTPUT_METHOD = "function_calling"


async def _get_jd_source_tools(config: Config | None = None):
    return (
        *await get_tools("web_fetch", "get_content", config=config),
        mark_jd_extraction_success,
        mark_jd_extraction_failure,
    )


def _message_content_to_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
                continue
            if isinstance(block, str):
                parts.append(block)
        return " ".join(parts)
    return str(content) if content is not None else ""


def _messages_to_text(messages: Sequence[object]) -> str:
    parts: list[str] = []
    for message in messages:
        content = getattr(message, "content", None)
        text = _message_content_to_text(content).strip()
        if not text:
            continue
        message_type = getattr(message, "type", "message")
        parts.append(f"[{message_type}]\n{text}")
    return "\n\n".join(parts)


def _normalize_images(images: object) -> list[str]:
    if images is None:
        return []
    if not isinstance(images, list):
        return []
    return [image.strip() for image in images if isinstance(image, str) and image.strip()]


def _image_data_url_to_content_block(data_url: str) -> dict[str, object]:
    document_parser.decode_image_data_url(data_url)
    return {
        "type": "image_url",
        "image_url": {"url": data_url},
    }

class JdAnalyzerAgent(BaseAgent[State]):

    def __init__(
        self,
        *args,
        config: Config | None = None,
        compactor: Compactor[State] | None = None,
        context_budget_policy: ContextBudgetPolicy | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, config=config, **kwargs)

        self._model_call_node = ModelCallGraph[State](
            *args,
            **kwargs,
            system_prompts=jd_web_search_system_prompt,
            config=config,
            tools=lambda runtime: _get_jd_source_tools(config),
            compactor=compactor,
            context_budget_policy=context_budget_policy,
        ).get_compiled_graph()

    def _prepare_jd_source_node(self, state: State) -> State:
        """
        Build a single JD acquisition prompt from explicit text, URL, images, and
        current messages before the model_call subgraph runs.
        """
        _dispatch_custom_event_safely(
            "on_progress_update",
            ProgressUpdateEvent(
                progress=0.05,
                message="Preparing JD source inputs.",
            ),
        )

        model: MaybeCallable[ModelSelection] = state.get("model")  # type: ignore
        model_selection = model(state) if callable(model) else model
        supports_image_input = bool(
            getattr(model_selection, "supports_image_input", False)
        )

        jd_text = state.get("jd_text")
        source_url = state.get("source_url")
        images = _normalize_images(state.get("images"))
        message_text = _messages_to_text(state.get("messages", []))

        source_parts: list[str] = [
            "Extract the complete original job description from the sources below.",
            "Use only explicitly provided sources. Do not search for a JD unless a source URL is present.",
        ]
        if source_url and source_url.strip():
            source_parts.append(f"[source_url]\n{source_url.strip()}")
        if jd_text and jd_text.strip():
            source_parts.append(f"[jd_text]\n{jd_text.strip()}")
        if message_text:
            source_parts.append(f"[current_messages]\n{message_text}")
        if images:
            source_parts.append(
                f"[images]\n{len(images)} image(s) were provided."
            )
        if len(source_parts) == 2 and not images:
            source_parts.append("[empty]\nNo JD source was provided.")

        content_blocks: list[dict[str, object]] = [
            {"type": "text", "text": "\n\n".join(source_parts)}
        ]

        if images and supports_image_input:
            content_blocks.extend(
                _image_data_url_to_content_block(image) for image in images
            )
        elif images:
            ocr_parts: list[str] = []
            for index, image in enumerate(images, start=1):
                # When images are provided and needs ocr, the process of ocr is probably already done by services.
                # So here we support both raw image data url and ocr text as input, and if it's image data url, we will do ocr to extract text and include in the prompt.
                ocr_text = (
                    document_parser.extract_image_data_url_ocr(image)
                    if document_parser.is_image_data_url(image)
                    else image
                )
                ocr_parts.append(
                    f"[image_{index}_ocr]\n{ocr_text.strip() if ocr_text else ''}"
                )
            content_blocks.append(
                {
                    "type": "text",
                    "text": "\n\n".join(ocr_parts),
                }
            )

        _dispatch_custom_event_safely(
            "on_progress_update",
            ProgressUpdateEvent(
                progress=0.12,
                message="Prepared JD source inputs.",
                additional_data={
                    "has_jd_text": bool(jd_text and jd_text.strip()),
                    "has_source_url": bool(source_url and source_url.strip()),
                    "image_count": len(images),
                    "used_image_input": bool(images and supports_image_input),
                },
            ),
        )

        return State(
            messages=[
                HumanMessage(content=content_blocks), # type: ignore
            ],
            source_url=source_url,
            images=images,
        )

    def _parse_jd_text_node(self, state: State) -> State:
        """
        Parse jd_text from the JD extraction marker tool called by model_call.
        """
        source_url = state.get("source_url")
        messages = state.get("messages", [])
        tool_name = ""
        tool_content = ""
        for msg in reversed(messages):
            if getattr(msg, "type", "") == "tool":
                tool_name = getattr(msg, "name", "") or ""
                tool_content = _message_content_to_text(getattr(msg, "content", None)).strip()
                break

        if not tool_name:
            logger.warning("No JD extraction marker tool call found.")
            error_message = "JD extraction failed: missing marker tool call."
            _dispatch_custom_event_safely(
                "on_progress_update",
                ProgressUpdateEvent(
                    progress=1.0,
                    message=error_message,
                ),
            )
            return State(jd_text=None, source_url=source_url, jd_error=error_message)

        if tool_name == mark_jd_extraction_failure.name:
            error_message = tool_content or "JD extraction failed."
            logger.info(f"JD extraction failed: {error_message[:200]}")
            _dispatch_custom_event_safely(
                "on_progress_update",
                ProgressUpdateEvent(
                    progress=1.0,
                    message="JD extraction failed.",
                    additional_data={"reason": error_message[:500]},
                ),
            )
            return State(jd_text=None, source_url=source_url, jd_error=error_message)

        if tool_name == mark_jd_extraction_success.name and tool_content:
            _dispatch_custom_event_safely(
                "on_progress_update",
                ProgressUpdateEvent(
                    progress=0.15,
                    message="Extracted JD text from marker tool.",
                    additional_data={"text_length": len(tool_content)},
                ),
            )
            return State(jd_text=tool_content, source_url=source_url)

        logger.warning(f"Unexpected or empty JD extraction tool result: {tool_name}")
        error_message = "JD extraction failed: invalid marker tool result."
        _dispatch_custom_event_safely(
            "on_progress_update",
            ProgressUpdateEvent(
                progress=1.0,
                message=error_message,
                additional_data={
                    "tool_name": tool_name,
                    "text_length": len(tool_content),
                },
            ),
        )
        return State(jd_text=None, source_url=source_url, jd_error=error_message)

    def _should_continue(self, state: State) -> str:
        """Route: if jd_text was extracted, continue to structure extraction; otherwise end."""
        jd_text = state.get("jd_text")
        if jd_text and jd_text.strip():
            return "extract_structure"
        return "end"

    async def _extract_structure_node(self, state: State) -> State:
        """
        Extract flat structured fields and blocks from JD text using a single model call.
        """
        await _adispatch_custom_event_safely(
            "on_progress_update",
            ProgressUpdateEvent(progress=0.2, message="Starting JD structure extraction."),
        )

        model: MaybeCallable[ModelSelection] = state.get("model")  # type: ignore
        model_selection = model(state) if callable(model) else model
        jd_text: str = state.get("jd_text")  # type: ignore

        while True:
            max_retries = self.config.model_call_retry_attempts
            repair_attempts = max(0, max_retries - 1)
            try:
                extractor = load_structured_model(
                    model_selection,
                    JobDescriptionEx,
                    method=JD_STRUCTURED_OUTPUT_METHOD,
                )
                logger.debug("Invoking model for JD structure extraction.")
                result = await extractor.ainvoke(
                    [
                        SystemMessage(content=jd_extraction_system_prompt),
                        HumanMessage(content=jd_text),
                    ],
                    max_repair_attempts=repair_attempts,
                )
                break
            except Exception as e:
                logger.error(
                    f"Error calling model for JD extraction after {max_retries} attempts:\n{e}"
                )
                await _adispatch_custom_event_safely(
                    "on_model_call_error",
                    ModelCallErrorEvent(
                        error=str(e), attempt=max_retries, max_attempts=max_retries
                    ),
                )

            logger.error(f"Model call failed after {max_retries} retries for JD extraction.")
            resp: BaseCommand = interrupt(
                BaseInterupt(
                    type="error",
                    message=f"Model call failed after {max_retries} retries for extracting JD structure.",
                )
            )
            match resp["type"]:
                case "retry":
                    continue
                case _:
                    raise ModelCallExecutionError(
                        f"Model call failed after {max_retries} retries and received interrupt "
                        f"with type {resp['type']} and message {resp.get('prompt', '')}"
                    )

        await _adispatch_custom_event_safely(
            "on_progress_update",
            ProgressUpdateEvent(
                progress=0.5,
                message="Extracted JD structure.",
                additional_data={
                    "job_title": result.job_title,
                    "block_count": len(result.blocks),
                },
            ),
        )

        return State(
            jd_extracted=result,
            blocks=result.blocks,
        )

    async def _extract_facts_node(self, state: State) -> State:
        """
        Extract facts from each JD block (parallel). Symmetric to resume fact extraction.
        """
        model: MaybeCallable[ModelSelection] = state.get("model")  # type: ignore
        model_selection = model(state) if callable(model) else model
        jd_extracted: JobDescriptionEx = state.get("jd_extracted")  # type: ignore
        blocks: list[JdRequirementBlockEx] = state.get("blocks")  # type: ignore
        source_url: str | None = state.get("source_url")
        jd_text: str = state.get("jd_text")  # type: ignore
        total_blocks = len(blocks)

        await _adispatch_custom_event_safely(
            "on_progress_update",
            ProgressUpdateEvent(
                progress=0.55,
                message="Extracting facts from JD blocks.",
                additional_data={"block_count": total_blocks},
            ),
        )

        if total_blocks == 0:
            job_description = self._build_final_result(jd_extracted, [], jd_text, source_url)
            await _adispatch_custom_event_safely(
                "on_progress_update",
                ProgressUpdateEvent(progress=1.0, message="Completed JD analysis (no blocks)."),
            )
            return State(job_description=job_description)

        blocks_with_facts: dict[int, JdRequirementBlock] = {}
        semaphore = asyncio.Semaphore(_FACT_EXTRACTION_CONCURRENCY)

        async def _extract_facts_for_block(
            index: int,
            block: JdRequirementBlockEx,
            extractor: Runnable[LanguageModelInput, JdFactsEx],
        ) -> tuple[int, JdRequirementBlock | None]:
            block_text = (
                f"[block_id]\n{block.block_id}\n\n"
                f"[block_type]\n{block.block_type}\n\n"
                f"[title]\n{block.title}\n\n"
                f"[content]\n{block.content}"
            )
            try:
                logger.debug(f"Extracting facts from JD block: {block.title}")
                async with semaphore:
                    facts_result: JdFactsEx = await extractor.ainvoke(
                        [
                            SystemMessage(content=jd_facts_extraction_system_prompt),
                            HumanMessage(content=block_text),
                        ],
                        max_repair_attempts=max(0, self.config.model_call_retry_attempts - 1),
                    )

                return (
                    index,
                    JdRequirementBlock(
                        block_type=block.block_type,
                        title=block.title,
                        content=block.content,
                        facts=[
                            JdFact(
                                fact_type=fact.fact_type,
                                custom_fact_type=fact.custom_fact_type,
                                importance=fact.importance,
                                text=fact.text,
                                evidence=fact.evidence,
                                keywords=fact.keywords,
                            )
                            for fact in facts_result.facts
                            if fact.block_id == block.block_id
                        ],
                    ),
                )
            except Exception as e:
                logger.error(f"Error extracting facts from JD block '{block.title}': {e}")
                await _adispatch_custom_event_safely(
                    "on_model_call_error",
                    ModelCallErrorEvent(
                        error=str(e),
                        attempt=1,
                        max_attempts=1,
                        additional_data={"block_title": block.title},
                    ),
                )
                return (index, None)

        # Retry loop
        remaining_blocks = list(enumerate(blocks))
        while True:
            max_retries = self.config.model_call_retry_attempts
            for attempt in range(max_retries):
                try:
                    extractor = load_structured_model(
                        model_selection,
                        JdFactsEx,
                        method=JD_STRUCTURED_OUTPUT_METHOD,
                    )
                except Exception as e:
                    logger.error(
                        f"Error loading model for JD fact extraction, attempt {attempt + 1}/{max_retries}:\n{e}"
                    )
                    await _adispatch_custom_event_safely(
                        "on_model_call_error",
                        ModelCallErrorEvent(
                            error=str(e), attempt=attempt + 1, max_attempts=max_retries
                        ),
                    )
                    continue

                results = await asyncio.gather(
                    *(
                        _extract_facts_for_block(index, block, extractor)
                        for index, block in remaining_blocks
                    )
                )

                for index, result in results:
                    if result is not None:
                        blocks_with_facts[index] = result

                failed_indexes = {index for index, result in results if result is None}

                completed = len(blocks_with_facts)
                progress = 0.55 + (0.4 * completed / total_blocks) if total_blocks else 0.95
                await _adispatch_custom_event_safely(
                    "on_progress_update",
                    ProgressUpdateEvent(
                        progress=min(progress, 0.95),
                        message="Extracting JD block facts.",
                        additional_data={
                            "completed_blocks": completed,
                            "failed_blocks": len(failed_indexes),
                            "total_blocks": total_blocks,
                        },
                    ),
                )

                if not failed_indexes:
                    ordered_blocks = [blocks_with_facts[index] for index in range(total_blocks)]
                    job_description = self._build_final_result(
                        jd_extracted, ordered_blocks, jd_text, source_url
                    )
                    await _adispatch_custom_event_safely(
                        "on_progress_update",
                        ProgressUpdateEvent(
                            progress=1.0,
                            message="Completed JD analysis.",
                            additional_data={
                                "block_count": len(ordered_blocks),
                                "fact_count": sum(
                                    len(b.facts) for b in ordered_blocks
                                ),
                            },
                        ),
                    )
                    return State(job_description=job_description)

                remaining_blocks = [
                    (index, block)
                    for index, block in remaining_blocks
                    if index in failed_indexes
                ]
                logger.debug(
                    f"Retrying fact extraction for blocks: "
                    f"{[block.title for _, block in remaining_blocks]}, "
                    f"attempt {attempt + 1}/{max_retries}."
                )

            # All retries exhausted
            resp: BaseCommand = interrupt(
                BaseInterupt(
                    type="error",
                    message=(
                        f"Model call failed after {max_retries} retries for extracting "
                        f"facts from some JD blocks."
                    ),
                )
            )
            match resp["type"]:
                case "retry":
                    continue
                case _:
                    raise ModelCallExecutionError(
                        f"Model call failed after {max_retries} retries and received interrupt "
                        f"with type {resp['type']} and message {resp.get('prompt', '')}"
                    )

    def _build_final_result(
        self,
        extracted: JobDescriptionEx,
        blocks_with_facts: list[JdRequirementBlock],
        raw_text: str,
        source_url: str | None,
    ) -> JobDescription:
        return JobDescription(
            raw_text=raw_text,
            source_url=source_url,
            company_name=extracted.company_name,
            company_industry=extracted.company_industry,
            company_size=extracted.company_size,
            job_title=extracted.job_title,
            job_level=extracted.job_level,
            job_family=extracted.job_family,
            primary_location=extracted.primary_location,
            locations=extracted.locations,
            remote_policy_raw=extracted.remote_policy_raw,
            employment_type_raw=extracted.employment_type_raw,
            experience_raw=extracted.experience_raw,
            years_experience_min=extracted.years_experience_min,
            years_experience_max=extracted.years_experience_max,
            education_raw=extracted.education_raw,
            education_min_rank=extracted.education_min_rank,
            major_requirement=extracted.major_requirement,
            salary=JdSalary(
                raw=extracted.salary_raw,
                min_monthly=extracted.salary_min_monthly,
                max_monthly=extracted.salary_max_monthly,
                months_per_year=extracted.salary_months_per_year,
                currency=extracted.salary_currency,
            ) if (
                extracted.salary_raw
                or extracted.salary_min_monthly is not None
                or extracted.salary_max_monthly is not None
                or extracted.salary_months_per_year is not None
                or extracted.salary_currency is not None
            ) else None,
            benefits=extracted.benefits,
            blocks=blocks_with_facts,
        )

    @override
    def get_graph(self) -> StateGraph[State]:
        graph = StateGraph[State](State)

        # Node 1: Prepare explicit text, URL, image, and message sources.
        graph.add_node("prepare_jd_source", self._prepare_jd_source_node)
        # Node 2: ModelCallGraph sub-graph — uses tools (web fetch) to obtain JD raw text
        graph.add_node("model_call", self._model_call_node)
        # Node 3: Parse jd_text from model_call AI response
        graph.add_node("parse_jd_text", self._parse_jd_text_node)
        # Node 4: Structured extraction
        graph.add_node("extract_structure", self._extract_structure_node)
        # Node 5: Fact extraction (parallel per block)
        graph.add_node("extract_facts", self._extract_facts_node)

        # Edges
        graph.add_edge(START, "prepare_jd_source")
        graph.add_edge("prepare_jd_source", "model_call")
        graph.add_edge("model_call", "parse_jd_text")
        graph.add_conditional_edges(
            "parse_jd_text",
            self._should_continue,
            {
                "extract_structure": "extract_structure",
                "end": END,
            },
        )
        graph.add_edge("extract_structure", "extract_facts")
        graph.add_edge("extract_facts", END)

        return graph
