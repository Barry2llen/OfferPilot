import asyncio
import json
from collections.abc import AsyncGenerator
from collections.abc import Generator
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from agent.workflows.resume_extract import ResumeExtractWorkflow
from db.repositories import ModelSelectionRepository, ResumeDocumentRepository, ResumeExtractionRepository
from exceptions import (
    EmptyResumeContentError,
    ResumeFileNotFoundError,
    ResumeNotFoundError,
    ResumeValidationError,
    UnsupportedResumeFileError,
)
from schemas.resume_document import (
    ResumeDocument,
    ResumeDetail,
    ResumeListItem,
)
from services import ModelSelectionService, ResumeService, UploadedResumeFile

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
        extraction_repository=ResumeExtractionRepository(session),
        upload_dir=request.app.state.config.resume_upload_dir,
    )


async def _read_upload_file(file: UploadFile) -> bytes:
    try:
        return await file.read()
    finally:
        await file.close()


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_to_jsonable(item) for item in value]

    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(_to_jsonable(data), ensure_ascii=False)}\n\n"


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
    service: ResumeService,
    resume_id: int,
    selection_id: int,
    selection: Any,
    resume_document: ResumeDocument,
    initial_detail: ResumeDetail,
) -> AsyncGenerator[str, None]:
    yield _sse("resume", {"resume": initial_detail})

    queue: asyncio.Queue[str | None] = asyncio.Queue()
    workflow = ResumeExtractWorkflow(config=request.app.state.config)

    async def handle_custom_event(event: dict[str, Any]) -> None:
        name = str(event.get("name") or "")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}

        if name == "on_progress_update":
            await queue.put(
                _sse(
                    "progress",
                    {
                        "resume_id": resume_id,
                        "progress": data.get("progress", 0),
                        "message": data.get("message"),
                        "additional_data": data.get("additional_data") or {},
                    },
                )
            )
            return

        if name == "on_model_call_error":
            await queue.put(
                _sse(
                    "model_error",
                    {
                        "resume_id": resume_id,
                        "attempt": data.get("attempt"),
                        "max_attempts": data.get("max_attempts"),
                        "detail": data.get("error"),
                        "additional_data": data.get("additional_data") or {},
                    },
                )
            )

    async def run_workflow() -> None:
        try:
            parsed_resume = await workflow.astream_events(
                selection,
                resume_document,
                handlers={"on_custom_event": handle_custom_event},
            )
            final_detail = service.complete_extraction(
                resume_id,
                selection_id,
                parsed_resume,
            )
            await queue.put(_sse("final", {"resume": final_detail}))
        except Exception as error:
            detail = str(error)
            service.fail_extraction(resume_id, selection_id, detail)
            await queue.put(
                _sse(
                    "error",
                    {
                        "resume_id": resume_id,
                        "detail": detail,
                        "parse_status": "failed",
                    },
                )
            )
        finally:
            await queue.put(None)

    task = asyncio.create_task(run_workflow())
    try:
        while True:
            item = await queue.get()
            if item is None:
                break
            yield item
    finally:
        if not task.done():
            task.cancel()


@router.get(
    "",
    response_model=list[ResumeListItem],
    summary="列出已上传简历",
    description=(
        "返回当前系统中所有简历记录的文件信息。"
        "适用于列表页展示，包含原文件信息和预览地址。"
    ),
    response_description="按上传时间倒序返回简历文件列表。",
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
    description="根据简历记录 ID 返回原文件信息和预览地址。",
    response_description="返回指定简历的文件详情。",
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
    summary="上传简历文件",
    description=(
        "上传 PDF、DOCX、PNG、JPG 或 JPEG 格式的简历文件。"
        "服务会保存原文件和文件元数据，并使用指定模型选择记录流式解析简历内容。"
    ),
    response_description="返回 text/event-stream 事件流。",
    responses={
        200: {
            "description": "返回 SSE 事件流。事件包括 resume、progress、model_error、final，失败时返回 error。",
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "example": 'event: progress\ndata: {"progress":0.4,"message":"Extracting resume sections."}\n\n',
                }
            },
        },
        404: _error_response("未找到指定模型选择配置。", example="Model selection not found: 1"),
        415: _error_response("上传了不支持的文件类型。", example="Legacy .doc files are not supported."),
        422: _error_response("文件为空或文件名非法。", example="Uploaded file is empty."),
    },
)
async def upload_resume_file(
    request: Request,
    selection_id: int = Form(
        ...,
        description="用于解析简历的模型选择记录 ID，对应 tb_model_selection.id。",
        examples=[1],
    ),
    file: UploadFile = File(
        ...,
        description="待上传的简历文件，支持 PDF、DOCX、PNG、JPG、JPEG。",
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

    return StreamingResponse(
        _stream_resume_extraction(
            request=request,
            service=service,
            resume_id=detail.id,
            selection_id=selection_id,
            selection=selection,
            resume_document=_resume_document_from_detail(processing_detail),
            initial_detail=processing_detail,
        ),
        media_type="text/event-stream",
    )


@router.put(
    "/{resume_id}/file",
    summary="替换简历原文件",
    description=(
        "使用新的简历文件替换指定记录对应的原始文件。"
        "替换成功后会更新文件名和媒体类型，并使用指定模型选择记录流式重新解析简历内容。"
    ),
    response_description="返回 text/event-stream 事件流。",
    responses={
        200: {
            "description": "返回 SSE 事件流。事件包括 resume、progress、model_error、final，失败时返回 error。",
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "example": 'event: final\ndata: {"resume":{"id":1,"parse_status":"parsed"}}\n\n',
                }
            },
        },
        404: _error_response("未找到指定简历。", example="Resume not found: 1"),
        415: _error_response("上传了不支持的文件类型。", example="Unsupported resume file type: .txt"),
        422: _error_response("文件为空或文件名非法。", example="Uploaded file is empty."),
    },
)
async def replace_resume_file(
    request: Request,
    resume_id: int = Path(
        ...,
        description="待替换原文件的简历记录 ID。",
        examples=[1],
    ),
    selection_id: int = Form(
        ...,
        description="用于重新解析简历的模型选择记录 ID，对应 tb_model_selection.id。",
        examples=[1],
    ),
    file: UploadFile = File(
        ...,
        description="新的简历文件，支持 PDF、DOCX、PNG、JPG、JPEG。",
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

    return StreamingResponse(
        _stream_resume_extraction(
            request=request,
            service=service,
            resume_id=detail.id,
            selection_id=selection_id,
            selection=selection,
            resume_document=_resume_document_from_detail(processing_detail),
            initial_detail=processing_detail,
        ),
        media_type="text/event-stream",
    )


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
