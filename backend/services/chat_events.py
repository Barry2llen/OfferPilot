from typing import Any

from langchain_core.messages import BaseMessage

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
    additional_kwargs = getattr(message, "additional_kwargs", None)
    if not isinstance(additional_kwargs, dict):
        return ""

    reasoning_content = additional_kwargs.get("reasoning_content")
    if isinstance(reasoning_content, str) and reasoning_content.strip():
        return reasoning_content
    return ""


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


def _is_tool_error_output(output: Any) -> bool:
    if getattr(output, "status", None) == "error":
        return True
    if isinstance(output, dict) and output.get("status") == "error":
        return True
    return False
