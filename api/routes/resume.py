from collections.abc import Generator
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Path, Request, Response, UploadFile
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
from services import (
    DocumentParserService,
    ResumeService,
    UploadedResumeFile,
)

router = APIRouter(prefix="/resumes", tags=["resumes"])

_ERROR_DETAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "detail": {
            "type": "string",
            "description": "错误详情描述。",
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
        parser=DocumentParserService(),
        upload_dir=request.app.state.config.resume_upload_dir,
    )


async def _read_upload_file(file: UploadFile) -> bytes:
    try:
        return await file.read()
    finally:
        await file.close()


@router.get(
    "",
    response_model=list[ResumeListItem],
    summary="列出已上传简历",
    description=(
        "返回当前系统中所有简历记录的摘要信息。"
        "适用于列表页展示，包含原文件信息、文本预览和预览地址。"
    ),
    response_description="按上传时间倒序返回简历摘要列表。",
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
    summary="获取简历详情",
    description="根据简历记录 ID 返回完整解析文本、原文件信息和预览地址。",
    response_description="返回指定简历的完整详情。",
    responses={
        404: _error_response("未找到指定简历。", example="Resume not found: 1"),
    },
)
async def get_resume(
    request: Request,
    resume_id: int = Path(
        ...,
        description="简历记录 ID。上传成功后响应体中的 `id` 可用于此接口。",
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
    response_model=ResumeDetail,
    summary="上传简历文件",
    description=(
        "上传 PDF、DOCX、PNG、JPG 或 JPEG 格式的简历文件。"
        "服务会保存原文件，并尝试提取完整文本内容用于后续展示和预览。"
    ),
    response_description="返回新建简历记录的完整信息。",
    responses={
        415: _error_response("上传了不支持的文件类型。", example="Legacy .doc files are not supported."),
        422: _error_response("文件为空、文件名非法或内容解析失败。", example="Resume content is empty."),
    },
)
async def upload_resume_file(
    request: Request,
    file: UploadFile = File(
        ...,
        description="待上传的简历文件，支持 PDF、DOCX、PNG、JPG、JPEG。",
    ),
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


@router.put(
    "/{resume_id}/file",
    response_model=ResumeDetail,
    summary="替换简历原文件",
    description=(
        "使用新的简历文件替换指定记录对应的原始文件，并重新提取全文内容。"
        "替换成功后会更新文件名、媒体类型和解析文本。"
    ),
    response_description="返回替换后的简历详情。",
    responses={
        404: _error_response("未找到指定简历。", example="Resume not found: 1"),
        415: _error_response("上传了不支持的文件类型。", example="Unsupported resume file type: .txt"),
        422: _error_response("文件为空、文件名非法或内容解析失败。", example="Resume content is empty."),
    },
)
async def replace_resume_file(
    request: Request,
    resume_id: int = Path(
        ...,
        description="待替换原文件的简历记录 ID。",
        examples=[1],
    ),
    file: UploadFile = File(
        ...,
        description="新的简历文件，支持 PDF、DOCX、PNG、JPG、JPEG。",
    ),
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


@router.delete(
    "/{resume_id}",
    status_code=204,
    summary="删除简历记录",
    description="删除指定简历记录，并尝试移除对应的已存储原始文件。",
    response_description="删除成功，无响应体。",
    responses={
        404: _error_response("未找到指定简历。", example="Resume not found: 1"),
    },
)
async def delete_resume(
    request: Request,
    resume_id: int = Path(
        ...,
        description="待删除的简历记录 ID。",
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
    summary="预览简历原文件",
    description=(
        "返回原始简历文件流，适用于浏览器在线预览。"
        "实际 `content-type` 取决于原始文件类型，常见为 PDF 或图片格式。"
    ),
    response_description="返回原始简历文件内容。",
    responses={
        200: {
            "description": "返回原始简历文件流。",
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"},
                }
            },
        },
        404: _error_response("未找到指定简历或其原文件。", example="Resume file not found: 1"),
    },
)
async def preview_resume_file(
    request: Request,
    resume_id: int = Path(
        ...,
        description="需要预览原文件的简历记录 ID。",
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
