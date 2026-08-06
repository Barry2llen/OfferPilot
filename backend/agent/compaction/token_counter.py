from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from .protocols import TokenCounter


def _canonicalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if hasattr(value, "model_dump"):
        return _canonicalize(value.model_dump(mode="json"))
    return value


def _tool_schema(tool: BaseTool) -> dict[str, Any]:
    try:
        converted = convert_to_openai_tool(tool)
    except Exception:
        raw_schema = getattr(tool, "tool_call_schema", {})
        if hasattr(raw_schema, "model_json_schema"):
            parameters = raw_schema.model_json_schema()
        elif isinstance(raw_schema, Mapping):
            parameters = dict(raw_schema)
        else:
            parameters = {"type": "object", "properties": {}}
        converted = {
            "type": "function",
            "function": {
                "name": str(getattr(tool, "name", "unknown")),
                "description": str(getattr(tool, "description", "") or ""),
                "parameters": parameters,
            },
        }
    canonical = _canonicalize(converted)
    if not isinstance(canonical, dict):
        raise TypeError("Tool schema conversion must produce a mapping.")
    # Force a stable JSON-compatible traversal now so token estimates do not rely
    # on object reprs or insertion order from provider adapters.
    json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return canonical


class ApproximateTokenCounter(TokenCounter):
    """Use LangChain's approximate counter with stable tool schemas."""

    async def acount(
        self,
        *,
        system_prompts: Sequence[BaseMessage],
        messages: Sequence[BaseMessage],
        tools: Sequence[BaseTool],
    ) -> int:
        all_messages = [*system_prompts, *messages]
        stable_tools = [_tool_schema(tool) for tool in tools]
        return count_tokens_approximately(
            all_messages,
            tools=stable_tools,
        )


__all__ = ["ApproximateTokenCounter"]
