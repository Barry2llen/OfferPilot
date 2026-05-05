import json
from typing import Any

from langchain_core.messages import BaseMessage

from agent.checkpointers import DatabaseCheckpointer
from db.models import GraphCheckpointORM
from db.repositories import CheckpointRepository
from schemas.ai import (
    AIChatHistoryDetailResponse,
    AIChatHistoryListResponse,
    AIChatHistoryMessage,
    AIChatHistorySummary,
)


_ROLE_BY_MESSAGE_TYPE = {
    "human": "user",
    "ai": "assistant",
    "tool": "tool",
}


class ChatHistoryService:
    """Read chat history from the latest LangGraph checkpoint per thread."""

    def __init__(
        self,
        repository: CheckpointRepository,
        checkpointer: DatabaseCheckpointer,
    ) -> None:
        self._repository = repository
        self._checkpointer = checkpointer

    def list_histories(
        self,
        *,
        limit: int,
        offset: int,
    ) -> AIChatHistoryListResponse:
        rows = self._repository.list_latest_checkpoints_by_thread(
            limit=limit,
            offset=offset,
        )
        return AIChatHistoryListResponse(
            items=[self._to_summary(row) for row in rows],
            limit=limit,
            offset=offset,
        )

    def get_history(self, thread_id: str) -> AIChatHistoryDetailResponse | None:
        row = self._repository.get_checkpoint(thread_id, "")
        if row is None:
            return None

        messages = self._get_messages(row.thread_id)
        normalized_messages = [_to_history_message(message) for message in messages]
        summary = _build_summary(row, messages)
        return AIChatHistoryDetailResponse(
            **summary.model_dump(),
            messages=normalized_messages,
        )

    def delete_history(self, thread_id: str) -> bool:
        row = self._repository.get_checkpoint(thread_id, "")
        if row is None:
            return False

        self._repository.delete_thread(thread_id)
        return True

    def _to_summary(self, row: GraphCheckpointORM) -> AIChatHistorySummary:
        return _build_summary(row, self._get_messages(row.thread_id))

    def _get_messages(self, thread_id: str) -> list[Any]:
        checkpoint_tuple = self._checkpointer.get_tuple(
            {"configurable": {"thread_id": thread_id}}
        )
        if checkpoint_tuple is None:
            return []

        messages = checkpoint_tuple.checkpoint.get("channel_values", {}).get("messages")
        return messages if isinstance(messages, list) else []


def _build_summary(
    row: GraphCheckpointORM,
    messages: list[Any],
) -> AIChatHistorySummary:
    return AIChatHistorySummary(
        thread_id=row.thread_id,
        title=_build_title(row.thread_id, messages),
        last_message_preview=_truncate(_message_text(messages[-1]), 80)
        if messages
        else "",
        message_count=len(messages),
        updated_at=row.created_at,
    )


def _build_title(thread_id: str, messages: list[Any]) -> str:
    for message in messages:
        if _message_type(message) == "human":
            title = _truncate(_message_text(message).strip(), 40)
            if title:
                return title
    return thread_id


def _to_history_message(message: Any) -> AIChatHistoryMessage:
    message_type = _message_type(message)
    payload: dict[str, Any] = {
        "role": _ROLE_BY_MESSAGE_TYPE.get(message_type, message_type),
        "type": message_type,
        "content": _jsonable(_message_content(message)),
    }
    for attr in ("name", "tool_call_id", "status"):
        value = _message_attr(message, attr)
        if value is not None:
            payload[attr] = str(value)
    return AIChatHistoryMessage(**payload)


def _message_type(message: Any) -> str:
    if isinstance(message, BaseMessage):
        return message.type
    if isinstance(message, dict):
        return str(message.get("type") or "message")
    return "message"


def _message_content(message: Any) -> Any:
    if isinstance(message, BaseMessage):
        if _has_display_content(message.content):
            return message.content
        reasoning_content = _message_reasoning_content(message)
        return reasoning_content or message.content
    if isinstance(message, dict) and "content" in message:
        content = message["content"]
        if _has_display_content(content):
            return content
        reasoning_content = _message_reasoning_content(message)
        return reasoning_content or content
    return message


def _message_attr(message: Any, attr: str) -> Any:
    if isinstance(message, BaseMessage):
        return getattr(message, attr, None)
    if isinstance(message, dict):
        return message.get(attr)
    return None


def _message_reasoning_content(message: Any) -> str:
    additional_kwargs = _message_attr(message, "additional_kwargs")
    if not isinstance(additional_kwargs, dict):
        return ""

    reasoning_content = additional_kwargs.get("reasoning_content")
    if isinstance(reasoning_content, str) and reasoning_content.strip():
        return reasoning_content
    return ""


def _has_display_content(content: Any) -> bool:
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list | tuple):
        return len(content) > 0
    return content is not None


def _message_text(message: Any) -> str:
    content = _message_content(message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        if parts:
            return "".join(parts)
    return json.dumps(_jsonable(content), ensure_ascii=False)


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseMessage):
        return _to_history_message(value).model_dump(exclude_none=True)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]

    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


def _truncate(value: str, limit: int) -> str:
    return value[:limit]
