from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from contextlib import aclosing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain.tools import BaseTool, ToolRuntime, tool
from pydantic import BaseModel, Field

from db.engine.manager import DatabaseManager
from db.repositories import (
    ChatFileRepository,
    ChatThreadFileRepository,
    JobDescriptionAnalysisRepository,
    ResumeDocumentRepository,
    ResumeExtractionRepository,
)
from exceptions import ChatFileProcessingError
from schemas.config import Config
from schemas.resume_document import ResumeDetail, ResumeDocument
from services.analysis_job_events import AnalysisJobEvent
from services.chat_file_service import ChatFileService
from services.jd_analysis_jobs import JdAnalysisJobManager
from services.job_description_analysis_service import JobDescriptionAnalysisService
from services.resume_extraction_jobs import ResumeExtractionJobManager
from services.resume_service import ResumeService, UploadedResumeFile
from utils.custom_events import _adispatch_custom_event_safely
from utils.i18n import Locale, localize_error, resolve_locale


@dataclass(slots=True, frozen=True)
class AnalysisToolDependencies:
    config: Config
    database: DatabaseManager
    resume_jobs: ResumeExtractionJobManager
    jd_jobs: JdAnalysisJobManager


def _locale(runtime: ToolRuntime[None, dict[str, Any]]) -> Locale:
    configurable = runtime.config.get("configurable", {})
    value = configurable.get("locale") if isinstance(configurable, dict) else None
    return resolve_locale(value if isinstance(value, str) else None)


def _model_selection(runtime: ToolRuntime[None, dict[str, Any]]) -> tuple[Any, int]:
    selection = runtime.state.get("model")
    if callable(selection):
        selection = selection(state=runtime.state)

    selection_id = getattr(selection, "id", None)
    if selection is None or not isinstance(selection_id, int):
        raise ValueError("A model selection is required for analysis.")
    return selection, selection_id


def _model_dump(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def _resource_id(resource_type: str, data: dict[str, Any], fallback: int) -> int:
    key = "resume" if resource_type == "resume" else "job_description"
    value = _model_dump(data.get(key))
    if isinstance(value, dict) and isinstance(value.get("id"), int):
        return value["id"]
    for candidate in (data.get("resume_id"), data.get("analysis_id")):
        if isinstance(candidate, int):
            return candidate
    return fallback


async def _forward_event(
    runtime: ToolRuntime[None, dict[str, Any]],
    *,
    tool_name: str,
    resource_type: str,
    resource_id: int,
    event: AnalysisJobEvent,
) -> None:
    await _adispatch_custom_event_safely(
        "on_analysis_job_event",
        {
            "tool_name": tool_name,
            "tool_call_id": runtime.tool_call_id,
            "resource_type": resource_type,
            "resource_id": _resource_id(resource_type, event.data, resource_id),
            "event": event.event,
            **event.data,
        },
    )


async def _wait_for_job(
    events: AsyncGenerator[AnalysisJobEvent, None],
    runtime: ToolRuntime[None, dict[str, Any]],
    *,
    tool_name: str,
    resource_type: str,
    resource_id: int,
    job_id: str,
) -> AnalysisJobEvent:
    terminal: AnalysisJobEvent | None = None
    async with aclosing(events) as event_stream:
        async for event in event_stream:
            await _forward_event(
                runtime,
                tool_name=tool_name,
                resource_type=resource_type,
                resource_id=resource_id,
                event=event,
            )
            if event.event in {"final", "error"}:
                terminal = event
                break

    if terminal is None:
        raise RuntimeError(f"Analysis job did not finish: {job_id}")
    return terminal


def _build_result(
    *,
    resource_type: str,
    resource_id: int,
    job_id: str,
    terminal: AnalysisJobEvent,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "resource_type": resource_type,
        "resource_id": resource_id,
        "job_id": job_id,
        "status": "parsed" if terminal.event == "final" else "failed",
    }

    if terminal.event == "final":
        key = "resume" if resource_type == "resume" else "job_description"
        detail = _model_dump(terminal.data.get(key))
        result["detail"] = detail
        result["result"] = (
            detail.get("result")
            if resource_type == "job_description" and isinstance(detail, dict)
            else detail
        )
    else:
        result["error"] = str(
            terminal.data.get("detail")
            or terminal.data.get("error")
            or "Analysis failed."
        )

    return result


def _content_and_artifact(result: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    return json.dumps(result, ensure_ascii=False), result


def _resume_service(dependencies: AnalysisToolDependencies, session) -> ResumeService:
    return ResumeService(
        repository=ResumeDocumentRepository(session),
        extraction_repository=ResumeExtractionRepository(session),
        upload_dir=dependencies.config.resume_upload_dir,
    )


def _chat_file_service(
    dependencies: AnalysisToolDependencies, session
) -> ChatFileService:
    return ChatFileService(
        file_repository=ChatFileRepository(session),
        thread_file_repository=ChatThreadFileRepository(session),
        upload_dir=dependencies.config.chat_file_upload_dir,
    )


def _resume_document(detail: ResumeDetail) -> ResumeDocument:
    return ResumeDocument.model_validate(detail.model_dump())


def build_resume_analysis_tool(
    dependencies: AnalysisToolDependencies,
) -> BaseTool:
    @tool(response_format="content_and_artifact")
    async def analyze_resume(
        resume_id: int | None = Field(
            default=None,
            description=(
                "Existing resume record ID to re-analyze. Provide this or file_id, not both."
            ),
            examples=[1],
        ),
        file_id: str | None = Field(
            default=None,
            description=(
                "Existing file-library file ID to create a new resume record from. "
                "Only PDF, DOCX, PNG, JPG, and JPEG files are supported."
            ),
            examples=["A1B2C3"],
        ),
        *,
        runtime: ToolRuntime[None, dict[str, Any]],
    ) -> tuple[str, dict[str, Any]]:
        """Analyze a resume and persist the structured result.

        Use exactly one explicit input: resume_id for an existing resume record,
        or file_id for a reusable file-library attachment. The current chat model
        is used automatically. Wait for the background job to reach parsed or
        failed before returning the persisted result.
        """

        locale = _locale(runtime)
        try:
            selection, selection_id = _model_selection(runtime)
            normalized_file_id = file_id.strip() if file_id else None
            if (resume_id is None) == (normalized_file_id is None):
                raise ValueError("Provide exactly one of resume_id or file_id.")

            with dependencies.database.get_session_factory()() as session:
                service = _resume_service(dependencies, session)
                if normalized_file_id is not None:
                    stored_file = _chat_file_service(
                        dependencies, session
                    ).get_file_raw(normalized_file_id)
                    try:
                        payload = Path(stored_file.path).read_bytes()
                    except OSError as error:
                        raise ChatFileProcessingError(
                            "The reusable file could not be read."
                        ) from error
                    detail = service.create_from_file(
                        UploadedResumeFile(
                            filename=stored_file.filename,
                            content_type=stored_file.media_type,
                            content=payload,
                        )
                    )
                    target_id = detail.id
                else:
                    assert resume_id is not None
                    detail = service.get_resume(resume_id)
                    target_id = resume_id

                processing_detail = service.begin_extraction(target_id, selection_id)

            try:
                job_id = await dependencies.resume_jobs.start(
                    resume_id=target_id,
                    selection_id=selection_id,
                    selection=selection,
                    resume_document=_resume_document(processing_detail),
                    initial_event=AnalysisJobEvent(
                        "resume", {"resume": processing_detail}
                    ),
                    locale=locale,
                )
            except Exception:
                with dependencies.database.get_session_factory()() as session:
                    _resume_service(dependencies, session).fail_extraction(
                        target_id,
                        selection_id,
                        "Failed to start resume analysis.",
                    )
                raise

            terminal = await _wait_for_job(
                dependencies.resume_jobs.events(target_id, job_id),
                runtime,
                tool_name=analyze_resume.name,
                resource_type="resume",
                resource_id=target_id,
                job_id=job_id,
            )
            result = _build_result(
                resource_type="resume",
                resource_id=target_id,
                job_id=job_id,
                terminal=terminal,
            )
            return _content_and_artifact(result)
        except Exception as error:
            raise RuntimeError(localize_error(error, locale)) from error

    return analyze_resume


def build_job_description_analysis_tool(
    dependencies: AnalysisToolDependencies,
) -> BaseTool:
    @tool(response_format="content_and_artifact")
    async def analyze_job_description(
        jd_text: str | None = Field(
            default=None,
            description="Pasted job description text. At least one input source is required.",
        ),
        source_url: str | None = Field(
            default=None,
            description="Source URL for the job description.",
            examples=["https://example.com/jobs/123"],
        ),
        file_ids: list[str] = Field(
            default_factory=list,
            description="Image file-library IDs to use as job description sources.",
            examples=[["A1B2C3"]],
        ),
        *,
        runtime: ToolRuntime[None, dict[str, Any]],
    ) -> tuple[str, dict[str, Any]]:
        """Analyze a job description and persist a new structured result.

        Provide pasted text, a source URL, and/or reusable image file IDs. The
        current chat model is used automatically. Wait for the analysis job to
        reach parsed or failed before returning the persisted result.
        """

        locale = _locale(runtime)
        try:
            selection, selection_id = _model_selection(runtime)
            normalized_text = jd_text.strip() if jd_text and jd_text.strip() else None
            normalized_url = (
                source_url.strip() if source_url and source_url.strip() else None
            )
            normalized_file_ids = [item.strip() for item in file_ids if item.strip()]

            with dependencies.database.get_session_factory()() as session:
                chat_files = _chat_file_service(dependencies, session)
                analysis_service = JobDescriptionAnalysisService(
                    JobDescriptionAnalysisRepository(session)
                )
                images: list[str] = []
                for file_id in normalized_file_ids:
                    images.append(
                        analysis_service.stored_file_to_data_url(
                            chat_files.get_file_raw(file_id)
                        )
                    )

                analysis_service.validate_sources(
                    jd_text=normalized_text,
                    source_url=normalized_url,
                    image_file_ids=normalized_file_ids,
                )
                detail = analysis_service.create_processing(
                    selection_id=selection_id,
                    source_url=normalized_url,
                    image_file_ids=normalized_file_ids,
                )

            try:
                job_id = await dependencies.jd_jobs.start(
                    analysis_id=detail.id,
                    selection_id=selection_id,
                    selection=selection,
                    jd_text=normalized_text,
                    source_url=normalized_url,
                    images=images,
                    initial_event=AnalysisJobEvent(
                        "job_description", {"job_description": detail}
                    ),
                    locale=locale,
                )
            except Exception:
                with dependencies.database.get_session_factory()() as session:
                    JobDescriptionAnalysisService(
                        JobDescriptionAnalysisRepository(session)
                    ).fail_analysis(
                        detail.id,
                        selection_id,
                        "Failed to start job description analysis.",
                    )
                raise

            terminal = await _wait_for_job(
                dependencies.jd_jobs.events(detail.id, job_id),
                runtime,
                tool_name=analyze_job_description.name,
                resource_type="job_description",
                resource_id=detail.id,
                job_id=job_id,
            )
            result = _build_result(
                resource_type="job_description",
                resource_id=detail.id,
                job_id=job_id,
                terminal=terminal,
            )
            return _content_and_artifact(result)
        except Exception as error:
            raise RuntimeError(localize_error(error, locale)) from error

    return analyze_job_description


def get_analysis_tools(
    dependencies: AnalysisToolDependencies,
) -> list[BaseTool]:
    return [
        build_resume_analysis_tool(dependencies),
        build_job_description_analysis_tool(dependencies),
    ]


__all__ = [
    "AnalysisToolDependencies",
    "build_job_description_analysis_tool",
    "build_resume_analysis_tool",
    "get_analysis_tools",
]
