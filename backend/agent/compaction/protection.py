from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from .errors import ContextCompactionError
from .models import CompactedMessage

_INVALID_EXCHANGE = "Invalid tool exchange"
_MEDIA_BLOCKS = {
    "image",
    "image_url",
    "input_image",
    "file",
    "input_file",
    "document",
    "audio",
    "input_audio",
    "video",
}


def tool_call_names(message: AIMessage) -> dict[str, str]:
    if message.invalid_tool_calls:
        raise ContextCompactionError(f"{_INVALID_EXCHANGE}: malformed tool call.")
    calls: dict[str, str] = {}
    for call in message.tool_calls:
        call_id = call.get("id")
        if not call_id or not call_id.strip() or call_id in calls:
            raise ContextCompactionError(
                f"{_INVALID_EXCHANGE}: missing or duplicate call ID."
            )
        calls[call_id] = call["name"]
    return calls


def message_groups(messages: Sequence[BaseMessage]) -> list[range]:
    """Group complete exchanges atomically and reject ambiguous provider history."""
    groups: list[range] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        end = index + 1
        if isinstance(message, ToolMessage):
            raise ContextCompactionError(f"{_INVALID_EXCHANGE}: orphan tool result.")
        if isinstance(message, AIMessage):
            calls = tool_call_names(message)
            if calls:
                unanswered = dict(calls)
                while end < len(messages) and isinstance(
                    result := messages[end], ToolMessage
                ):
                    tool_name = unanswered.pop(result.tool_call_id, None)
                    if tool_name is None or (result.name and result.name != tool_name):
                        raise ContextCompactionError(
                            f"{_INVALID_EXCHANGE}: unmatched or duplicate tool result."
                        )
                    if result.content == "[INTERRUPT_TOOL_CALLED]":
                        raise ContextCompactionError(
                            f"{_INVALID_EXCHANGE}: unfinished tool call."
                        )
                    end += 1
                if unanswered:
                    raise ContextCompactionError(
                        f"{_INVALID_EXCHANGE}: unfinished tool call."
                    )
        groups.append(range(index, end))
        index = end
    return groups


def has_indispensable_payload(message: BaseMessage) -> bool:
    if isinstance(message, HumanMessage):
        return isinstance(message.content, list) or bool(
            message.additional_kwargs.get("attachments")
        )
    return isinstance(message.content, list) and any(
        isinstance(block, dict)
        and (
            block.get("type") in _MEDIA_BLOCKS
            or (isinstance(message, ToolMessage) and block.get("type") != "text")
        )
        for block in message.content
    )


def protect_entries(
    entries: Sequence[CompactedMessage],
    *,
    keep_recent_turns: int,
) -> tuple[CompactedMessage, ...]:
    """Protect user input and evidence. Give recent history a soft priority."""
    if keep_recent_turns < 0:
        raise ValueError("keep_recent_turns must be non-negative.")

    users = [
        index
        for index, entry in enumerate(entries)
        if entry.kind != "summary" and isinstance(entry.rendered, HumanMessage)
    ]
    current_user = users[-1] if users else None
    recent_start = (
        users[-keep_recent_turns]
        if 0 < keep_recent_turns < len(users)
        else (users[0] if users and keep_recent_turns else len(entries))
    )
    protected_entries: list[CompactedMessage] = []
    for group in message_groups([entry.rendered for entry in entries]):
        protected = any(
            index == current_user
            or entries[index].protected
            or isinstance(entries[index].rendered, SystemMessage)
            or has_indispensable_payload(entries[index].rendered)
            for index in group
        )
        protected_entries.extend(
            replace(entries[index], protected=protected, recent=index >= recent_start)
            for index in group
        )
    return tuple(protected_entries)
