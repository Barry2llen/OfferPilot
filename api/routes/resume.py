from collections.abc import Generator
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, File, HTTPException, Path, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from db.repositories import ModelSelectionRepository, ResumeDocumentRepository
from exceptions import (
    ChatModelLoadError,
    EmptyResumeContentError,
    ModelCallExecutionError,
    ModelSelectionNotFoundError,
    ModelSelectionValidationError,
    ResumeFileNotFoundError,
    ResumeNotFoundError,
    ResumeParsingError,
    ResumePreviewError,
    ResumePreviewFileNotFoundError,
    ResumeValidationError,
    UnsupportedResumeFileError,
)
from schemas.resume_advice import ResumeAdviceRequest, ResumeAdviceResponse
from schemas.resume_document import (
    ResumeDetail,
    ResumeListItem,
)
from services import (
    DocumentParserService,
    ModelSelectionService,
    ResumeAdviceService,
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


def _build_model_selection_service(session: Session) -> ModelSelectionService:
    return ModelSelectionService(ModelSelectionRepository(session))


def _build_resume_advice_service(request: Request, session: Session) -> ResumeAdviceService:
    return ResumeAdviceService(
        resume_service=_build_resume_service(request, session),
        model_selection_service=_build_model_selection_service(session),
        config=request.app.state.config,
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
        "服务会保存原文件，并尝试提取完整文本内容用于后续展示和优化建议。"
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


@router.post(
    "/{resume_id}/advice",
    response_model=ResumeAdviceResponse,
    summary="生成简历优化建议",
    description=(
        "基于已上传的简历记录生成一份完整的优化建议。"
        "请求中必须提供已存在且支持图片输入的 `model_selection_id`，"
        "可选传入 `user_prompt` 指定关注重点。"
    ),
    response_description="返回模型生成的完整简历优化建议。",
    responses={
        404: _error_response("未找到指定简历或模型配置。", example="Model selection not found: 1"),
        422: _error_response("模型不支持图片输入或请求内容不合法。", example="Model selection does not support image input."),
        500: _error_response("简历预览转换失败或模型执行失败。", example="Failed to convert PDF resume to preview images."),
    },
)
async def generate_resume_advice(
    request: Request,
    resume_id: int = Path(
        ...,
        description="需要生成优化建议的简历记录 ID。",
        examples=[1],
    ),
    payload: ResumeAdviceRequest = Body(
        ...,
        description="用于指定模型配置和附加优化要求的请求体。",
        examples=[
            {
                "model_selection_id": 1,
                "user_prompt": "请重点分析项目表述、量化成果和岗位匹配度。",
            }
        ],
    ),
    session: Session = Depends(_get_request_db_session),
) -> ResumeAdviceResponse:
    service = _build_resume_advice_service(request, session)

    try:
        generation = service.prepare_generation(resume_id=resume_id, request=payload)
        return await service.generate_advice(generation)
    except (ResumeNotFoundError, ModelSelectionNotFoundError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ResumePreviewFileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ModelSelectionValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (
        ResumePreviewError,
        ChatModelLoadError,
        ModelCallExecutionError,
    ) as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post(
    "/{resume_id}/advice/stream",
    summary="流式生成简历优化建议",
    description=(
        "以 Server-Sent Events 形式持续返回简历优化建议。"
        "\n\n事件协议："
        "\n- `event: token`：增量文本片段"
        "\n- `event: done`：最终完整建议"
        "\n- `event: error`：执行失败信息"
    ),
    response_description="返回 `text/event-stream` 事件流。",
    responses={
        200: {
            "description": "返回 SSE 事件流，客户端可逐步消费模型输出。",
            "content": {
                "text/event-stream": {
                    "schema": {
                        "type": "string",
                        "example": (
                            "event: token\n"
                            "data: {\"content\": \"建议先补充量化成果\"}\n\n"
                            "event: done\n"
                            "data: {\"resume_id\": 1, \"model_selection_id\": 1, "
                            "\"content\": \"建议先补充量化成果，并突出岗位匹配度。\"}\n\n"
                        ),
                    }
                }
            },
        },
        404: _error_response("未找到指定简历或模型配置。", example="Resume not found: 1"),
        422: _error_response("模型不支持图片输入或请求内容不合法。", example="Model selection does not support image input."),
        500: _error_response("简历预览转换失败。", example="Failed to convert DOCX resume to preview images."),
    },
)
async def stream_resume_advice(
    request: Request,
    resume_id: int = Path(
        ...,
        description="需要生成优化建议的简历记录 ID。",
        examples=[1],
    ),
    payload: ResumeAdviceRequest = Body(
        ...,
        description="用于指定模型配置和附加优化要求的请求体。",
        examples=[
            {
                "model_selection_id": 1,
                "user_prompt": "请按技术栈、项目成果和表达精炼度给出建议。",
            }
        ],
    ),
    session: Session = Depends(_get_request_db_session),
) -> StreamingResponse:
    service = _build_resume_advice_service(request, session)

    try:
        generation = service.prepare_generation(resume_id=resume_id, request=payload)
    except (ResumeNotFoundError, ModelSelectionNotFoundError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ResumePreviewFileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ModelSelectionValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ResumePreviewError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    return StreamingResponse(
        service.stream_advice(generation),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
