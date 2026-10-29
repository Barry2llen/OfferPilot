"""Prepare and start persisted analyses for Supervisor tools."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from db.engine.manager import DatabaseManager
from db.repositories import (
    ChatFileRepository,
    ChatThreadFileRepository,
    JobDescriptionAnalysisRepository,
    ResumeDocumentRepository,
    ResumeExtractionRepository,
)
from schemas.config import Config
from schemas.job_description_analysis import JobDescriptionAnalysisDetail
from schemas.model_selection import ModelSelection
from schemas.resume_document import ResumeDetail, ResumeDocument
from services.analysis_job_events import AnalysisJobEvent
from services.analysis_jobs import AnalysisJobManager, run_owned_io
from services.chat_file_service import ChatFileService, UploadedChatFile
from services.jd_analysis_jobs import JdAnalysisJobManager
from services.job_description_analysis_service import JobDescriptionAnalysisService
from services.resume_extraction_jobs import ResumeExtractionJobManager
from services.resume_service import ResumeService, UploadedResumeFile
from utils.i18n import Locale


@dataclass(frozen=True)
class AnalysisHandle:
    resource_type: str
    resource_id: int
    job_id: str
    manager: AnalysisJobManager

    def metadata(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "job_id": self.job_id,
        }


class AnalysisBusyError(ValueError):
    def __init__(self, handle: AnalysisHandle):
        super().__init__("Resume analysis is already processing.")
        self.handle = handle


class AnalysisStartError(ValueError):
    def __init__(self, handle: AnalysisHandle, cause: BaseException):
        super().__init__(str(cause))
        self.handle = handle


class AnalysisStartCancelled(asyncio.CancelledError):
    def __init__(self, handle: AnalysisHandle):
        super().__init__("Analysis was cancelled.")
        self.handle = handle


@dataclass(frozen=True)
class AnalysisService:
    config: Config
    database: DatabaseManager
    resume_jobs: ResumeExtractionJobManager
    jd_jobs: JdAnalysisJobManager

    def _resumes(self, session: Session) -> ResumeService:
        return ResumeService(
            ResumeDocumentRepository(session),
            self.config.resume_upload_dir,
            ResumeExtractionRepository(session),
        )

    def _files(self, session: Session) -> ChatFileService:
        return ChatFileService(
            ChatFileRepository(session),
            ChatThreadFileRepository(session),
            self.config.chat_file_upload_dir,
        )

    async def start_resume(
        self,
        *,
        selection: ModelSelection,
        resume_id: int | None,
        file_id: str | None,
        locale: Locale,
    ) -> AnalysisHandle:
        normalized = (file_id or "").strip() or None
        if (resume_id is None) == (normalized is None):
            raise ValueError("Provide exactly one of resume_id or file_id.")
        if resume_id is not None and resume_id <= 0:
            raise ValueError("Resume ID must be positive.")
        selection_id = self._selection_id(selection)
        async with self.resume_jobs.admission(resume_id or 0):
            active = (
                self.resume_jobs.active_job(resume_id)
                if resume_id is not None
                else None
            )
            if active:
                raise AnalysisBusyError(
                    AnalysisHandle(
                        "resume", active.resource_id, active.job_id, self.resume_jobs
                    )
                )
            processing, interrupted = await run_owned_io(
                lambda: self._prepare_resume(selection_id, resume_id, normalized)
            )
            return await self._launch_resume(processing, selection, locale, interrupted)

    def _prepare_resume(
        self, selection_id: int, resume_id: int | None, file_id: str | None
    ) -> ResumeDetail:
        with self.database.get_session_factory()() as session:
            service = self._resumes(session)
            if file_id is not None:
                stored = self._files(session).get_file_raw(file_id)
                detail = service.create_from_file(
                    UploadedResumeFile(
                        filename=stored.filename,
                        content_type=stored.media_type,
                        content=Path(stored.path).read_bytes(),
                    )
                )
            else:
                assert resume_id is not None
                detail = service.get_resume(resume_id)
                if detail.parse_status == "processing":
                    raise AnalysisBusyError(
                        AnalysisHandle("resume", resume_id, "", self.resume_jobs)
                    )
                service.get_resume_file(resume_id)
            return service.begin_extraction(detail.id, selection_id)

    async def start_resume_file(
        self,
        *,
        selection: ModelSelection,
        uploaded_file: UploadedResumeFile,
        resume_id: int | None,
        locale: Locale,
    ) -> AnalysisHandle:
        selection_id = self._selection_id(selection)
        async with self.resume_jobs.admission(resume_id or 0):
            if resume_id is not None:
                _, interrupted = await run_owned_io(
                    lambda: self._validate_replacement(resume_id, uploaded_file)
                )
                if interrupted:
                    raise asyncio.CancelledError
                active = self.resume_jobs.active_job(resume_id)
                if active:
                    await self.resume_jobs.cancel(
                        resume_id,
                        active.job_id,
                        reason="Analysis was superseded by a newer job.",
                    )
            processing, interrupted = await run_owned_io(
                lambda: self._prepare_resume_file(
                    selection_id, uploaded_file, resume_id
                )
            )
            return await self._launch_resume(processing, selection, locale, interrupted)

    def _validate_replacement(
        self, resume_id: int, uploaded: UploadedResumeFile
    ) -> None:
        with self.database.get_session_factory()() as session:
            service = self._resumes(session)
            service.get_resume(resume_id)
            service.validate_upload(uploaded)

    def _prepare_resume_file(
        self, selection_id: int, uploaded: UploadedResumeFile, resume_id: int | None
    ) -> ResumeDetail:
        with self.database.get_session_factory()() as session:
            service = self._resumes(session)
            detail = (
                service.create_from_file(uploaded)
                if resume_id is None
                else service.replace_resume_file(resume_id, uploaded)
            )
            return service.begin_extraction(detail.id, selection_id)

    async def _launch_resume(
        self,
        processing: ResumeDetail,
        selection: ModelSelection,
        locale: Locale,
        interrupted: bool,
    ) -> AnalysisHandle:
        initial = AnalysisJobEvent("resume", {"resume": processing})
        selection_id = self._selection_id(selection)
        try:
            if interrupted:
                raise asyncio.CancelledError
            job_id = await self.resume_jobs.start(
                resume_id=processing.id,
                selection_id=selection_id,
                selection=selection,
                resume_document=ResumeDocument.model_validate(processing.model_dump()),
                initial_event=initial,
                locale=locale,
            )
        except (Exception, asyncio.CancelledError) as error:
            handle = await self._failed_start(
                self.resume_jobs, processing.id, selection_id, initial, error, locale
            )
            if isinstance(error, asyncio.CancelledError):
                raise AnalysisStartCancelled(handle) from error
            raise AnalysisStartError(handle, error) from error
        return AnalysisHandle("resume", processing.id, job_id, self.resume_jobs)

    async def start_job_description(
        self,
        *,
        selection: ModelSelection,
        jd_text: str | None,
        source_url: str | None,
        file_ids: list[str],
        locale: Locale,
        uploaded_files: list[UploadedChatFile] | None = None,
    ) -> AnalysisHandle:
        selection_id = self._selection_id(selection)
        text = (jd_text or "").strip() or None
        url = (source_url or "").strip() or None
        ids = list(dict.fromkeys(value.strip() for value in file_ids if value.strip()))
        prepared, interrupted = await run_owned_io(
            lambda: self._prepare_jd(selection_id, text, url, ids, uploaded_files or [])
        )
        detail, images = prepared
        initial = AnalysisJobEvent("job_description", {"job_description": detail})
        try:
            if interrupted:
                raise asyncio.CancelledError
            job_id = await self.jd_jobs.start(
                analysis_id=detail.id,
                selection_id=selection_id,
                selection=selection,
                jd_text=text,
                source_url=url,
                images=images,
                initial_event=initial,
                locale=locale,
            )
        except (Exception, asyncio.CancelledError) as error:
            handle = await self._failed_start(
                self.jd_jobs, detail.id, selection_id, initial, error, locale
            )
            if isinstance(error, asyncio.CancelledError):
                raise AnalysisStartCancelled(handle) from error
            raise AnalysisStartError(handle, error) from error
        return AnalysisHandle("job_description", detail.id, job_id, self.jd_jobs)

    def _prepare_jd(
        self,
        selection_id: int,
        text: str | None,
        url: str | None,
        file_ids: list[str],
        uploads: list[UploadedChatFile],
    ) -> tuple[JobDescriptionAnalysisDetail, list[str]]:
        paths: list[Path] = []
        with self.database.get_session_factory()() as session:
            try:
                service = JobDescriptionAnalysisService(
                    JobDescriptionAnalysisRepository(session)
                )
                files = self._files(session)
                stored = files.store_files(uploads)
                paths = stored.created_file_paths
                ids = [record.id for record in stored.records]
                images = [
                    service.image_record_to_data_url(record)
                    for record in stored.records
                ]
                for file_id in file_ids:
                    images.append(
                        service.stored_file_to_data_url(files.get_file_raw(file_id))
                    )
                    ids.append(file_id)
                service.validate_sources(
                    jd_text=text, source_url=url, image_file_ids=ids
                )
                detail = service.create_processing(
                    selection_id=selection_id, source_url=url, image_file_ids=ids
                )
                return detail, images
            except Exception:
                session.rollback()
                for path in paths:
                    path.unlink(missing_ok=True)
                raise

    async def _failed_start(
        self,
        manager: AnalysisJobManager,
        resource_id: int,
        selection_id: int,
        initial: AnalysisJobEvent,
        error: BaseException,
        locale: Locale,
    ) -> AnalysisHandle:
        job_id = await manager.failed_start(
            resource_id,
            selection_id,
            initial,
            str(error) or "Analysis was cancelled.",
            locale,
        )
        return AnalysisHandle(manager.resource_type, resource_id, job_id, manager)

    @staticmethod
    def _selection_id(selection: ModelSelection) -> int:
        if selection.id is None:
            raise ValueError("A model selection is required for analysis.")
        return selection.id

    def recover(self) -> None:
        with self.database.get_session_factory()() as session:
            ResumeExtractionRepository(session).recover_processing()
            JobDescriptionAnalysisRepository(session).recover_processing()
            session.commit()
