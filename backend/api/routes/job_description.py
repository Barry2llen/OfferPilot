from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from db.repositories import (
    ChatFileRepository,
    ChatThreadFileRepository,
    JobDescriptionAnalysisRepository,
    ModelSelectionRepository,
)
from exceptions import (
    ChatFileNotFoundError,
    ChatFileProcessingError,
    EmptyChatFileContentError,
    JobDescriptionAnalysisNotFoundError,
    JobDescriptionAnalysisValidationError,
    ResumeValidationError,
    UnsupportedChatFileError,
)
from schemas.job_description_analysis import (
    JobDescriptionAnalysisDetail,
    JobDescriptionAnalysisListItem,
)
from services import (
    ChatFileService,
    JobDescriptionAnalysisService,
    ModelSelectionService,
    UploadedChatFile,
)
from services.jd_analysis_jobs import JdAnalysisJobManager
from utils.i18n import request_locale
from utils.stream import render_sse_event

router = APIRouter(prefix="/job-descriptions", tags=["job-descriptions"])

_ERROR_DETAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "detail": {
            "type": "string",
            "description": "Description of the error.",
        }
    },
    "required": ["detail"],
}


@dataclass(slots=True)
class _JdAnalyzePayload:
    selection_id: int
    jd_text: str | None
    source_url: str | None
    file_ids: list[str]
    uploaded_files: list[UploadedChatFile]


def _error_response(description: str, *, example: str) -> dict:
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": _ERROR_DETAIL_SCHEMA,
                "example": {"detail": example},
            }
        },
    }


def _get_request_db_session(request: Request) -> Generator[Session, None, None]:
    session = request.app.state.database.get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def _build_analysis_service(session: Session) -> JobDescriptionAnalysisService:
    return JobDescriptionAnalysisService(JobDescriptionAnalysisRepository(session))


def _build_chat_file_service(request: Request, session: Session) -> ChatFileService:
    return ChatFileService(
        file_repository=ChatFileRepository(session),
        thread_file_repository=ChatThreadFileRepository(session),
        upload_dir=request.app.state.config.chat_file_upload_dir,
    )


def _get_model_selection(selection_id: int, session: Session):
    selection_service = ModelSelectionService(ModelSelectionRepository(session))
    selection = selection_service.get_by_id(selection_id)
    if selection is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model selection not found: {selection_id}",
        )
    return selection


def _sse(event: str, data: dict[str, Any]) -> str:
    return render_sse_event(event, data)


async def _read_upload_file(file: StarletteUploadFile) -> bytes:
    try:
        return await file.read()
    finally:
        await file.close()


async def _parse_payload(request: Request) -> _JdAnalyzePayload:
    form = await request.form()
    selection_raw = form.get("selection_id")
    try:
        selection_id = int(str(selection_raw))
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=422, detail="selection_id is required."
        ) from error

    jd_text = str(form.get("jd_text") or "").strip() or None
    source_url = str(form.get("source_url") or "").strip() or None
    file_ids = [
        str(item).strip()
        for key in ("file_ids", "file_ids[]")
        for item in form.getlist(key)
        if str(item).strip()
    ]

    uploaded_files: list[UploadedChatFile] = []
    for key in ("files", "files[]"):
        for item in form.getlist(key):
            if not isinstance(item, StarletteUploadFile):
                continue
            uploaded_files.append(
                UploadedChatFile(
                    filename=item.filename or "",
                    content_type=item.content_type,
                    content=await _read_upload_file(item),
                )
            )

    return _JdAnalyzePayload(
        selection_id=selection_id,
        jd_text=jd_text,
        source_url=source_url,
        file_ids=file_ids,
        uploaded_files=uploaded_files,
    )


async def _stream_jd_analysis(
    *,
    request: Request,
    analysis_id: int,
    job_id: str,
) -> AsyncGenerator[str, None]:
    manager: JdAnalysisJobManager = request.app.state.jd_analysis_jobs
    async for item in manager.stream(analysis_id, job_id):
        yield item


@router.get(
    "",
    response_model=list[JobDescriptionAnalysisListItem],
    summary="List JD analysis history",
    description="Return created JD analysis records with status, source, and structured summary fields.",
    response_description="Returns JD analysis history ordered by creation time.",
)
async def list_job_descriptions(
    session: Session = Depends(_get_request_db_session),
) -> list[JobDescriptionAnalysisListItem]:
    return _build_analysis_service(session).list_analyses()


@router.get(
    "/{analysis_id}",
    response_model=JobDescriptionAnalysisDetail,
    summary="Get JD analysis details",
    description="Return the original text and structured analysis for a JD analysis ID.",
    response_description="Returns the requested JD analysis details.",
    responses={
        404: _error_response(
            "The requested JD analysis was not found.",
            example="JD analysis not found: 1",
        ),
    },
)
async def get_job_description(
    analysis_id: int = Path(..., description="JD analysis record ID.", examples=[1]),
    session: Session = Depends(_get_request_db_session),
) -> JobDescriptionAnalysisDetail:
    try:
        return _build_analysis_service(session).get_analysis(analysis_id)
    except JobDescriptionAnalysisNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "",
    summary="Create and stream JD analysis",
    description=(
        "Analyze a JD with the selected model. Supports pasted JD text, source URLs, uploaded PNG/JPG/JPEG "
        "images, and file_ids[] references to images in the file library."
    ),
    response_description="Returns a text/event-stream response.",
    responses={
        200: {
            "description": "Returns SSE events including job_description, progress, model_error, and final; failures use error.",
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "example": 'event: final\ndata: {"job_description":{"id":1,"status":"parsed"}}\n\n',
                }
            },
        },
        404: _error_response(
            "The requested model selection or file was not found.",
            example="Model selection not found: 1",
        ),
        415: _error_response(
            "An unsupported file type was uploaded or referenced.",
            example="Unsupported JD image file type: .pdf",
        ),
        422: _error_response(
            "The JD input is invalid.",
            example="JD text, source URL, or at least one image is required.",
        ),
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "selection_id": {
                                "type": "integer",
                                "description": "Model selection record ID used for JD analysis.",
                                "example": 1,
                            },
                            "jd_text": {
                                "type": "string",
                                "description": "Pasted JD text.",
                                "example": "Responsibilities: Build and maintain backend services.",
                            },
                            "source_url": {
                                "type": "string",
                                "description": "Source URL for the JD.",
                                "example": "https://example.com/jobs/123",
                            },
                            "files[]": {
                                "type": "array",
                                "items": {"type": "string", "format": "binary"},
                                "description": "Uploaded JD images. PNG, JPG, and JPEG are supported.",
                            },
                            "file_ids[]": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "File IDs for reusable images in the file library.",
                                "example": ["A1B2C3"],
                            },
                        },
                        "required": ["selection_id"],
                    }
                }
            },
        }
    },
)
async def analyze_job_description(
    request: Request,
    session: Session = Depends(_get_request_db_session),
) -> StreamingResponse:
    payload = await _parse_payload(request)
    selection = _get_model_selection(payload.selection_id, session)
    chat_file_service = _build_chat_file_service(request, session)
    analysis_service = _build_analysis_service(session)
    created_file_paths = []

    try:
        stored_files = chat_file_service.store_files(payload.uploaded_files)
        created_file_paths = stored_files.created_file_paths
        image_file_ids = [record.id for record in stored_files.records]
        images = [
            analysis_service.image_record_to_data_url(record)
            for record in stored_files.records
        ]

        for file_id in payload.file_ids:
            stored = chat_file_service.get_file_raw(file_id)
            images.append(analysis_service.stored_file_to_data_url(stored))
            image_file_ids.append(file_id)

        analysis_service.validate_sources(
            jd_text=payload.jd_text,
            source_url=payload.source_url,
            image_file_ids=image_file_ids,
        )
        detail = analysis_service.create_processing(
            selection_id=payload.selection_id,
            source_url=payload.source_url,
            image_file_ids=image_file_ids,
        )
    except (
        ChatFileNotFoundError,
        ChatFileProcessingError,
        EmptyChatFileContentError,
        JobDescriptionAnalysisValidationError,
        ResumeValidationError,
        UnsupportedChatFileError,
    ) as error:
        session.rollback()
        for path in created_file_paths:
            path.unlink(missing_ok=True)
        _raise_input_error(error)

    manager: JdAnalysisJobManager = request.app.state.jd_analysis_jobs
    job_id = await manager.start(
        analysis_id=detail.id,
        selection_id=payload.selection_id,
        selection=selection,
        jd_text=payload.jd_text,
        source_url=payload.source_url,
        images=images,
        initial_event=_sse("job_description", {"job_description": detail}),
        locale=request_locale(request),
    )

    return StreamingResponse(
        _stream_jd_analysis(
            request=request,
            analysis_id=detail.id,
            job_id=job_id,
        ),
        media_type="text/event-stream",
    )


@router.delete(
    "/{analysis_id}",
    status_code=204,
    summary="Delete JD analysis",
    description="Delete a JD analysis record without deleting referenced file library images.",
    response_description="Deleted successfully with no response body.",
    responses={
        404: _error_response(
            "The requested JD analysis was not found.",
            example="JD analysis not found: 1",
        ),
    },
)
async def delete_job_description(
    analysis_id: int = Path(..., description="JD analysis record ID.", examples=[1]),
    session: Session = Depends(_get_request_db_session),
) -> Response:
    try:
        _build_analysis_service(session).delete_analysis(analysis_id)
    except JobDescriptionAnalysisNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return Response(status_code=204)


def _raise_input_error(error: Exception) -> None:
    if isinstance(error, ChatFileNotFoundError):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(error, UnsupportedChatFileError):
        raise HTTPException(status_code=415, detail=str(error)) from error
    if isinstance(
        error,
        (
            EmptyChatFileContentError,
            JobDescriptionAnalysisValidationError,
            ResumeValidationError,
        ),
    ):
        raise HTTPException(status_code=422, detail=str(error)) from error
    if isinstance(error, ChatFileProcessingError):
        raise HTTPException(status_code=422, detail=str(error)) from error
    raise HTTPException(status_code=400, detail=str(error)) from error
