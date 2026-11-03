from typing import Any

from langchain_core.messages import BaseMessage

from utils.message_content import extract_message_reasoning, extract_text_content
from utils.stream import to_jsonable


def _extract_content(messages: list[BaseMessage]) -> Any:
    if not messages:
        return ""

    last_message = messages[-1]
    content = last_message.content
    if _has_display_content(content):
        if isinstance(content, str):
            return content
        return to_jsonable(content)

    reasoning_content = _extract_message_reasoning(last_message)
    if reasoning_content:
        return reasoning_content

    return to_jsonable(content)


def _has_display_content(content: Any) -> bool:
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list | tuple):
        return len(content) > 0
    return content is not None


def _extract_message_reasoning(message: Any) -> str:
    reasoning = extract_message_reasoning(message)
    return reasoning if reasoning.strip() else ""


def _extract_chunk_text(chunk: Any) -> str:
    return extract_text_content(getattr(chunk, "content", chunk))


def _extract_chunk_reasoning(chunk: Any) -> str:
    return extract_message_reasoning(chunk)


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


def _is_tool_error_output(output: Any) -> bool:
    if getattr(output, "status", None) == "error":
        return True
    if isinstance(output, dict) and output.get("status") == "error":
        return True
    return False
