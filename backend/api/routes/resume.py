from collections.abc import AsyncGenerator, Generator
from typing import Any
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from db.repositories import (
    ModelSelectionRepository,
    ResumeDocumentRepository,
    ResumeExtractionRepository,
)
from exceptions import (
    EmptyResumeContentError,
    ResumeFileNotFoundError,
    ResumeNotFoundError,
    ResumeValidationError,
    UnsupportedResumeFileError,
)
from schemas.resume_document import (
    ResumeDetail,
    ResumeDocument,
    ResumeListItem,
)
from services import ModelSelectionService, ResumeService, UploadedResumeFile
from services.resume_extraction_jobs import ResumeExtractionJobManager
from utils.i18n import request_locale
from utils.stream import render_sse_event

router = APIRouter(prefix="/resumes", tags=["resumes"])

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


def _build_resume_service(request: Request, session: Session) -> ResumeService:
    return ResumeService(
        repository=ResumeDocumentRepository(session),
        extraction_repository=ResumeExtractionRepository(session),
        upload_dir=request.app.state.config.resume_upload_dir,
    )


async def _read_upload_file(file: UploadFile) -> bytes:
    try:
        return await file.read()
    finally:
        await file.close()


def _sse(event: str, data: dict[str, Any]) -> str:
    return render_sse_event(event, data)


def _get_model_selection(selection_id: int, session: Session):
    selection_service = ModelSelectionService(ModelSelectionRepository(session))
    selection = selection_service.get_by_id(selection_id)
    if selection is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model selection not found: {selection_id}",
        )
    return selection


def _resume_document_from_detail(detail: ResumeDetail) -> ResumeDocument:
    return ResumeDocument.model_validate(detail.model_dump())


async def _stream_resume_extraction(
    *,
    request: Request,
    resume_id: int,
    job_id: str,
) -> AsyncGenerator[str, None]:
    manager: ResumeExtractionJobManager = request.app.state.resume_extraction_jobs
    async for item in manager.stream(resume_id, job_id):
        yield item


@router.get(
    "",
    response_model=list[ResumeListItem],
    summary="List uploaded resumes",
    description=(
        "Return file information for all resume records. Intended for list views and includes "
        "original file metadata and preview URLs."
    ),
    response_description="Returns resumes ordered by upload time.",
)
async def list_resumes(
    request: Request,
    session: Session = Depends(_get_request_db_session),
) -> list[ResumeListItem]:
    service = _build_resume_service(request, session)
    return service.list_resumes()


@router.get(
    "/{resume_id}",
    response_model=ResumeDetail,
    summary="Get resume details",
    description="Return original file information and a preview URL for a resume record ID.",
    response_description="Returns the requested resume details.",
    responses={
        404: _error_response(
            "The requested resume was not found.", example="Resume not found: 1"
        ),
    },
)
async def get_resume(
    request: Request,
    resume_id: int = Path(
        ...,
        description="Resume record ID. Use the `id` returned after upload.",
        examples=[1],
    ),
    session: Session = Depends(_get_request_db_session),
) -> ResumeDetail:
    service = _build_resume_service(request, session)
    try:
        return service.get_resume(resume_id)
    except ResumeNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/files",
    summary="Upload a resume file",
    description=(
        "Upload a PDF, DOCX, PNG, JPG, or JPEG resume file. The service stores the original file and metadata, "
        "then streams parsing with the selected model. The parsing job continues in the background if the SSE "
        "connection is closed."
    ),
    response_description="Returns a text/event-stream response.",
    responses={
        200: {
            "description": "Returns SSE events including resume, progress, model_error, and final; failures use error.",
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "example": 'event: progress\ndata: {"progress":0.4,"message":"Extracting resume sections."}\n\n',
                }
            },
        },
        404: _error_response(
            "The requested model selection was not found.",
            example="Model selection not found: 1",
        ),
        415: _error_response(
            "The uploaded file type is not supported.",
            example="Legacy .doc files are not supported.",
        ),
        422: _error_response(
            "The file is empty or its name is invalid.",
            example="Uploaded file is empty.",
        ),
    },
)
async def upload_resume_file(
    request: Request,
    selection_id: int = Form(
        ...,
        description="Model selection record ID used to parse the resume.",
        examples=[1],
    ),
    file: UploadFile = File(
        ...,
        description="Resume file to upload. PDF, DOCX, PNG, JPG, and JPEG are supported.",
    ),
    session: Session = Depends(_get_request_db_session),
) -> StreamingResponse:
    selection = _get_model_selection(selection_id, session)
    service = _build_resume_service(request, session)
    payload = await _read_upload_file(file)

    try:
        detail = service.create_from_file(
            UploadedResumeFile(
                filename=file.filename or "",
                content_type=file.content_type,
                content=payload,
            )
        )
        processing_detail = service.begin_extraction(detail.id, selection_id)
    except UnsupportedResumeFileError as error:
        raise HTTPException(status_code=415, detail=str(error)) from error
    except (
        EmptyResumeContentError,
        ResumeValidationError,
    ) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    manager: ResumeExtractionJobManager = request.app.state.resume_extraction_jobs
    job_id = await manager.start(
        resume_id=detail.id,
        selection_id=selection_id,
        selection=selection,
        resume_document=_resume_document_from_detail(processing_detail),
        initial_event=_sse("resume", {"resume": processing_detail}),
        locale=request_locale(request),
    )

    return StreamingResponse(
        _stream_resume_extraction(
            request=request,
            resume_id=detail.id,
            job_id=job_id,
        ),
        media_type="text/event-stream",
    )


@router.put(
    "/{resume_id}/file",
    summary="Replace a resume file",
    description=(
        "Replace the original file for a resume record. The filename and media type are updated, and parsing "
        "is streamed with the selected model. The background parsing job continues if the SSE connection closes."
    ),
    response_description="Returns a text/event-stream response.",
    responses={
        200: {
            "description": "Returns SSE events including resume, progress, model_error, and final; failures use error.",
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "example": 'event: final\ndata: {"resume":{"id":1,"parse_status":"parsed"}}\n\n',
                }
            },
        },
        404: _error_response(
            "The requested resume was not found.", example="Resume not found: 1"
        ),
        415: _error_response(
            "The uploaded resume file type is not supported.",
            example="Unsupported resume file type: .txt",
        ),
        422: _error_response(
            "The file is empty or its name is invalid.",
            example="Uploaded file is empty.",
        ),
    },
)
async def replace_resume_file(
    request: Request,
    resume_id: int = Path(
        ...,
        description="Resume record ID whose original file will be replaced.",
        examples=[1],
    ),
    selection_id: int = Form(
        ...,
        description="Model selection record ID used to reparse the resume.",
        examples=[1],
    ),
    file: UploadFile = File(
        ...,
        description="New resume file. PDF, DOCX, PNG, JPG, and JPEG are supported.",
    ),
    session: Session = Depends(_get_request_db_session),
) -> StreamingResponse:
    selection = _get_model_selection(selection_id, session)
    service = _build_resume_service(request, session)
    payload = await _read_upload_file(file)

    try:
        detail = service.replace_resume_file(
            resume_id,
            UploadedResumeFile(
                filename=file.filename or "",
                content_type=file.content_type,
                content=payload,
            ),
        )
        processing_detail = service.begin_extraction(detail.id, selection_id)
    except ResumeNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except UnsupportedResumeFileError as error:
        raise HTTPException(status_code=415, detail=str(error)) from error
    except (
        EmptyResumeContentError,
        ResumeValidationError,
    ) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    manager: ResumeExtractionJobManager = request.app.state.resume_extraction_jobs
    job_id = await manager.start(
        resume_id=detail.id,
        selection_id=selection_id,
        selection=selection,
        resume_document=_resume_document_from_detail(processing_detail),
        initial_event=_sse("resume", {"resume": processing_detail}),
        locale=request_locale(request),
    )

    return StreamingResponse(
        _stream_resume_extraction(
            request=request,
            resume_id=detail.id,
            job_id=job_id,
        ),
        media_type="text/event-stream",
    )


@router.delete(
    "/{resume_id}",
    status_code=204,
    summary="Delete a resume",
    description="Delete a resume record and attempt to remove its stored original file.",
    response_description="Deleted successfully with no response body.",
    responses={
        404: _error_response(
            "The requested resume was not found.", example="Resume not found: 1"
        ),
    },
)
async def delete_resume(
    request: Request,
    resume_id: int = Path(
        ...,
        description="Resume record ID to delete.",
        examples=[1],
    ),
    session: Session = Depends(_get_request_db_session),
) -> Response:
    service = _build_resume_service(request, session)
    try:
        service.delete_resume(resume_id)
    except ResumeNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return Response(status_code=204)


@router.get(
    "/{resume_id}/file",
    response_class=FileResponse,
    summary="Preview the original resume file",
    description=(
        "Return the original resume file stream for browser preview. The `content-type` depends on the "
        "original file and is commonly PDF or an image."
    ),
    response_description="Returns the original resume file content.",
    responses={
        200: {
            "description": "Returns the original resume file stream.",
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"},
                }
            },
        },
        404: _error_response(
            "The requested resume or original file was not found.",
            example="Resume file not found: 1",
        ),
    },
)
async def preview_resume_file(
    request: Request,
    resume_id: int = Path(
        ...,
        description="Resume record ID whose original file should be previewed.",
        examples=[1],
    ),
    session: Session = Depends(_get_request_db_session),
) -> FileResponse:
    service = _build_resume_service(request, session)
    try:
        stored_file = service.get_resume_file(resume_id)
    except (ResumeNotFoundError, ResumeFileNotFoundError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    headers: dict[str, str] = {"Content-Disposition": "inline"}
    if stored_file.filename:
        encoded_filename = quote(stored_file.filename)
        headers["Content-Disposition"] = f"inline; filename*=UTF-8''{encoded_filename}"

    return FileResponse(
        path=stored_file.path,
        media_type=stored_file.media_type,
        headers=headers,
    )
