from typing import Any


def extract_text_content(content: Any) -> str:
    """Read visible text without mixing provider reasoning blocks into the answer."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif (
            isinstance(block, dict)
            and block.get("type") in (None, "text", "output_text")
            and isinstance(block.get("text"), str)
        ):
            parts.append(block["text"])
    return "".join(parts)


def extract_message_reasoning(message: Any) -> str:
    """Read provider content blocks or legacy metadata, preserving stream whitespace."""
    content = (
        message.get("content")
        if isinstance(message, dict)
        else getattr(message, "content", None)
    )
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict) or block.get("type") not in {
                "reasoning",
                "thinking",
                "reasoning_text",
                "summary_text",
            }:
                continue
            value = block.get("text") or block.get("thinking") or block.get("reasoning")
            if isinstance(value, str):
                parts.append(value)
            summary = block.get("summary")
            if isinstance(summary, list):
                for item in summary:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        parts.append(item["text"])
        if parts:
            return "".join(parts)
    additional_kwargs = (
        message.get("additional_kwargs")
        if isinstance(message, dict)
        else getattr(message, "additional_kwargs", None)
    )
    if not isinstance(additional_kwargs, dict):
        return ""
    reasoning = additional_kwargs.get("reasoning_content")
    return reasoning if isinstance(reasoning, str) else ""
