import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from agent.workflows.resume_extract import ResumeExtractWorkflow
from db.engine.manager import DatabaseManager
from db.repositories import ResumeDocumentRepository, ResumeExtractionRepository
from schemas.config import Config
from schemas.resume_document import ResumeDocument
from services.resume_service import ResumeService
from utils.stream import render_sse_event


@dataclass(slots=True)
class _ResumeExtractionJob:
    job_id: str
    resume_id: int
    history: list[str] = field(default_factory=list)
    subscribers: set[asyncio.Queue[str | None]] = field(default_factory=set)
    done: bool = False
    task: asyncio.Task[None] | None = None


class ResumeExtractionJobManager:
    """Run resume extraction independently of any single SSE connection."""

    def __init__(
        self,
        *,
        config: Config,
        database: DatabaseManager,
    ) -> None:
        self._config = config
        self._database = database
        self._jobs: dict[int, _ResumeExtractionJob] = {}
        self._lock = asyncio.Lock()

    async def start(
        self,
        *,
        resume_id: int,
        selection_id: int,
        selection: Any,
        resume_document: ResumeDocument,
        initial_event: str,
    ) -> str:
        job_id = uuid4().hex
        job = _ResumeExtractionJob(
            job_id=job_id,
            resume_id=resume_id,
            history=[initial_event],
        )

        async with self._lock:
            previous = self._jobs.get(resume_id)
            if previous and previous.task and not previous.task.done():
                previous.task.cancel()
                previous.done = True
                for queue in list(previous.subscribers):
                    queue.put_nowait(None)
            self._jobs[resume_id] = job
            job.task = asyncio.create_task(
                self._run(
                    job_id=job_id,
                    resume_id=resume_id,
                    selection_id=selection_id,
                    selection=selection,
                    resume_document=resume_document,
                )
            )

        return job_id

    async def stream(self, resume_id: int, job_id: str) -> AsyncGenerator[str, None]:
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        async with self._lock:
            job = self._jobs.get(resume_id)
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
                job = self._jobs.get(resume_id)
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
        resume_id: int,
        selection_id: int,
        selection: Any,
        resume_document: ResumeDocument,
    ) -> None:
        workflow = ResumeExtractWorkflow(config=self._config)

        async def handle_custom_event(event: dict[str, Any]) -> None:
            name = str(event.get("name") or "")
            data = event.get("data") if isinstance(event.get("data"), dict) else {}

            if name == "on_progress_update":
                await self._publish(
                    resume_id,
                    job_id,
                    "progress",
                    {
                        "resume_id": resume_id,
                        "progress": data.get("progress", 0),
                        "message": data.get("message"),
                        "additional_data": data.get("additional_data") or {},
                    },
                )
                return

            if name == "on_model_call_error":
                await self._publish(
                    resume_id,
                    job_id,
                    "model_error",
                    {
                        "resume_id": resume_id,
                        "attempt": data.get("attempt"),
                        "max_attempts": data.get("max_attempts"),
                        "detail": data.get("error"),
                        "additional_data": data.get("additional_data") or {},
                    },
                )

        try:
            parsed_resume = await workflow.astream_events(
                selection,
                resume_document,
                handlers={"on_custom_event": handle_custom_event},
            )
            if not await self._is_current(resume_id, job_id):
                return
            with self._database.get_session_factory()() as session:
                service = ResumeService(
                    repository=ResumeDocumentRepository(session),
                    extraction_repository=ResumeExtractionRepository(session),
                    upload_dir=self._config.resume_upload_dir,
                )
                final_detail = service.complete_extraction(
                    resume_id,
                    selection_id,
                    parsed_resume,
                )
            await self._publish(
                resume_id,
                job_id,
                "final",
                {"resume": final_detail},
                done=True,
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if not await self._is_current(resume_id, job_id):
                return
            detail = str(error)
            with self._database.get_session_factory()() as session:
                service = ResumeService(
                    repository=ResumeDocumentRepository(session),
                    extraction_repository=ResumeExtractionRepository(session),
                    upload_dir=self._config.resume_upload_dir,
                )
                service.fail_extraction(resume_id, selection_id, detail)
            await self._publish(
                resume_id,
                job_id,
                "error",
                {
                    "resume_id": resume_id,
                    "detail": detail,
                    "parse_status": "failed",
                },
                done=True,
            )
        finally:
            await self._finish_if_current(resume_id, job_id)

    async def _publish(
        self,
        resume_id: int,
        job_id: str,
        event: str,
        data: dict[str, Any],
        *,
        done: bool = False,
    ) -> None:
        payload = render_sse_event(event, data)
        async with self._lock:
            job = self._jobs.get(resume_id)
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

    async def _finish_if_current(self, resume_id: int, job_id: str) -> None:
        async with self._lock:
            job = self._jobs.get(resume_id)
            if job is None or job.job_id != job_id or job.done:
                return
            job.done = True
            subscribers = list(job.subscribers)

        for queue in subscribers:
            await queue.put(None)

    async def _is_current(self, resume_id: int, job_id: str) -> bool:
        async with self._lock:
            job = self._jobs.get(resume_id)
            return job is not None and job.job_id == job_id
