import json
from collections.abc import AsyncGenerator, Generator
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.types import Command
from sqlalchemy.orm import Session

from db.repositories import ModelSelectionRepository
from exceptions import ChatModelLoadError, ModelCallExecutionError
from schemas.ai import AIChatRequest, AIChatResponse, AIChatStreamRequest
from services import ModelSelectionService

router = APIRouter(prefix="/ai", tags=["ai"])

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


def _make_thread_id(thread_id: str | None) -> str:
    return thread_id or uuid4().hex


def _agent_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _extract_content(messages: list[BaseMessage]) -> str:
    if not messages:
        return ""

    last_message = messages[-1]
    content = last_message.content
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


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


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(_to_jsonable(data), ensure_ascii=False)}\n\n"


@router.post(
    "/chat",
    response_model=AIChatResponse,
    summary="调用基础 AI 对话",
    description="使用指定模型选择记录调用 SupervisorAgent，并通过 DatabaseCheckpointer 保存会话状态。",
    response_description="返回 AI 最终回复和本次会话线程 ID。",
    responses={
        404: _error_response("未找到指定模型选择配置。", example="Model selection not found: 1"),
        502: _error_response("模型加载或调用失败。", example="Model call failed after 3 retries."),
    },
)
async def chat(
    payload: AIChatRequest,
    request: Request,
    session: Session = Depends(_get_request_db_session),
) -> AIChatResponse:
    selection_service = ModelSelectionService(ModelSelectionRepository(session))
    selection = selection_service.get_by_id(payload.selection_id)
    if selection is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model selection not found: {payload.selection_id}",
        )

    thread_id = _make_thread_id(payload.thread_id)
    state = {
        "model": selection,
        "messages": [HumanMessage(content=payload.prompt)],
    }

    try:
        final_state = await run_in_threadpool(
            request.app.state.supervisor_agent.invoke,
            state,
            _agent_config(thread_id),
        )
    except (ChatModelLoadError, ModelCallExecutionError, ValueError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    return AIChatResponse(
        thread_id=thread_id,
        content=_extract_content(final_state.get("messages", [])),
    )


@router.post(
    "/chat/stream",
    summary="流式调用基础 AI 对话",
    description=(
        "使用指定模型选择记录调用 SupervisorAgent，并以 SSE 返回会话线程、工具调用过程、"
        "失败中断和最终回复。首次请求传 prompt；收到 interrupt 后可使用同一 thread_id "
        "和 command.type=retry 恢复失败节点。"
    ),
    response_description="返回 text/event-stream 事件流。",
    responses={
        200: {
            "description": (
                "返回 SSE 事件流。事件包括 thread、token、tool_start、tool_end、"
                "tool_error、interrupt、final，失败时返回 error。"
            ),
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "example": 'event: final\ndata: {"content":"你好"}\n\n',
                }
            },
        },
        404: _error_response("未找到指定模型选择配置。", example="Model selection not found: 1"),
    },
)
async def chat_stream(
    payload: AIChatStreamRequest,
    request: Request,
    session: Session = Depends(_get_request_db_session),
) -> StreamingResponse:
    selection_service = ModelSelectionService(ModelSelectionRepository(session))
    selection = selection_service.get_by_id(payload.selection_id)
    if selection is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model selection not found: {payload.selection_id}",
        )

    command_type = payload.command.type if payload.command else "prompt"
    thread_id = payload.thread_id if command_type == "retry" else _make_thread_id(payload.thread_id)

    if command_type == "retry":
        assert payload.command is not None
        agent_input: dict[str, Any] | Command = Command(
            resume=payload.command.model_dump(exclude_none=True)
        )
    else:
        prompt = payload.command.prompt if payload.command and payload.command.prompt else payload.prompt
        agent_input = {
            "model": selection,
            "messages": [HumanMessage(content=prompt or "")],
        }

    async def event_stream() -> AsyncGenerator[str, None]:
        yield _sse("thread", {"thread_id": thread_id})
        final_state: dict[str, Any] | None = None
        try:
            async for event in request.app.state.supervisor_agent.astream_events(
                agent_input,
                _agent_config(thread_id),
                version="v2",
            ):
                event_name = event.get("event")
                data = event.get("data") if isinstance(event.get("data"), dict) else {}
                tool_name = str(event.get("name") or "")

                interrupt_payloads = _extract_interrupt_payloads(event)
                if interrupt_payloads:
                    for interrupt_payload in interrupt_payloads:
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
                            "output": output,
                        },
                    )
                    continue

                if event_name == "on_tool_error":
                    yield _sse(
                        "tool_error",
                        {
                            "thread_id": thread_id,
                            "tool_name": tool_name,
                            "detail": str(data.get("error") or data.get("output") or ""),
                        },
                    )
                    continue

                if event_name in {"on_chat_model_stream", "on_llm_stream"}:
                    text = _extract_chunk_text(data.get("chunk"))
                    if text:
                        yield _sse(
                            "token",
                            {
                                "thread_id": thread_id,
                                "content": text,
                            },
                        )

                output = _extract_event_output(event)
                if output is not None:
                    final_state = output
        except Exception as error:
            yield _sse("error", {"detail": str(error)})
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
