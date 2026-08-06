import json
from collections.abc import Mapping
from typing import Any

from langchain_core.messages import BaseMessage

from agent.checkpointers import DatabaseCheckpointer
from db.models import GraphCheckpointORM
from db.repositories import CheckpointRepository, ChatThreadFileRepository
from schemas.ai import (
    AIChatHistoryDetailResponse,
    AIChatHistoryListResponse,
    AIChatHistoryMessage,
    AIChatHistorySummary,
)
from schemas.chat_file import ChatAttachmentRef
from utils.tool_outputs import QUERY_TOOL_NAME, summarize_tool_output


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
        thread_file_repository: ChatThreadFileRepository | None = None,
    ) -> None:
        self._repository = repository
        self._checkpointer = checkpointer
        self._thread_file_repository = thread_file_repository

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

        checkpoint_state = self._get_checkpoint_state(row.thread_id)
        messages = self._messages_from_state(checkpoint_state)
        normalized_messages = _to_history_messages(messages)
        summary = _build_summary(
            row,
            messages,
            self._thread_file_repository,
            context_compacted=_has_auto_compacted_context(checkpoint_state),
        )
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
        checkpoint_state = self._get_checkpoint_state(row.thread_id)
        messages = self._messages_from_state(checkpoint_state)
        return _build_summary(
            row,
            messages,
            self._thread_file_repository,
            context_compacted=_has_auto_compacted_context(checkpoint_state),
        )

    def _get_checkpoint_state(self, thread_id: str) -> dict[str, Any]:
        checkpoint_tuple = self._checkpointer.get_tuple(
            {"configurable": {"thread_id": thread_id}}
        )
        if checkpoint_tuple is None:
            return {}

        channel_values = checkpoint_tuple.checkpoint.get("channel_values", {})
        return channel_values if isinstance(channel_values, dict) else {}

    @staticmethod
    def _messages_from_state(state: Mapping[str, Any]) -> list[Any]:
        messages = state.get("messages")
        return messages if isinstance(messages, list) else []


def _build_summary(
    row: GraphCheckpointORM,
    messages: list[Any],
    thread_file_repository: ChatThreadFileRepository | None = None,
    *,
    context_compacted: bool = False,
) -> AIChatHistorySummary:
    attachment_count = (
        thread_file_repository.count_by_thread(row.thread_id)
        if thread_file_repository is not None
        else 0
    )
    requires_image_input = (
        thread_file_repository.has_image_mode(row.thread_id)
        if thread_file_repository is not None
        else False
    )
    return AIChatHistorySummary(
        thread_id=row.thread_id,
        title=_build_title(row.thread_id, messages),
        last_message_preview=_truncate(_message_text(messages[-1]), 80)
        if messages
        else "",
        message_count=len(messages),
        attachment_count=attachment_count,
        requires_image_input=requires_image_input,
        context_compacted=context_compacted,
        updated_at=row.created_at,
    )


def _has_auto_compacted_context(state: Mapping[str, Any]) -> bool:
    snapshot = state.get("context_compaction")
    return isinstance(snapshot, Mapping) and snapshot.get("auto_compacted") is True


def _build_title(thread_id: str, messages: list[Any]) -> str:
    for message in messages:
        if _message_type(message) == "human":
            title = _truncate(_message_text(message).strip(), 40)
            if title:
                return title
    return thread_id


def _to_history_messages(messages: list[Any]) -> list[AIChatHistoryMessage]:
    normalized: list[AIChatHistoryMessage] = []
    for message in messages:
        normalized.append(_to_history_message(message))
    return normalized


def _to_history_message(message: Any) -> AIChatHistoryMessage:
    message_type = _message_type(message)
    message_name = _message_attr(message, "name")
    content = _message_content(message)
    if message_type == "human":
        display_content = _message_display_content(message)
        if display_content is not None:
            content = display_content
    reasoning = _message_reasoning_content(message)
    if message_type == "ai" and not _has_display_content(content) and reasoning:
        content = ""

    if message_type == "tool" and message_name is not None:
        tool_output = message if str(message_name) == QUERY_TOOL_NAME else content
        content = summarize_tool_output(str(message_name), tool_output)

    payload: dict[str, Any] = {
        "role": _ROLE_BY_MESSAGE_TYPE.get(message_type, message_type),
        "type": message_type,
        "content": _jsonable(content),
    }
    attachments = _message_attachments(message)
    if attachments:
        payload["attachments"] = [item.model_dump(mode="json") for item in attachments]
    if reasoning:
        payload["reasoning"] = reasoning
        reasoning_duration_ms = _message_reasoning_duration_ms(message)
        if reasoning_duration_ms is not None:
            payload["reasoning_duration_ms"] = reasoning_duration_ms
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
        return message.content
    if isinstance(message, dict) and "content" in message:
        return message["content"]
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


def _message_display_content(message: Any) -> str | None:
    additional_kwargs = _message_attr(message, "additional_kwargs")
    if not isinstance(additional_kwargs, dict):
        return None

    display_content = additional_kwargs.get("display_content")
    if isinstance(display_content, str):
        return display_content
    return None


def _message_attachments(message: Any) -> list[ChatAttachmentRef]:
    additional_kwargs = _message_attr(message, "additional_kwargs")
    if not isinstance(additional_kwargs, dict):
        return []

    attachments = additional_kwargs.get("attachments")
    if not isinstance(attachments, list):
        return []

    normalized: list[ChatAttachmentRef] = []
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        try:
            normalized.append(ChatAttachmentRef(**attachment))
        except Exception:
            continue
    return normalized


def _message_reasoning_duration_ms(message: Any) -> int | None:
    additional_kwargs = _message_attr(message, "additional_kwargs")
    if not isinstance(additional_kwargs, dict):
        return None

    duration_ms = additional_kwargs.get("reasoning_duration_ms")
    if isinstance(duration_ms, bool):
        return None
    if isinstance(duration_ms, int) and duration_ms >= 0:
        return duration_ms
    if isinstance(duration_ms, float) and duration_ms >= 0:
        return round(duration_ms)
    return None


def _has_display_content(content: Any) -> bool:
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list | tuple):
        return len(content) > 0
    return content is not None


def _message_text(message: Any) -> str:
    display_content = _message_display_content(message)
    if display_content is not None:
        return display_content

    content = _message_content(message)
    text = _content_text(content)
    if text:
        return text
    reasoning = _message_reasoning_content(message)
    if reasoning:
        return reasoning
    return json.dumps(_jsonable(content), ensure_ascii=False)


def _content_text(content: Any) -> str:
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
    return ""


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
