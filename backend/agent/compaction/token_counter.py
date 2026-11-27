from __future__ import annotations

import json
from collections.abc import Sequence
from math import ceil
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from .protocols import TokenCounter, ToolSchema

_IMAGE_BLOCKS = {"image", "image_url", "input_image"}
_TOKENS_PER_IMAGE = 2_048


def _wire_tokens(value: Any) -> int:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return ceil(len(encoded.encode("utf-8", errors="surrogatepass")) / 3)


def _message_tokens(message: BaseMessage) -> int:
    content = message.content
    image_tokens = 0
    if isinstance(content, list):
        blocks = []
        for block in content:
            if isinstance(block, dict) and block.get("type") in _IMAGE_BLOCKS:
                image_tokens += _TOKENS_PER_IMAGE
                blocks.append({"type": block["type"]})
            else:
                blocks.append(block)
        content = blocks

    wire: dict[str, Any] = {"role": message.type, "content": content}
    if message.name:
        wire["name"] = message.name
    if isinstance(message, AIMessage):
        if message.tool_calls:
            wire["tool_calls"] = message.tool_calls
        for key in ("reasoning_content", "function_call"):
            if key in message.additional_kwargs:
                wire[key] = message.additional_kwargs[key]
    elif isinstance(message, ToolMessage):
        wire["tool_call_id"] = message.tool_call_id
        wire["status"] = message.status

    return _wire_tokens(wire) + image_tokens + 3


class ApproximateTokenCounter(TokenCounter):
    """Estimate serialized inputs, plus a fixed allowance per image and message."""

    async def acount(
        self,
        *,
        system_prompts: Sequence[BaseMessage],
        messages: Sequence[BaseMessage],
        tools: Sequence[ToolSchema],
    ) -> int:
        tool_tokens = (
            _wire_tokens(
                [
                    convert_to_openai_tool(tool) if isinstance(tool, BaseTool) else tool
                    for tool in tools
                ]
            )
            if tools
            else 0
        )
        return tool_tokens + sum(
            _message_tokens(message) for message in (*system_prompts, *messages)
        )


__all__ = ["ApproximateTokenCounter"]
