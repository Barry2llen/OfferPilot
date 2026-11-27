"""Background tool batches owned by a single chat run."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, ToolCall, ToolMessage
from pydantic import BaseModel, Field

from utils.logger import logger

ASYNC_TOOL_BATCH_ID = "async_tool_batch_id"

type NotifyMode = Literal["all", "any"]


class AsyncToolCall(BaseModel):
    name: str = Field(
        description="Name of another tool available to the agent.",
        examples=["analyze_resume"],
        min_length=1,
    )
    args: dict[str, Any] = Field(
        description="Arguments matching that tool's schema.",
        examples=[{"resume_id": 1}],
    )


type SubmitAsyncTools = Callable[[list[AsyncToolCall], NotifyMode], str]
type ToolResult = tuple[ToolCall, ToolMessage]


@dataclass
class _Batch:
    notify: NotifyMode
    pending: int
    results: dict[int, ToolResult] = field(default_factory=dict)

    def ordered_results(self) -> list[ToolResult]:
        return [self.results[index] for index in sorted(self.results)]


class AsyncToolRun:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[ToolMessage]] = set()
        self._batches: dict[str, _Batch] = {}
        self._ready: list[tuple[str, list[ToolResult]]] = []
        self._available = asyncio.Event()

    @property
    def has_work(self) -> bool:
        return bool(self._batches or self._ready)

    @property
    def has_results(self) -> bool:
        return bool(self._ready)

    def submit(
        self,
        requests: list[AsyncToolCall],
        notify: NotifyMode,
        execute: Callable[[ToolCall], Awaitable[ToolMessage]],
    ) -> str:
        batch_id = uuid4().hex
        calls: list[ToolCall] = [
            {
                "type": "tool_call",
                "name": request.name,
                "args": request.args,
                "id": f"call_{uuid4().hex}",
            }
            for request in requests
        ]
        self._batches[batch_id] = _Batch(notify, len(calls))
        for index, call in enumerate(calls):
            self._start(batch_id, index, call, execute)
        return json.dumps(
            {
                "batch_id": batch_id,
                "status": "scheduled",
                "notify": notify,
                "calls": [
                    {"tool_call_id": call["id"], "name": call["name"]} for call in calls
                ],
            }
        )

    def _start(
        self,
        batch_id: str,
        index: int,
        call: ToolCall,
        execute: Callable[[ToolCall], Awaitable[ToolMessage]],
    ) -> None:
        async def invoke() -> ToolMessage:
            return await execute(call)

        task = asyncio.create_task(invoke())
        self._tasks.add(task)
        task.add_done_callback(
            lambda completed: self._complete(completed, batch_id, index, call)
        )

    def _complete(
        self,
        task: asyncio.Task[ToolMessage],
        batch_id: str,
        index: int,
        call: ToolCall,
    ) -> None:
        self._tasks.discard(task)
        try:
            message = task.result()
        except asyncio.CancelledError:
            message = self._error(call, "Background tool was cancelled.")
        except Exception:
            logger.exception("Background tool {} failed unexpectedly", call["name"])
            message = self._error(call, "Background tool execution failed.")

        batch = self._batches[batch_id]
        batch.pending -= 1
        result = (call, message)
        if batch.notify == "any":
            self._ready.append((batch_id, [result]))
        else:
            batch.results[index] = result
        if batch.pending == 0:
            if batch.notify == "all":
                self._ready.append((batch_id, batch.ordered_results()))
            self._batches.pop(batch_id)
        if self._ready:
            self._available.set()

    @staticmethod
    def _error(call: ToolCall, content: str) -> ToolMessage:
        return ToolMessage(
            id=uuid4().hex,
            name=call["name"],
            tool_call_id=call["id"] or "",
            content=content,
            status="error",
        )

    def _take_messages(self) -> list[BaseMessage]:
        messages: list[BaseMessage] = []
        for batch_id, results in self._ready:
            # Providers require each tool result to follow a matching assistant call.
            messages.append(
                AIMessage(
                    id=uuid4().hex,
                    content=[],
                    tool_calls=[call for call, _ in results],
                    additional_kwargs={ASYNC_TOOL_BATCH_ID: batch_id},
                )
            )
            messages.extend(message for _, message in results)
        self._ready.clear()
        self._available.clear()
        return messages

    async def next_messages(self) -> list[BaseMessage]:
        await self._available.wait()
        return self._take_messages()

    async def close(self) -> list[BaseMessage]:
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        return self._take_messages()
