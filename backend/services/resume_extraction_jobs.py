from typing import Any

from agent.workflows.resume_extract import ResumeExtractWorkflow
from db.repositories import ResumeDocumentRepository, ResumeExtractionRepository
from schemas.resume_document import ResumeDocument
from services.analysis_job_events import AnalysisJobEvent
from services.analysis_jobs import AnalysisJob, AnalysisJobManager
from services.resume_service import ResumeService
from utils.i18n import DEFAULT_LOCALE, Locale


class ResumeExtractionJobManager(AnalysisJobManager):
    resource_type = "resume"
    record_key = "resume"

    async def start(
        self,
        *,
        resume_id: int,
        selection_id: int,
        selection: Any,
        resume_document: ResumeDocument,
        initial_event: AnalysisJobEvent,
        locale: Locale = DEFAULT_LOCALE,
    ) -> str:
        async def workflow(job: AnalysisJob):
            return await ResumeExtractWorkflow(config=self._config).astream_events(
                selection,
                resume_document,
                handlers={"on_custom_event": lambda event: self.progress(job, event)},
            )

        return await self._start(
            resource_id=resume_id,
            selection_id=selection_id,
            locale=locale,
            initial_event=initial_event,
            workflow=workflow,
        )

    def complete(self, job: AnalysisJob, result: Any):
        with self._database.get_session_factory()() as session:
            return ResumeService(
                ResumeDocumentRepository(session),
                self._config.resume_upload_dir,
                ResumeExtractionRepository(session),
            ).complete_extraction(job.resource_id, job.selection_id, result)

    def fail(self, job: AnalysisJob, detail: str) -> None:
        with self._database.get_session_factory()() as session:
            ResumeService(
                ResumeDocumentRepository(session),
                self._config.resume_upload_dir,
                ResumeExtractionRepository(session),
            ).fail_extraction(job.resource_id, job.selection_id, detail)
