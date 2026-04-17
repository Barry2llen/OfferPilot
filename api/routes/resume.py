from collections.abc import Generator
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from db.repositories import ResumeDocumentRepository
from exceptions import (
    EmptyResumeContentError,
    ResumeFileNotFoundError,
    ResumeNotFoundError,
    ResumeParsingError,
    ResumeValidationError,
    UnsupportedResumeFileError,
)
from schemas.resume_document import (
    ResumeDetail,
    ResumeListItem,
)
from services import DocumentParserService, ResumeService, UploadedResumeFile

router = APIRouter(prefix="/resumes", tags=["resumes"])


def _get_request_db_session(request: Request) -> Generator[Session, None, None]:
    session = request.app.state.database.get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def _build_resume_service(request: Request, session: Session) -> ResumeService:
    return ResumeService(
        repository=ResumeDocumentRepository(session),
        parser=DocumentParserService(),
        upload_dir=request.app.state.config.resume_upload_dir,
    )


async def _read_upload_file(file: UploadFile) -> bytes:
    try:
        return await file.read()
    finally:
        await file.close()


@router.get("", response_model=list[ResumeListItem])
async def list_resumes(
    request: Request,
    session: Session = Depends(_get_request_db_session),
) -> list[ResumeListItem]:
    service = _build_resume_service(request, session)
    return service.list_resumes()


@router.get("/{resume_id}", response_model=ResumeDetail)
async def get_resume(
    resume_id: int,
    request: Request,
    session: Session = Depends(_get_request_db_session),
) -> ResumeDetail:
    service = _build_resume_service(request, session)
    try:
        return service.get_resume(resume_id)
    except ResumeNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/files", response_model=ResumeDetail)
async def upload_resume_file(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(_get_request_db_session),
) -> ResumeDetail:
    service = _build_resume_service(request, session)
    payload = await _read_upload_file(file)

    try:
        return service.create_from_file(
            UploadedResumeFile(
                filename=file.filename or "",
                content_type=file.content_type,
                content=payload,
            )
        )
    except UnsupportedResumeFileError as error:
        raise HTTPException(status_code=415, detail=str(error)) from error
    except (
        EmptyResumeContentError,
        ResumeParsingError,
        ResumeValidationError,
    ) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.put("/{resume_id}/file", response_model=ResumeDetail)
async def replace_resume_file(
    resume_id: int,
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(_get_request_db_session),
) -> ResumeDetail:
    service = _build_resume_service(request, session)
    payload = await _read_upload_file(file)

    try:
        return service.replace_resume_file(
            resume_id,
            UploadedResumeFile(
                filename=file.filename or "",
                content_type=file.content_type,
                content=payload,
            ),
        )
    except ResumeNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except UnsupportedResumeFileError as error:
        raise HTTPException(status_code=415, detail=str(error)) from error
    except (
        EmptyResumeContentError,
        ResumeParsingError,
        ResumeValidationError,
    ) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.delete("/{resume_id}", status_code=204)
async def delete_resume(
    resume_id: int,
    request: Request,
    session: Session = Depends(_get_request_db_session),
) -> Response:
    service = _build_resume_service(request, session)
    try:
        service.delete_resume(resume_id)
    except ResumeNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return Response(status_code=204)


@router.get("/{resume_id}/file")
async def preview_resume_file(
    resume_id: int,
    request: Request,
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
