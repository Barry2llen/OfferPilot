import asyncio
import json
from collections.abc import Generator
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, StreamingResponse
from langchain_core.messages import message_to_dict
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from db.repositories import (
    ChatFileRepository,
    ChatThreadFileRepository,
    CheckpointRepository,
    ModelSelectionRepository,
)
from exceptions import (
    ChatFileNotFoundError,
    ChatFileProcessingError,
    EmptyChatFileContentError,
    ResumeValidationError,
    UnsupportedChatFileError,
)
from schemas.ai import (
    AIChatCommand,
    AIChatHistoryDetailResponse,
    AIChatHistoryListResponse,
    AIChatRequest,
    AIChatResponse,
    AIChatStreamRequest,
)
from schemas.chat_file import ChatFileDetail, ChatFileListItem
from schemas.chat_run import ChatRunResponse, InputAnswer
from services import (
    ChatFileService,
    ChatHistoryService,
    ModelSelectionService,
    UploadedChatFile,
)
from utils.i18n import request_locale

router = APIRouter(prefix="/ai", tags=["ai"])

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


@dataclass(slots=True)
class ParsedAIChatPayload:
    selection_id: int
    prompt: str | None
    thread_id: str | None
    command: AIChatCommand | None
    file_ids: list[str]
    uploaded_files: list[UploadedChatFile]


def _build_chat_file_service(request: Request, session: Session) -> ChatFileService:
    return ChatFileService(
        file_repository=ChatFileRepository(session),
        thread_file_repository=ChatThreadFileRepository(session),
        upload_dir=request.app.state.config.chat_file_upload_dir,
    )


async def _parse_ai_chat_payload(
    request: Request,
    *,
    stream: bool,
) -> ParsedAIChatPayload:
    if not _is_multipart_request(request):
        return await _parse_json_ai_chat_payload(request, stream=stream)
    return await _parse_multipart_ai_chat_payload(request, stream=stream)


def _is_multipart_request(request: Request) -> bool:
    content_type = request.headers.get("content-type", "")
    return content_type.startswith("multipart/form-data")


async def _parse_json_ai_chat_payload(
    request: Request,
    *,
    stream: bool,
) -> ParsedAIChatPayload:
    try:
        body = await request.json()
    except json.JSONDecodeError as error:
        raise RequestValidationError(
            [{"loc": ("body",), "msg": str(error), "type": "json_invalid"}]
        ) from error

    try:
        if stream:
            payload = AIChatStreamRequest(**body)
            return ParsedAIChatPayload(
                selection_id=payload.selection_id,
                prompt=payload.prompt,
                thread_id=payload.thread_id,
                command=payload.command,
                file_ids=payload.file_ids,
                uploaded_files=[],
            )

        payload = AIChatRequest(**body)
        return ParsedAIChatPayload(
            selection_id=payload.selection_id,
            prompt=payload.prompt,
            thread_id=payload.thread_id,
            command=None,
            file_ids=payload.file_ids,
            uploaded_files=[],
        )
    except Exception as error:
        if isinstance(error, RequestValidationError):
            raise
        if hasattr(error, "errors"):
            raise RequestValidationError(error.errors()) from error  # type: ignore[arg-type]
        raise


async def _parse_multipart_ai_chat_payload(
    request: Request,
    *,
    stream: bool,
) -> ParsedAIChatPayload:
    form = await request.form()
    payload_data: dict[str, Any] = {
        "selection_id": form.get("selection_id"),
        "prompt": _none_if_blank(form.get("prompt")),
        "thread_id": _none_if_blank(form.get("thread_id")),
        "file_ids": _form_list(form, "file_ids"),
    }

    command_raw = form.get("command")
    if isinstance(command_raw, str) and command_raw.strip():
        try:
            payload_data["command"] = json.loads(command_raw)
        except json.JSONDecodeError as error:
            raise RequestValidationError(
                [
                    {
                        "loc": ("body", "command"),
                        "msg": str(error),
                        "type": "json_invalid",
                    }
                ]
            ) from error

    uploaded_files = await _read_uploaded_chat_files(form)

    try:
        if stream:
            payload = AIChatStreamRequest(**payload_data)
            return ParsedAIChatPayload(
                selection_id=payload.selection_id,
                prompt=payload.prompt,
                thread_id=payload.thread_id,
                command=payload.command,
                file_ids=payload.file_ids,
                uploaded_files=uploaded_files,
            )

        payload = AIChatRequest(**payload_data)
        return ParsedAIChatPayload(
            selection_id=payload.selection_id,
            prompt=payload.prompt,
            thread_id=payload.thread_id,
            command=None,
            file_ids=payload.file_ids,
            uploaded_files=uploaded_files,
        )
    except Exception as error:
        if hasattr(error, "errors"):
            raise RequestValidationError(error.errors()) from error  # type: ignore[arg-type]
        raise


def _form_list(form: Any, key: str) -> list[str]:
    values: list[str] = []
    for name in (key, f"{key}[]"):
        for item in form.getlist(name):
            if isinstance(item, str):
                normalized = item.strip()
                if normalized:
                    values.append(normalized)
    return values


def _none_if_blank(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


async def _read_uploaded_chat_files(form: Any) -> list[UploadedChatFile]:
    uploaded_files: list[UploadedChatFile] = []
    for name in ("files", "files[]"):
        for item in form.getlist(name):
            if not isinstance(item, StarletteUploadFile):
                continue
            uploaded_files.append(
                UploadedChatFile(
                    filename=item.filename or "",
                    content_type=item.content_type,
                    content=await _read_upload_file(item),
                )
            )
    return uploaded_files


async def _read_upload_file(file: StarletteUploadFile) -> bytes:
    try:
        return await file.read()
    finally:
        await file.close()


def _make_thread_id(thread_id: str | None) -> str:
    return thread_id or uuid4().hex


def _get_model_selection(selection_id: int, session: Session):
    selection_service = ModelSelectionService(ModelSelectionRepository(session))
    selection = selection_service.get_by_id(selection_id)
    if selection is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model selection not found: {selection_id}",
        )
    return selection


def _raise_chat_input_error(error: Exception) -> None:
    if isinstance(error, ChatFileNotFoundError):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(error, UnsupportedChatFileError):
        raise HTTPException(status_code=415, detail=str(error)) from error
    if isinstance(error, (EmptyChatFileContentError, ResumeValidationError)):
        raise HTTPException(status_code=422, detail=str(error)) from error
    if isinstance(error, ChatFileProcessingError):
        raise HTTPException(status_code=422, detail=str(error)) from error
    raise error


@router.get(
    "/chats",
    response_model=AIChatHistoryListResponse,
    summary="List AI conversation history",
    description=(
        "Read the latest state for each thread_id from LangGraph checkpoints and return "
        "conversation titles, message previews, message counts, and update times."
    ),
    response_description="Returns conversation summaries ordered by most recent update.",
)
async def list_chat_histories(
    request: Request,
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Page size, up to 100.",
        examples=[20],
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of items to skip.",
        examples=[0],
    ),
    session: Session = Depends(_get_request_db_session),
) -> AIChatHistoryListResponse:
    history_service = ChatHistoryService(
        CheckpointRepository(session),
        request.app.state.checkpointer,
        ChatThreadFileRepository(session),
    )
    manager = request.app.state.chat_runs
    page = await asyncio.to_thread(manager.repository.conversation_page, limit, offset)
    items = []
    for row in page:
        if row["has_checkpoint"]:
            history = history_service.get_history(row["thread_id"])
            if history is not None:
                items.append(history)
        else:
            pending = await manager.unstarted_history(row["thread_id"])
            if pending is not None:
                items.append(AIChatHistoryDetailResponse(**pending))
    return AIChatHistoryListResponse(items=items, limit=limit, offset=offset)


@router.get(
    "/chats/{thread_id}/history",
    response_model=AIChatHistoryDetailResponse,
    response_model_exclude_none=True,
    summary="Get AI conversation history",
    description=(
        "Read the complete message history for a thread_id from the latest LangGraph checkpoint "
        "and convert it into a simplified structure for the frontend."
    ),
    response_description="Returns the complete history for the requested conversation.",
    responses={
        404: _error_response(
            "Conversation history was not found.",
            example="Chat history not found: conversation-001",
        ),
    },
)
async def get_chat_history(
    thread_id: str,
    request: Request,
    session: Session = Depends(_get_request_db_session),
) -> AIChatHistoryDetailResponse:
    history_service = ChatHistoryService(
        CheckpointRepository(session),
        request.app.state.checkpointer,
        ChatThreadFileRepository(session),
    )
    history = history_service.get_history(thread_id)
    if history is None:
        pending = await request.app.state.chat_runs.unstarted_history(thread_id)
        if pending is not None:
            history = AIChatHistoryDetailResponse(**pending)
    if history is None:
        raise HTTPException(
            status_code=404,
            detail=f"Chat history not found: {thread_id}",
        )
    return history


@router.delete(
    "/chats/{thread_id}",
    status_code=204,
    summary="Delete AI conversation history",
    description=(
        "Delete the LangGraph checkpoint, checkpoint blobs, and pending writes for a thread_id. "
        "Deletion waits for admitted preparations and active execution before deleting history and attachment links. "
        "Failed cleanup keeps the conversation closed to new runs until deletion succeeds."
    ),
    response_description="Deleted successfully with no response body.",
    responses={
        404: _error_response(
            "Conversation history was not found.",
            example="Chat history not found: conversation-001",
        ),
    },
)
async def delete_chat_history(
    request: Request,
    thread_id: str = Path(
        ...,
        description="Conversation thread ID to delete.",
        examples=["conversation-001"],
    ),
) -> Response:
    def cleanup() -> bool:
        with request.app.state.database.get_session_factory()() as session:
            history_service = ChatHistoryService(
                CheckpointRepository(session),
                request.app.state.checkpointer,
            )
            deleted = history_service.delete_history(thread_id)
            _build_chat_file_service(request, session).delete_thread_attachments(
                thread_id
            )
            session.commit()
            return deleted

    deleted = await request.app.state.chat_runs.delete_thread(thread_id, cleanup)
    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"Chat history not found: {thread_id}"
        )
    return Response(status_code=204)


@router.get(
    "/files",
    response_model=list[ChatFileListItem],
    summary="List chat files",
    description="Return reusable chat attachments and their thread reference counts.",
    response_description="Returns chat attachments ordered by storage time.",
)
async def list_chat_files(
    request: Request,
    session: Session = Depends(_get_request_db_session),
) -> list[ChatFileListItem]:
    return _build_chat_file_service(request, session).list_files()


@router.get(
    "/files/{file_id}",
    response_model=ChatFileDetail,
    summary="Get chat file details",
    description="Return file details and reference counts for a short chat file ID.",
    response_description="Returns the requested chat file details.",
    responses={
        404: _error_response(
            "The requested chat file was not found.",
            example="Chat file not found: A1B2C3",
        ),
    },
)
async def get_chat_file(
    request: Request,
    file_id: str = Path(
        ...,
        description="Short chat file ID.",
        examples=["A1B2C3"],
    ),
    session: Session = Depends(_get_request_db_session),
) -> ChatFileDetail:
    try:
        return _build_chat_file_service(request, session).get_file_detail(file_id)
    except ChatFileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get(
    "/files/{file_id}/raw",
    response_class=FileResponse,
    summary="Get raw chat file content",
    description="Return raw chat file content for preview or confirmation before reuse.",
    response_description="Returns the raw chat file stream.",
    responses={
        404: _error_response(
            "The requested chat file was not found.",
            example="Chat file not found: A1B2C3",
        ),
    },
)
async def get_chat_file_raw(
    request: Request,
    file_id: str = Path(
        ...,
        description="Short chat file ID.",
        examples=["A1B2C3"],
    ),
    session: Session = Depends(_get_request_db_session),
) -> FileResponse:
    try:
        stored = _build_chat_file_service(request, session).get_file_raw(file_id)
    except ChatFileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return FileResponse(
        path=stored.path,
        media_type=stored.media_type,
        filename=stored.filename,
    )


@router.post(
    "/chat",
    response_model=AIChatResponse,
    summary="Call the AI chat API",
    description=(
        "Call SupervisorAgent with the selected model and persist conversation state through "
        "DatabaseCheckpointer. Supports JSON requests and multipart requests with files[] / file_ids[]. "
        "Idempotency-Key retries return the persisted result even after the event cache expires. "
        "Runs needing human input fail with 502; use the interactive endpoint instead."
    ),
    response_description="Returns the AI response and the conversation thread ID.",
    responses={
        409: _error_response(
            "Conflicting idempotency key or an old run whose result cannot be reliably recovered.",
            example="The result of this run is no longer available.",
        ),
        404: _error_response(
            "The requested model selection was not found.",
            example="Model selection not found: 1",
        ),
        415: _error_response(
            "The uploaded chat file type is not supported.",
            example="Unsupported chat file type: .exe",
        ),
        422: _error_response(
            "The chat attachment is invalid or could not be processed.",
            example="Uploaded chat file is empty.",
        ),
        502: _error_response(
            "The model could not be loaded or called.",
            example="Model call failed after 3 retries.",
        ),
    },
)
async def chat(request: Request) -> AIChatResponse:
    run = await _submit_chat_run(request, interactive=False)
    manager = request.app.state.chat_runs
    result = await manager.result(run["run_id"])
    return AIChatResponse(thread_id=run["thread_id"], content=result)


async def _submit_chat_run(request: Request, *, interactive=True):
    payload = await _parse_ai_chat_payload(request, stream=True)
    if payload.command and payload.command.type != "prompt":
        raise HTTPException(
            410,
            "Legacy query/retry commands are no longer supported. Submit an answer to /ai/chat/runs/{run_id}/inputs/{request_id}.",
        )
    key = request.headers.get("Idempotency-Key") or uuid4().hex
    if not 1 <= len(key) <= 128:
        raise HTTPException(422, "Invalid idempotency key.")
    fingerprint = sha256(
        json.dumps(
            {
                "thread_id": payload.thread_id,
                "selection_id": payload.selection_id,
                "prompt": payload.prompt,
                "command": payload.command.model_dump() if payload.command else None,
                "file_ids": payload.file_ids,
                "interactive": interactive,
                "locale": request_locale(request),
                "uploads": [
                    (f.filename, f.content_type, sha256(f.content).hexdigest())
                    for f in payload.uploaded_files
                ],
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    manager = request.app.state.chat_runs
    previous = await manager.lookup_key(key, fingerprint)
    if previous:
        return previous
    thread_id = _make_thread_id(payload.thread_id)

    def prepare():
        with request.app.state.database.get_session_factory()() as session:
            selection = _get_model_selection(payload.selection_id, session)
            service = _build_chat_file_service(request, session)
            prompt = (
                (payload.command.prompt if payload.command else None)
                or payload.prompt
                or ""
            )
            try:
                prepared = service.prepare_prompt(
                    thread_id=thread_id,
                    selection=selection,
                    prompt=prompt,
                    file_ids=payload.file_ids,
                    uploaded_files=payload.uploaded_files,
                )
                prepared.human_message.id = uuid4().hex
                session.commit()
            except (
                ChatFileNotFoundError,
                ChatFileProcessingError,
                EmptyChatFileContentError,
                ResumeValidationError,
                UnsupportedChatFileError,
            ) as error:
                session.rollback()
                _raise_chat_input_error(error)
            return {
                "prompt": prompt,
                "selection_id": payload.selection_id,
                "human_message": message_to_dict(prepared.human_message),
                "file_ids": [a.file_id for a in prepared.attachments],
                "resolved_attachments": [
                    a.model_dump(mode="json") for a in prepared.attachments
                ],
                "requires_image_input": prepared.requires_image_input,
                "attachment_count": prepared.attachment_count,
                "locale": request_locale(request),
            }

    return await manager.enqueue(
        key=key,
        fingerprint=fingerprint,
        thread_id=thread_id,
        prepare=prepare,
        interactive=interactive,
    )


_RUN_ERRORS: dict[int | str, dict[str, Any]] = {
    code: _error_response(description, example=description)
    for code, description in {
        404: "Chat run not found.",
        409: "Conflicting request or unavailable conversation.",
        410: "The input request has expired.",
        422: "Invalid submission or answer.",
        429: "The conversation queue is full.",
    }.items()
}

_RUN_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            media: {
                "schema": {
                    "type": "object",
                    "required": ["selection_id"],
                    "properties": {
                        "selection_id": {
                            "type": "integer",
                            "description": "Model selection ID.",
                            "example": 1,
                        },
                        "prompt": {
                            "type": "string",
                            "description": "User message; optional with attachments.",
                        },
                        "thread_id": {
                            "type": "string",
                            "description": "Existing conversation ID; omitted for a new conversation.",
                        },
                        "file_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Previously uploaded attachment IDs.",
                        },
                        **(
                            {
                                "files": {
                                    "type": "array",
                                    "items": {"type": "string", "format": "binary"},
                                }
                            }
                            if media == "multipart/form-data"
                            else {}
                        ),
                    },
                }
            }
            for media in ("application/json", "multipart/form-data")
        },
    }
}


@router.post(
    "/chat/runs",
    openapi_extra=_RUN_BODY,
    response_model=ChatRunResponse,
    status_code=202,
    summary="Create a chat run",
    description="Accept JSON or multipart chat input and enqueue it in conversation order. Use Idempotency-Key to safely retry a submission.",
    response_description="The accepted run and its current queue status.",
    responses=_RUN_ERRORS,
)
async def create_chat_run(
    request: Request,
    idempotency_key: str | None = Header(
        default=None,
        max_length=128,
        description="Stable key reused when retrying the same submission.",
    ),
):
    return await _submit_chat_run(request)


@router.get(
    "/chat/runs",
    response_model=list[ChatRunResponse],
    summary="List conversation runs",
    description="List submitted runs in FIFO order, including pending input requests and runs lost on restart.",
    response_description="Ordered conversation runs.",
    responses=_RUN_ERRORS,
)
async def list_chat_runs(
    request: Request, thread_id: str = Query(description="Conversation ID.")
):
    return await request.app.state.chat_runs.list(thread_id)


@router.get(
    "/chat/runs/{run_id}",
    response_model=ChatRunResponse,
    summary="Get a chat run",
    description="Read execution state independently of any SSE subscription.",
    response_description="Run status and pending input requests.",
    responses=_RUN_ERRORS,
)
async def get_chat_run(request: Request, run_id: str):
    return await request.app.state.chat_runs.get(run_id)


@router.get(
    "/chat/runs/{run_id}/events",
    summary="Subscribe to chat events",
    description="Replay events after the supplied sequence, then follow live events. A snapshot replaces expired replay history. Disconnecting does not cancel execution.",
    response_description="Sequenced SSE events or a display snapshot.",
    responses=_RUN_ERRORS,
)
async def subscribe_chat_run(
    request: Request,
    run_id: str,
    after: int = Query(default=0, ge=0, description="Last applied event ID."),
):
    await request.app.state.chat_runs.get(run_id)
    return StreamingResponse(
        request.app.state.chat_runs.stream(run_id, after),
        media_type="text/event-stream",
    )


@router.post(
    "/chat/runs/{run_id}/inputs/{request_id}",
    response_model=ChatRunResponse,
    summary="Answer an input request",
    description="Wake the original execution without invoking the graph again. Identical repeat answers are idempotent; conflicting answers are rejected.",
    response_description="Current run state.",
    responses=_RUN_ERRORS,
)
async def answer_chat_input(
    request: Request, run_id: str, request_id: str, payload: InputAnswer
):
    manager = request.app.state.chat_runs
    await manager.get(run_id)
    await manager.broker.submit(run_id, request_id, payload.answer.model_dump())
    return await manager.get(run_id)


@router.post(
    "/chat/runs/{run_id}/cancel",
    response_model=ChatRunResponse,
    summary="Cancel a chat run",
    description="Cancel and await this run. Later queued messages still execute; cancel each queued run to remove it.",
    response_description="The terminated run state.",
    responses=_RUN_ERRORS,
)
async def cancel_chat_run(request: Request, run_id: str):
    return await request.app.state.chat_runs.cancel(run_id)


@router.post(
    "/chat/stream",
    openapi_extra=_RUN_BODY,
    summary="Start and subscribe to a chat run",
    description="Compatibility entry point for prompt submissions. Execution survives SSE disconnection. Answers use the separate run input endpoint; legacy query/retry commands return 410.",
    response_description="SSE events including thread, token, reasoning, tool_start/end/error, input_required/resolved, run_status, snapshot, final and error.",
    responses=_RUN_ERRORS,
)
async def chat_stream(request: Request):
    run = await _submit_chat_run(request)
    return StreamingResponse(
        request.app.state.chat_runs.stream(run["run_id"], -1),
        media_type="text/event-stream",
    )
