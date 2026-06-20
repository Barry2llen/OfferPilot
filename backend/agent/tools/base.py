from __future__ import annotations

import inspect
from typing import Protocol
from collections.abc import AsyncIterable, Awaitable, Iterable

from langgraph._internal._typing import StateLike
from langchain_core.tools import BaseTool

from schemas.config import Config

from ..base import BaseAgentState, GraphRuntime
from .query import query
from .web_search import get_web_search_tools

type Tools = Iterable[BaseTool] | Awaitable[Iterable[BaseTool]] | AsyncIterable[BaseTool]

class ToolsBuilder[State: StateLike = BaseAgentState](Protocol):
    def __call__(self, runtime: GraphRuntime[State]) -> Tools: ...


async def _collect_tools(tools: Tools) -> tuple[BaseTool, ...]:
    if inspect.isawaitable(tools):
        tools = await tools

    if isinstance(tools, AsyncIterable):
        return tuple([tool async for tool in tools])

    if isinstance(tools, Iterable):
        return tuple(tools)

    raise TypeError(f"Expected tools iterable, got {type(tools).__name__}")


def normalize_tools[State: StateLike = BaseAgentState](tools: Tools | ToolsBuilder[State] | None) -> ToolsBuilder[State]:
    if tools is None:
        return lambda runtime: ()

    if callable(tools):
        return tools

    if isinstance(tools, Iterable):
        resolved_tools = tuple(tools)
        return lambda runtime: resolved_tools

    cached_tools: tuple[BaseTool, ...] | None = None

    async def build_tools(runtime: GraphRuntime[State]) -> tuple[BaseTool, ...]:
        nonlocal cached_tools
        if cached_tools is None:
            cached_tools = await _collect_tools(tools)
        return cached_tools

    return build_tools


async def resolve_tools[State: StateLike = BaseAgentState](
    tools_builder: ToolsBuilder[State],
    runtime: GraphRuntime[State],
) -> tuple[BaseTool, ...]:
    return await _collect_tools(tools_builder(runtime))


async def get_all_tools(
    config: Config | None = None
) -> list[BaseTool]:
    tools = await get_web_search_tools(config)
    return [*tools, query]

async def get_tools(*names: str, config: Config | None = None) -> list[BaseTool]:
    all_tools = await get_all_tools(config)
    name_set = set(names)
    return [tool for tool in all_tools if tool.name in name_set]

__all__ = [
    "Tools",
    "ToolsBuilder",
    "normalize_tools",
    "resolve_tools",
    "get_all_tools",
    "get_tools"
]
