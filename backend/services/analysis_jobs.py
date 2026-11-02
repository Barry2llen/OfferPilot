"""Task ownership, cancellation and observation for analysis workflows."""

from __future__ import annotations

import asyncio
from collections import OrderedDict, deque
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from contextvars import Context
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from db.engine.manager import DatabaseManager
from schemas.config import Config
from services.analysis_job_events import AnalysisEventHub, AnalysisJobEvent
from utils.i18n import DEFAULT_LOCALE, Locale, localize_error
from utils.logger import logger


async def run_owned_io[T](operation: Callable[[], T]) -> tuple[T, bool]:
    """Finish a short file/DB operation before its owner handles cancellation."""
    task = asyncio.create_task(asyncio.to_thread(operation))
    interrupted = False
    while True:
        try:
            return await asyncio.shield(task), interrupted
        except asyncio.CancelledError:
            if task.cancelled():
                raise
            interrupted = True


@dataclass(slots=True)
class AnalysisJob:
    job_id: str
    resource_id: int
    selection_id: int
    locale: Locale
    history: deque[AnalysisJobEvent] = field(default_factory=lambda: deque(maxlen=256))
    subscribers: set[asyncio.Queue[AnalysisJobEvent]] = field(default_factory=set)
    done: bool = False
    sequence: int = 0
    task: asyncio.Task[None] | None = None
    cancel_detail: str = "Analysis was cancelled."


class AnalysisJobManager:
    resource_type: str
    record_key: str

    def __init__(
        self,
        *,
        config: Config,
        database: DatabaseManager,
        event_hub: AnalysisEventHub | None = None,
    ) -> None:
        self._config = config
        self._database = database
        self._event_hub = event_hub
        self._jobs: dict[int, AnalysisJob] = {}
        self._by_id: OrderedDict[str, AnalysisJob] = OrderedDict()
        self._lock = asyncio.Lock()
        self._admissions: dict[int, asyncio.Lock] = {}
        self._closing = False

    def admission(self, resource_id: int) -> asyncio.Lock:
        return self._admissions.setdefault(resource_id, asyncio.Lock())

    def active_job(self, resource_id: int) -> AnalysisJob | None:
        job = self._jobs.get(resource_id)
        return job if job is not None and not job.done else None

    def outcome(self, resource_id: int, job_id: str) -> AnalysisJobEvent | None:
        job = self._by_id.get(job_id)
        if job and job.resource_id == resource_id and job.done and job.history:
            return job.history[-1]
        return None

    async def _start(
        self,
        *,
        resource_id: int,
        selection_id: int,
        initial_event: AnalysisJobEvent,
        locale: Locale,
        workflow: Callable[[AnalysisJob], Awaitable[Any]],
    ) -> str:
        async with self._lock:
            if self._closing:
                raise RuntimeError("Analysis service is shutting down.")
            previous = self.active_job(resource_id)
            if previous:
                # A replacement has already saved its processing row. Do not overwrite it.
                self._emit(
                    previous,
                    "error",
                    {"detail": "Analysis was superseded by a newer job."},
                    done=True,
                )
                if previous.task:
                    previous.task.cancel()
            job = AnalysisJob(uuid4().hex, resource_id, selection_id, locale)
            self._jobs[resource_id] = job
            self._by_id[job.job_id] = job
            self._emit(job, initial_event.event, initial_event.data)
            # No chat callbacks, model tokens or user-input ports may escape the job.
            job.task = asyncio.create_task(
                self._execute(job, workflow), context=Context()
            )
            for old_id, old in list(self._by_id.items()):
                if len(self._by_id) <= 256:
                    break
                if old.done and (old.task is None or old.task.done()):
                    del self._by_id[old_id]
                    if self._jobs.get(old.resource_id) is old:
                        del self._jobs[old.resource_id]
        return job.job_id

    def _emit(
        self, job: AnalysisJob, event: str, data: dict[str, Any], *, done: bool = False
    ) -> None:
        if job.done:
            return
        job.sequence += 1
        payload = {
            **data,
            "resource_type": self.resource_type,
            "resource_id": job.resource_id,
            "job_id": job.job_id,
            "event_id": job.sequence,
            "status": "parsed"
            if event == "final"
            else "failed"
            if event == "error"
            else "processing",
        }
        payload["resume_id" if self.resource_type == "resume" else "analysis_id"] = (
            job.resource_id
        )
        item = AnalysisJobEvent(event, payload)
        job.history.append(item)
        job.done = done
        if self._event_hub:
            self._event_hub.publish_nowait(item)
        for queue in tuple(job.subscribers):
            if queue.full():
                # Observation may skip old updates, but must still receive the terminal.
                queue.get_nowait()
            queue.put_nowait(item)
            if done:
                job.subscribers.discard(queue)

    async def progress(self, job: AnalysisJob, event: Mapping[str, Any]) -> None:
        name, data = event.get("name"), event.get("data") or {}
        async with self._lock:
            if self._jobs.get(job.resource_id) is not job or job.done:
                return
            if name == "on_progress_update":
                self._emit(
                    job,
                    "progress",
                    {
                        "progress": data.get("progress", 0),
                        "message": data.get("message"),
                        "additional_data": data.get("additional_data") or {},
                    },
                )
            elif name == "on_model_call_error":
                self._emit(
                    job,
                    "model_error",
                    {
                        "attempt": data.get("attempt"),
                        "max_attempts": data.get("max_attempts"),
                        "detail": data.get("error"),
                        "additional_data": data.get("additional_data") or {},
                    },
                )

    async def _execute(
        self, job: AnalysisJob, workflow: Callable[[AnalysisJob], Awaitable[Any]]
    ) -> None:
        try:
            result = await workflow(job)
            async with self._lock:
                if self._jobs.get(job.resource_id) is job and not job.done:
                    detail, interrupted = await run_owned_io(
                        lambda: self.complete(job, result)
                    )
                    self._emit(job, "final", {self.record_key: detail}, done=True)
                    if interrupted:
                        raise asyncio.CancelledError
        except asyncio.CancelledError:
            await self._fail(job, job.cancel_detail)
            raise
        except Exception as error:
            await self._fail(job, str(error), error=error)

    async def _fail(
        self, job: AnalysisJob, detail: str, *, error: Exception | None = None
    ) -> None:
        async with self._lock:
            if self._jobs.get(job.resource_id) is not job or job.done:
                return
            try:
                await run_owned_io(lambda: self.fail(job, detail))
            except Exception:
                logger.exception(
                    "Could not persist analysis failure for {}:{}",
                    self.resource_type,
                    job.resource_id,
                )
            self._emit(
                job,
                "error",
                {
                    "detail": localize_error(error, "en-US") if error else detail,
                    "parse_status"
                    if self.resource_type == "resume"
                    else "status": "failed",
                },
                done=True,
            )

    def complete(self, job: AnalysisJob, result: Any) -> Any:
        raise NotImplementedError

    async def failed_start(
        self,
        resource_id: int,
        selection_id: int,
        initial: AnalysisJobEvent,
        detail: str,
        locale: Locale,
    ) -> str:
        active = self.active_job(resource_id)
        if active:
            await self.cancel(resource_id, active.job_id, reason=detail)
            return active.job_id
        job = AnalysisJob(uuid4().hex, resource_id, selection_id, locale)
        async with self._lock:
            self._jobs[resource_id] = job
            self._by_id[job.job_id] = job
            self._emit(job, initial.event, initial.data)
        await self._fail(job, detail)
        return job.job_id

    def fail(self, job: AnalysisJob, detail: str) -> None:
        raise NotImplementedError

    async def events(
        self, resource_id: int, job_id: str
    ) -> AsyncGenerator[AnalysisJobEvent, None]:
        queue: asyncio.Queue[AnalysisJobEvent] = asyncio.Queue(128)
        async with self._lock:
            job = self._by_id.get(job_id)
            if job is None or job.resource_id != resource_id:
                return
            history = list(job.history)
            if not job.done:
                job.subscribers.add(queue)
        try:
            for event in history:
                yield event
                if event.event in {"final", "error"}:
                    return
            while not job.done or not queue.empty():
                event = await queue.get()
                yield event
                if event.event in {"final", "error"}:
                    return
            if job.done and job.history and job.history[-1] not in history:
                yield job.history[-1]
        finally:
            job.subscribers.discard(queue)

    async def stream(self, resource_id: int, job_id: str) -> AsyncGenerator[str, None]:
        job = self._by_id.get(job_id)
        async for event in self.events(resource_id, job_id):
            yield event.to_sse(job.locale if job else DEFAULT_LOCALE)

    async def cancel(
        self, resource_id: int, job_id: str, *, reason: str = "Analysis was cancelled."
    ) -> None:
        job = self._by_id.get(job_id)
        if job is None or job.resource_id != resource_id or job.done:
            return
        job.cancel_detail = reason
        if job.task:
            job.task.cancel()
            await asyncio.gather(job.task, return_exceptions=True)
        # A task cancelled before its first instruction still needs a persisted terminal.
        await self._fail(job, reason)

    async def shutdown(self) -> None:
        self._closing = True
        await asyncio.gather(
            *(
                self.cancel(
                    job.resource_id,
                    job.job_id,
                    reason="Backend stopped; analysis was interrupted.",
                )
                for job in list(self._jobs.values())
                if not job.done
            )
        )
        await asyncio.gather(
            *(job.task for job in self._by_id.values() if job.task),
            return_exceptions=True,
        )
