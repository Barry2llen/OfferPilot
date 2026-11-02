"""Structured analysis events shared by job observers and legacy SSE APIs."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from utils.i18n import (
    DEFAULT_LOCALE,
    MESSAGES,
    Locale,
    localize_error,
    localize_model_retry_detail,
    localize_progress_message,
)
from utils.stream import render_sse_event, to_jsonable


def _localized_error(detail: str, locale: Locale) -> str:
    for translations in MESSAGES.values():
        if detail in translations.values():
            return translations[locale]
    return localize_error(detail, locale)


@dataclass(slots=True, frozen=True)
class AnalysisJobEvent:
    event: str
    data: dict[str, Any]

    def localized(self, locale: Locale = DEFAULT_LOCALE) -> dict[str, Any]:
        data = dict(to_jsonable(self.data))
        if isinstance(data.get("message"), str):
            data["message"] = localize_progress_message(data["message"], locale)
        if self.event == "model_error":
            data["detail"] = localize_model_retry_detail(
                data.get("detail"),
                locale,
                attempt=data.get("attempt"),
                max_attempts=data.get("max_attempts"),
            )
        elif self.event == "error" and data.get("detail"):
            data["detail"] = _localized_error(data["detail"], locale)
        if data.get("error"):
            data["error"] = _localized_error(data["error"], locale)
        if isinstance(data.get("model_error"), dict):
            retry = data["model_error"]
            data["model_error"] = localize_model_retry_detail(
                retry.get("detail"),
                locale,
                attempt=retry.get("attempt"),
                max_attempts=retry.get("max_attempts"),
            )
        return data

    def to_sse(self, locale: Locale = DEFAULT_LOCALE) -> str:
        return render_sse_event(self.event, self.localized(locale))


class AnalysisEventHub:
    """Bounded current projection; every subscription starts with a snapshot."""

    def __init__(
        self, *, subscriber_events: int = 128, retained_tasks: int = 256
    ) -> None:
        self._subscribers: set[asyncio.Queue[AnalysisJobEvent | None]] = set()
        self._tasks: OrderedDict[tuple[str, int], dict[str, Any]] = OrderedDict()
        self._sequence = 0
        self._subscriber_events = subscriber_events
        self._retained_tasks = retained_tasks
        self._closed = False

    def publish_nowait(self, event: AnalysisJobEvent) -> None:
        if self._closed:
            return
        self._sequence += 1
        data = {**to_jsonable(event.data), "event_id": self._sequence}
        event = AnalysisJobEvent(event.event, data)
        key = (data["resource_type"], data["resource_id"])
        old = self._tasks.get(key, {})
        current = old if old.get("job_id") == data.get("job_id") else {}
        task = {
            "resource_type": key[0],
            "resource_id": key[1],
            "job_id": data["job_id"],
            "event_id": self._sequence,
            "status": data.get("status", current.get("status", "processing")),
            "progress": current.get("progress", 0),
            "message": current.get("message"),
            "model_error": current.get("model_error"),
            "error": None,
        }
        if event.event == "progress":
            task.update(
                progress=data.get("progress", 0),
                message=data.get("message"),
                model_error=None,
            )
        elif event.event == "model_error":
            task["model_error"] = {
                name: data.get(name) for name in ("detail", "attempt", "max_attempts")
            }
        elif event.event in {"final", "error"}:
            task.update(message=None, model_error=None, error=data.get("detail"))
            if event.event == "final":
                task["progress"] = 1
        self._tasks[key] = task
        self._tasks.move_to_end(key)
        # Active tasks stay visible; old terminals can always be read via REST.
        for stale_key in list(self._tasks):
            if len(self._tasks) <= self._retained_tasks:
                break
            if self._tasks[stale_key]["status"] != "processing":
                del self._tasks[stale_key]
        for queue in tuple(self._subscribers):
            if queue.full():
                self._subscribers.discard(queue)
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(None)
            else:
                queue.put_nowait(event)

    async def publish(self, event: AnalysisJobEvent) -> None:
        self.publish_nowait(event)

    async def stream(
        self,
        *,
        heartbeat_seconds: float = 15,
        locale: Locale = DEFAULT_LOCALE,
    ) -> AsyncGenerator[str, None]:
        queue: asyncio.Queue[AnalysisJobEvent | None] = asyncio.Queue(
            self._subscriber_events
        )
        if self._closed:
            return
        # Capture and subscribe without yielding to avoid a snapshot/live gap.
        self._subscribers.add(queue)
        snapshot = {
            "event_id": self._sequence,
            "tasks": [
                AnalysisJobEvent("snapshot", task).localized(locale)
                for task in self._tasks.values()
            ],
        }
        try:
            yield render_sse_event("snapshot", snapshot)
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), heartbeat_seconds)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if event is None:
                    break
                yield event.to_sse(locale)
        finally:
            self._subscribers.discard(queue)

    async def close(self) -> None:
        self._closed = True
        for queue in tuple(self._subscribers):
            while not queue.empty():
                queue.get_nowait()
            queue.put_nowait(None)
        self._subscribers.clear()
