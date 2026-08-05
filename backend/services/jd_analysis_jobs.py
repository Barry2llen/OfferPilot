import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from agent.workflows.jd_analyzer import JdAnalysisWorkflow
from db.engine.manager import DatabaseManager
from db.repositories import JobDescriptionAnalysisRepository
from schemas.config import Config
from services.job_description_analysis_service import JobDescriptionAnalysisService
from utils.stream import render_sse_event
from utils.i18n import (
    DEFAULT_LOCALE,
    Locale,
    localize_error,
    localize_model_retry_detail,
    localize_progress_message,
)


@dataclass(slots=True)
class _JdAnalysisJob:
    job_id: str
    analysis_id: int
    locale: Locale = DEFAULT_LOCALE
    history: list[str] = field(default_factory=list)
    subscribers: set[asyncio.Queue[str | None]] = field(default_factory=set)
    done: bool = False
    task: asyncio.Task[None] | None = None


class JdAnalysisJobManager:
    """Run JD analysis independently of any single SSE connection."""

    def __init__(
        self,
        *,
        config: Config,
        database: DatabaseManager,
    ) -> None:
        self._config = config
        self._database = database
        self._jobs: dict[int, _JdAnalysisJob] = {}
        self._lock = asyncio.Lock()

    async def start(
        self,
        *,
        analysis_id: int,
        selection_id: int,
        selection: Any,
        jd_text: str | None,
        source_url: str | None,
        images: list[str],
        initial_event: str,
        locale: Locale = DEFAULT_LOCALE,
    ) -> str:
        job_id = uuid4().hex
        job = _JdAnalysisJob(
            job_id=job_id,
            analysis_id=analysis_id,
            locale=locale,
            history=[initial_event],
        )

        async with self._lock:
            self._jobs[analysis_id] = job
            job.task = asyncio.create_task(
                self._run(
                    job_id=job_id,
                    analysis_id=analysis_id,
                    selection_id=selection_id,
                    selection=selection,
                    jd_text=jd_text,
                    source_url=source_url,
                    images=images,
                    locale=locale,
                )
            )

        return job_id

    async def stream(self, analysis_id: int, job_id: str) -> AsyncGenerator[str, None]:
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        async with self._lock:
            job = self._jobs.get(analysis_id)
            if job is None or job.job_id != job_id:
                return
            for event in job.history:
                queue.put_nowait(event)
            if job.done:
                queue.put_nowait(None)
            else:
                job.subscribers.add(queue)

        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            async with self._lock:
                job = self._jobs.get(analysis_id)
                if job is not None and job.job_id == job_id:
                    job.subscribers.discard(queue)

    async def shutdown(self) -> None:
        async with self._lock:
            tasks = [
                job.task
                for job in self._jobs.values()
                if job.task is not None and not job.task.done()
            ]
            for task in tasks:
                task.cancel()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run(
        self,
        *,
        job_id: str,
        analysis_id: int,
        selection_id: int,
        selection: Any,
        jd_text: str | None,
        source_url: str | None,
        images: list[str],
        locale: Locale,
    ) -> None:
        workflow = JdAnalysisWorkflow(config=self._config)

        async def handle_custom_event(event: dict[str, Any]) -> None:
            name = str(event.get("name") or "")
            data = event.get("data") if isinstance(event.get("data"), dict) else {}

            if name == "on_progress_update":
                await self._publish(
                    analysis_id,
                    job_id,
                    "progress",
                    {
                        "analysis_id": analysis_id,
                        "progress": data.get("progress", 0),
                        "message": localize_progress_message(data.get("message"), locale),
                        "additional_data": data.get("additional_data") or {},
                    },
                )
                return

            if name == "on_model_call_error":
                await self._publish(
                    analysis_id,
                    job_id,
                    "model_error",
                    {
                        "analysis_id": analysis_id,
                        "attempt": data.get("attempt"),
                        "max_attempts": data.get("max_attempts"),
                        "detail": localize_model_retry_detail(
                            data.get("error"),
                            locale,
                            attempt=data.get("attempt") or 0,
                            max_attempts=data.get("max_attempts") or 0,
                        ),
                        "additional_data": data.get("additional_data") or {},
                    },
                )

        try:
            parsed_jd = await workflow.astream_events(
                selection,
                jd_text=jd_text,
                source_url=source_url,
                images=images,
                handlers={"on_custom_event": handle_custom_event},
            )
            if not await self._is_current(analysis_id, job_id):
                return
            with self._database.get_session_factory()() as session:
                service = JobDescriptionAnalysisService(
                    JobDescriptionAnalysisRepository(session)
                )
                final_detail = service.complete_analysis(
                    analysis_id,
                    selection_id,
                    parsed_jd,
                )
            await self._publish(
                analysis_id,
                job_id,
                "final",
                {"job_description": final_detail},
                done=True,
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if not await self._is_current(analysis_id, job_id):
                return
            detail = str(error)
            localized_detail = localize_error(error, locale)
            with self._database.get_session_factory()() as session:
                service = JobDescriptionAnalysisService(
                    JobDescriptionAnalysisRepository(session)
                )
                service.fail_analysis(analysis_id, selection_id, detail)
            await self._publish(
                analysis_id,
                job_id,
                "error",
                {
                    "analysis_id": analysis_id,
                    "detail": localized_detail,
                    "status": "failed",
                },
                done=True,
            )
        finally:
            await self._finish_if_current(analysis_id, job_id)

    async def _publish(
        self,
        analysis_id: int,
        job_id: str,
        event: str,
        data: dict[str, Any],
        *,
        done: bool = False,
    ) -> None:
        payload = render_sse_event(event, data)
        async with self._lock:
            job = self._jobs.get(analysis_id)
            if job is None or job.job_id != job_id:
                return
            job.history.append(payload)
            if done:
                job.done = True
            subscribers = list(job.subscribers)

        for queue in subscribers:
            await queue.put(payload)
            if done:
                await queue.put(None)

    async def _finish_if_current(self, analysis_id: int, job_id: str) -> None:
        async with self._lock:
            job = self._jobs.get(analysis_id)
            if job is None or job.job_id != job_id or job.done:
                return
            job.done = True
            subscribers = list(job.subscribers)

        for queue in subscribers:
            await queue.put(None)

    async def _is_current(self, analysis_id: int, job_id: str) -> bool:
        async with self._lock:
            job = self._jobs.get(analysis_id)
            return job is not None and job.job_id == job_id
