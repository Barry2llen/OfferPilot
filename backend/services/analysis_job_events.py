from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from utils.stream import render_sse_event


@dataclass(slots=True, frozen=True)
class AnalysisJobEvent:
    """A structured event emitted by a resume or JD analysis job."""

    event: str
    data: dict[str, Any]

    def to_sse(self) -> str:
        return render_sse_event(self.event, self.data)


class AnalysisEventHub:
    """Broadcast analysis job events to long-lived frontend subscriptions."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[AnalysisJobEvent | None]] = set()
        self._lock = asyncio.Lock()

    async def publish(self, event: AnalysisJobEvent) -> None:
        async with self._lock:
            subscribers = list(self._subscribers)

        for queue in subscribers:
            queue.put_nowait(event)

    def publish_nowait(self, event: AnalysisJobEvent) -> None:
        """Publish from a manager critical section without yielding first."""

        for queue in tuple(self._subscribers):
            queue.put_nowait(event)

    async def stream(
        self, *, heartbeat_seconds: float | None = None
    ) -> AsyncGenerator[str, None]:
        queue: asyncio.Queue[AnalysisJobEvent | None] = asyncio.Queue()
        async with self._lock:
            self._subscribers.add(queue)

        try:
            while True:
                if heartbeat_seconds is None:
                    event = await queue.get()
                else:
                    try:
                        event = await asyncio.wait_for(
                            queue.get(), timeout=heartbeat_seconds
                        )
                    except TimeoutError:
                        yield ": keep-alive\n\n"
                        continue
                if event is None:
                    break
                yield event.to_sse()
        finally:
            async with self._lock:
                self._subscribers.discard(queue)

    async def close(self) -> None:
        async with self._lock:
            subscribers = list(self._subscribers)
            self._subscribers.clear()

        for queue in subscribers:
            queue.put_nowait(None)


__all__ = ["AnalysisEventHub", "AnalysisJobEvent"]
