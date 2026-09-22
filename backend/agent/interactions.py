"""Process-local interaction port. No execution objects enter graph state."""

import asyncio
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from uuid import uuid4

from langchain_core.messages import BaseMessage

from exceptions import ModelCallExecutionError
from schemas.model_selection import ModelSelection
from utils.i18n import Locale, public_run_error


class InteractionError(ValueError):
    def __init__(self, detail: str, status_code: int = 409) -> None:
        super().__init__(detail)
        self.status_code = status_code


@dataclass
class PendingInput:
    data: dict[str, Any]
    future: asyncio.Future[dict[str, Any]]
    answer: dict[str, Any] | None = None
    cancelled: bool = False


class InteractionBroker:
    def __init__(
        self,
        publish: Callable[..., Awaitable[None]],
        *,
        limit: int = 32,
        timeout: float | None = None,
    ) -> None:
        self.publish = publish
        self.limit = limit
        self.timeout = timeout
        self.items: dict[tuple[str, str], PendingInput] = {}
        self.closed: set[str] = set()

    def list_pending(self, run_id: str) -> list[dict[str, Any]]:
        return [
            item.data
            for (rid, _), item in self.items.items()
            if rid == run_id and not item.future.done()
        ]

    async def ask(
        self, context: "InteractionContext", request: Mapping[str, Any]
    ) -> dict[str, Any]:
        if context.run_id in self.closed:
            raise InteractionError("This run is no longer active.", 410)
        if not context.interactive:
            raise ModelCallExecutionError(
                "User input is required. Use the interactive chat endpoint."
            )
        if len(self.list_pending(context.run_id)) >= self.limit:
            raise ModelCallExecutionError("Too many pending input requests.")
        request_id = uuid4().hex
        data = {
            **request,
            "type": request.get("type") or "error",
            "request_id": request_id,
            "run_id": context.run_id,
            "thread_id": context.thread_id,
            "tool_call_id": context.tool_call_id,
            "source": context.source,
        }
        item = PendingInput(data, asyncio.get_running_loop().create_future())
        self.items[context.run_id, request_id] = item
        try:
            await self.publish(context.run_id, "input_required", data)
            async with asyncio.timeout(self.timeout):
                return await item.future
        except BaseException:
            item.cancelled = True
            item.future.cancel()
            raise

    async def submit(
        self, run_id: str, request_id: str, answer: dict[str, Any]
    ) -> None:
        item = self.items.get((run_id, request_id))
        if item is None or item.cancelled:
            raise InteractionError("This input request is no longer available.", 410)
        if item.data.get("type") == "query":
            if set(answer) - {"choice", "note"} or answer.get("choice") not in {
                "firstChoice",
                "secondChoice",
                "thirdChoice",
                "other",
            }:
                raise InteractionError("Invalid query answer.", 422)
            note = answer.get("note")
            if note is not None and not isinstance(note, str):
                raise InteractionError("Invalid query note.", 422)
            answer = {"choice": answer["choice"], "note": (note or "").strip() or None}
        elif answer != {"type": "retry"}:
            raise InteractionError("Only retry is accepted for this request.", 422)
        # No awaits between the state check and transition: atomic on our event loop.
        if item.answer is not None:
            if item.answer == answer:
                return
            raise InteractionError("A different answer was already submitted.")
        if run_id in self.closed:
            raise InteractionError("This input request is no longer available.", 410)
        if item.future.done():
            raise InteractionError("This input request has expired.", 410)
        item.answer = answer
        item.future.set_result(answer)
        await self.publish(run_id, "input_resolved", {**item.data, "answer": answer})

    def cancel_run(self, run_id: str) -> None:
        self.closed.add(run_id)
        for (rid, _), item in self.items.items():
            if rid == run_id and not item.future.done():
                item.cancelled = True
                item.future.cancel()

    def forget(self, run_id: str) -> None:
        self.items = {
            key: value for key, value in self.items.items() if key[0] != run_id
        }
        self.closed.discard(run_id)


@dataclass
class InteractionContext:
    broker: InteractionBroker
    run_id: str
    thread_id: str
    interactive: bool = True
    tool_call_id: str | None = None
    source: str = "supervisor"
    messages: list[BaseMessage] = field(default_factory=list)
    resolve_model: Callable[[], Awaitable[ModelSelection]] | None = None
    locale: Locale = "zh-CN"

    async def ask(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if request.get("type") == "error" and request.get("message"):
            request = {
                **request,
                "message": public_run_error(request["message"], self.locale),
            }
        return await self.broker.ask(self, request)


# Explicitly bound by the run owner, inherited by LangChain's child workflow tasks.
# Unlike graph/config state, this scope is never serialized by a checkpointer.
interaction_context: ContextVar[InteractionContext | None] = ContextVar(
    "offerpilot_interaction_context", default=None
)


async def ask_user(request: Mapping[str, Any]) -> dict[str, Any]:
    context = interaction_context.get()
    if context is None:
        raise ModelCallExecutionError(request.get("message", "User input is required."))
    return await context.ask(request)
