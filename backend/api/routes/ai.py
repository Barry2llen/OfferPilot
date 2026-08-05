import json
from dataclasses import dataclass
from collections.abc import AsyncGenerator, Generator
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, StreamingResponse
from langchain_core.messages import BaseMessage
from langgraph.types import Command
from starlette.datastructures import UploadFile as StarletteUploadFile
from sqlalchemy.orm import Session

from db.repositories import (
    ChatFileRepository,
    ChatThreadFileRepository,
    CheckpointRepository,
    ModelSelectionRepository,
)
from exceptions import (
    ChatFileNotFoundError,
    ChatFileProcessingError,
    ChatModelLoadError,
    EmptyChatFileContentError,
    ModelCallExecutionError,
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
from services import (
    ChatFileService,
    ChatHistoryService,
    ModelSelectionService,
    UploadedChatFile,
)
from utils.tool_outputs import summarize_tool_output
from utils.i18n import localize_error, request_locale

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
                [{"loc": ("body", "command"), "msg": str(error), "type": "json_invalid"}]
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


def _agent_config(thread_id: str, *, recursion_limit: int) -> dict:
    return {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": recursion_limit,
    }


def _extract_content(messages: list[BaseMessage]) -> Any:
    if not messages:
        return ""

    last_message = messages[-1]
    content = last_message.content
    if _has_display_content(content):
        if isinstance(content, str):
            return content
        return _to_jsonable(content)

    reasoning_content = _extract_message_reasoning(last_message)
    if reasoning_content:
        return reasoning_content

    return _to_jsonable(content)


def _has_display_content(content: Any) -> bool:
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list | tuple):
        return len(content) > 0
    return content is not None


def _extract_message_reasoning(message: Any) -> str:
    additional_kwargs = getattr(message, "additional_kwargs", None)
    if not isinstance(additional_kwargs, dict):
        return ""

    reasoning_content = additional_kwargs.get("reasoning_content")
    if isinstance(reasoning_content, str) and reasoning_content.strip():
        return reasoning_content
    return ""


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseMessage):
        payload: dict[str, Any] = {
            "type": value.type,
            "content": value.content,
        }
        for attr in ("name", "tool_call_id", "status"):
            attr_value = getattr(value, attr, None)
            if attr_value is not None:
                payload[attr] = attr_value
        return payload
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_to_jsonable(item) for item in value]

    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


def _extract_chunk_text(chunk: Any) -> str:
    content = getattr(chunk, "content", chunk)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return ""


def _extract_chunk_reasoning(chunk: Any) -> str:
    additional_kwargs = getattr(chunk, "additional_kwargs", None)
    if not isinstance(additional_kwargs, dict):
        return ""

    reasoning_content = additional_kwargs.get("reasoning_content")
    return reasoning_content if isinstance(reasoning_content, str) else ""


def _extract_reasoning_duration_ms(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, float) and value >= 0:
        return round(value)
    return None


def _extract_event_output(event: dict[str, Any]) -> dict[str, Any] | None:
    data = event.get("data")
    if not isinstance(data, dict):
        return None
    output = data.get("output")
    return output if isinstance(output, dict) and "messages" in output else None


def _extract_interrupt_payloads(event: dict[str, Any]) -> list[dict[str, Any]]:
    data = event.get("data")
    if not isinstance(data, dict):
        return []

    chunk = data.get("chunk")
    if not isinstance(chunk, dict) or "__interrupt__" not in chunk:
        return []

    interrupts = chunk["__interrupt__"]
    if not isinstance(interrupts, list | tuple):
        interrupts = [interrupts]

    payloads: list[dict[str, Any]] = []
    for interrupt in interrupts:
        value = getattr(interrupt, "value", interrupt)
        interrupt_id = getattr(interrupt, "id", None)

        if isinstance(value, dict):
            payload: dict[str, Any] = {
                "type": value.get("type", "other"),
                "message": value.get("message"),
            }
            extra = {
                key: item
                for key, item in value.items()
                if key not in {"type", "message"}
            }
            payload.update(extra)
        else:
            payload = {
                "type": "other",
                "message": str(value),
            }

        if interrupt_id is not None:
            payload["id"] = interrupt_id
        payloads.append(payload)

    return payloads


def _is_tool_error_output(output: Any) -> bool:
    if getattr(output, "status", None) == "error":
        return True
    if isinstance(output, dict) and output.get("status") == "error":
        return True
    return False


def _is_query_interrupt_tool_error(tool_name: str, detail: str) -> bool:
    if tool_name != "query":
        return False
    return "Interrupt(" in detail and "type" in detail and "query" in detail


def _sse(event: str, data: dict) -> str:
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
    return history_service.list_histories(limit=limit, offset=offset)


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
        "The conversation cannot be retried or continued after deletion."
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
    session: Session = Depends(_get_request_db_session),
) -> Response:
    history_service = ChatHistoryService(
        CheckpointRepository(session),
        request.app.state.checkpointer,
    )
    deleted = history_service.delete_history(thread_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Chat history not found: {thread_id}",
        )
    _build_chat_file_service(request, session).delete_thread_attachments(thread_id)
    session.commit()
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
        404: _error_response("The requested chat file was not found.", example="Chat file not found: A1B2C3"),
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
        404: _error_response("The requested chat file was not found.", example="Chat file not found: A1B2C3"),
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
        "DatabaseCheckpointer. Supports JSON requests and multipart requests with files[] / file_ids[]."
    ),
    response_description="Returns the AI response and the conversation thread ID.",
    responses={
        404: _error_response("The requested model selection was not found.", example="Model selection not found: 1"),
        415: _error_response("The uploaded chat file type is not supported.", example="Unsupported chat file type: .exe"),
        422: _error_response("The chat attachment is invalid or could not be processed.", example="Uploaded chat file is empty."),
        502: _error_response("The model could not be loaded or called.", example="Model call failed after 3 retries."),
    },
)
async def chat(
    request: Request,
    session: Session = Depends(_get_request_db_session),
) -> AIChatResponse:
    payload = await _parse_ai_chat_payload(request, stream=False)
    selection = _get_model_selection(payload.selection_id, session)
    thread_id = _make_thread_id(payload.thread_id)
    chat_file_service = _build_chat_file_service(request, session)
    prepared_prompt = None
    try:
        prepared_prompt = chat_file_service.prepare_prompt(
            thread_id=thread_id,
            selection=selection,
            prompt=payload.prompt or "",
            file_ids=payload.file_ids,
            uploaded_files=payload.uploaded_files,
        )
        state = {
            "model": selection,
            "messages": [prepared_prompt.human_message],
        }
        final_state = await request.app.state.supervisor_agent.ainvoke(
            state,
            _agent_config(
                thread_id,
                recursion_limit=request.app.state.config.graph_recursion_limit,
            ),
        )
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
    except (ChatModelLoadError, ModelCallExecutionError, ValueError) as error:
        session.rollback()
        if prepared_prompt is not None:
            for path in prepared_prompt.created_file_paths:
                path.unlink(missing_ok=True)
        raise HTTPException(status_code=502, detail=str(error)) from error

    return AIChatResponse(
        thread_id=thread_id,
        content=_extract_content(final_state.get("messages", [])),
    )


@router.post(
    "/chat/stream",
    summary="Stream the AI chat API",
    description=(
        "Call SupervisorAgent with the selected model and return the thread, tool activity, "
        "interrupts, and final response over SSE. Send prompt for the first request; after an interrupt, "
        "reuse the thread_id with command.type=retry to retry a failed node or command.type=query to "
        "submit a query tool choice/note. Supports JSON and multipart requests with files[] / file_ids[]."
    ),
    response_description="Returns a text/event-stream response.",
    responses={
        200: {
            "description": (
                "Returns SSE events including thread, token, reasoning, reasoning_done, tool_start, "
                "tool_end, tool_error, interrupt, and final; failures use error. Query interrupts include "
                "question, firstChoice, firstChoiceDescription, secondChoice, secondChoiceDescription, "
                "thirdChoice, and thirdChoiceDescription. Search tool output contains only the safe frontend "
                "summary fields url, title, and favicon. The thread event also includes resolved_attachments, "
                "attachment_count, and requires_image_input."
            ),
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "example": 'event: final\ndata: {"content":"Hello"}\n\n',
                }
            },
        },
        404: _error_response("The requested model selection was not found.", example="Model selection not found: 1"),
        415: _error_response("The uploaded chat file type is not supported.", example="Unsupported chat file type: .exe"),
        422: _error_response("The chat attachment is invalid or could not be processed.", example="Uploaded chat file is empty."),
    },
)
async def chat_stream(
    request: Request,
    session: Session = Depends(_get_request_db_session),
) -> StreamingResponse:
    payload = await _parse_ai_chat_payload(request, stream=True)
    selection = _get_model_selection(payload.selection_id, session)

    command_type = payload.command.type if payload.command else "prompt"
    thread_id = payload.thread_id if command_type == "retry" else _make_thread_id(payload.thread_id)
    prepared_prompt = None

    if command_type in {"retry", "query"}:
        assert payload.command is not None
        chat_file_service = _build_chat_file_service(request, session)
        resume_payload: dict[str, Any]
        if command_type == "query":
            resume_payload = {
                "choice": payload.command.choice,
                "note": payload.command.note,
            }
        else:
            resume_payload = payload.command.model_dump(exclude_none=True)
        agent_input: dict[str, Any] | Command = Command(
            resume=resume_payload
        )
        requires_image_input = chat_file_service.thread_requires_image_input(thread_id or "")
        attachment_count = ChatThreadFileRepository(session).count_by_thread(thread_id or "")
        resolved_attachments: list[dict[str, Any]] = []
    else:
        prompt = payload.command.prompt if payload.command and payload.command.prompt else payload.prompt
        chat_file_service = _build_chat_file_service(request, session)
        try:
            prepared_prompt = chat_file_service.prepare_prompt(
                thread_id=thread_id or "",
                selection=selection,
                prompt=prompt or "",
                file_ids=payload.file_ids,
                uploaded_files=payload.uploaded_files,
            )
        except (
            ChatFileNotFoundError,
            ChatFileProcessingError,
            EmptyChatFileContentError,
            ResumeValidationError,
            UnsupportedChatFileError,
        ) as error:
            session.rollback()
            _raise_chat_input_error(error)

        agent_input = {
            "model": selection,
            "messages": [prepared_prompt.human_message],
        }
        requires_image_input = prepared_prompt.requires_image_input
        attachment_count = prepared_prompt.attachment_count
        resolved_attachments = [
            attachment.model_dump(mode="json")
            for attachment in prepared_prompt.attachments
        ]
        session.commit()

    async def event_stream() -> AsyncGenerator[str, None]:
        yield _sse(
            "thread",
            {
                "thread_id": thread_id,
                "resolved_attachments": resolved_attachments,
                "attachment_count": attachment_count,
                "requires_image_input": requires_image_input,
            },
        )
        final_state: dict[str, Any] | None = None
        try:
            async for event in request.app.state.supervisor_agent.astream_events(
                agent_input,
                _agent_config(
                    thread_id,
                    recursion_limit=request.app.state.config.graph_recursion_limit,
                ),
                version="v2",
            ):
                event_name = event.get("event")
                data = event.get("data") if isinstance(event.get("data"), dict) else {}
                tool_name = str(event.get("name") or "")

                interrupt_payloads = _extract_interrupt_payloads(event)
                if interrupt_payloads:
                    for interrupt_payload in interrupt_payloads:
                        message = interrupt_payload.get("message")
                        if isinstance(message, str):
                            interrupt_payload["message"] = localize_error(
                                message,
                                request_locale(request),
                            )
                        yield _sse(
                            "interrupt",
                            {
                                "thread_id": thread_id,
                                **interrupt_payload,
                            },
                        )
                    return

                if event_name == "on_tool_start":
                    yield _sse(
                        "tool_start",
                        {
                            "thread_id": thread_id,
                            "tool_name": tool_name,
                            "input": data.get("input"),
                        },
                    )
                    continue

                if event_name == "on_tool_end":
                    output = data.get("output")
                    if _is_tool_error_output(output):
                        yield _sse(
                            "tool_error",
                            {
                                "thread_id": thread_id,
                                "tool_name": tool_name,
                                "detail": _extract_content([output])
                                if isinstance(output, BaseMessage)
                                else str(output),
                            },
                        )
                        continue

                    yield _sse(
                        "tool_end",
                        {
                            "thread_id": thread_id,
                            "tool_name": tool_name,
                            "output": summarize_tool_output(tool_name, output),
                        },
                    )
                    continue

                if event_name == "on_tool_error":
                    detail = str(data.get("error") or data.get("output") or "")
                    if _is_query_interrupt_tool_error(tool_name, detail):
                        continue
                    yield _sse(
                        "tool_error",
                        {
                            "thread_id": thread_id,
                            "tool_name": tool_name,
                            "detail": detail,
                        },
                    )
                    continue

                if event_name == "on_custom_event" and tool_name == "on_reasoning_done":
                    duration_ms = _extract_reasoning_duration_ms(data.get("duration_ms"))
                    if duration_ms is not None:
                        yield _sse(
                            "reasoning_done",
                            {
                                "thread_id": thread_id,
                                "duration_ms": duration_ms,
                            },
                        )
                    continue

                if event_name in {"on_chat_model_stream", "on_llm_stream"}:
                    chunk = data.get("chunk")
                    text = _extract_chunk_text(chunk)
                    if text:
                        yield _sse(
                            "token",
                            {
                                "thread_id": thread_id,
                                "content": text,
                            },
                        )
                    else:
                        reasoning = _extract_chunk_reasoning(chunk)
                        if reasoning:
                            yield _sse(
                                "reasoning",
                                {
                                    "thread_id": thread_id,
                                    "content": reasoning,
                                },
                            )

                output = _extract_event_output(event)
                if output is not None:
                    final_state = output
        except Exception as error:
            yield _sse(
                "error",
                {"detail": localize_error(error, request_locale(request))},
            )
            return

        yield _sse(
            "final",
            {
                "thread_id": thread_id,
                "content": _extract_content(
                    final_state.get("messages", []) if final_state else []
                ),
            },
        )

    return StreamingResponse(event_stream(), media_type="text/event-stream")
