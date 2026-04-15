from collections.abc import Generator

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from db.repositories import ResumeDocumentRepository
from schemas.resume_document import ResumeDocument, ResumeTextCreateRequest
from services import (
    DocumentParserService,
    EmptyResumeContentError,
    ResumeParsingError,
    ResumeService,
    UnsupportedResumeFileError,
    UploadedResumeFile,
)

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


@router.post("/text", response_model=ResumeDocument)
async def upload_resume_text(
    payload: ResumeTextCreateRequest,
    request: Request,
    session: Session = Depends(_get_request_db_session),
) -> ResumeDocument:
    service = _build_resume_service(request, session)
    try:
        return service.create_from_text(payload.content)
    except EmptyResumeContentError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/files", response_model=ResumeDocument)
async def upload_resume_file(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(_get_request_db_session),
) -> ResumeDocument:
    service = _build_resume_service(request, session)

    try:
        payload = await file.read()
    finally:
        await file.close()

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
    except (EmptyResumeContentError, ResumeParsingError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
