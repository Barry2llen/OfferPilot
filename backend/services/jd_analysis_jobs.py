from typing import Any

from agent.workflows.jd_analyzer import JdAnalysisWorkflow
from db.repositories import JobDescriptionAnalysisRepository
from services.analysis_job_events import AnalysisJobEvent
from services.analysis_jobs import AnalysisJob, AnalysisJobManager
from services.job_description_analysis_service import JobDescriptionAnalysisService
from utils.i18n import DEFAULT_LOCALE, Locale


class JdAnalysisJobManager(AnalysisJobManager):
    resource_type = "job_description"
    record_key = "job_description"

    async def start(
        self,
        *,
        analysis_id: int,
        selection_id: int,
        selection: Any,
        jd_text: str | None,
        source_url: str | None,
        images: list[str],
        initial_event: AnalysisJobEvent,
        locale: Locale = DEFAULT_LOCALE,
    ) -> str:
        async def workflow(job: AnalysisJob):
            return await JdAnalysisWorkflow(config=self._config).astream_events(
                selection,
                jd_text=jd_text,
                source_url=source_url,
                images=images,
                handlers={"on_custom_event": lambda event: self.progress(job, event)},
            )

        return await self._start(
            resource_id=analysis_id,
            selection_id=selection_id,
            locale=locale,
            initial_event=initial_event,
            workflow=workflow,
        )

    def complete(self, job: AnalysisJob, result: Any):
        with self._database.get_session_factory()() as session:
            return JobDescriptionAnalysisService(
                JobDescriptionAnalysisRepository(session),
            ).complete_analysis(job.resource_id, job.selection_id, result)

    def fail(self, job: AnalysisJob, detail: str) -> None:
        with self._database.get_session_factory()() as session:
            JobDescriptionAnalysisService(
                JobDescriptionAnalysisRepository(session),
            ).fail_analysis(job.resource_id, job.selection_id, detail)
