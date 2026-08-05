from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import JobDescriptionAnalysisORM


class JobDescriptionAnalysisRepository:
    """Repository for tb_job_description_analysis persistence."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, analysis: JobDescriptionAnalysisORM) -> JobDescriptionAnalysisORM:
        self._session.add(analysis)
        self._session.flush()
        self._session.refresh(analysis)
        return analysis

    def list_all(self) -> list[JobDescriptionAnalysisORM]:
        statement = select(JobDescriptionAnalysisORM).order_by(
            JobDescriptionAnalysisORM.created_at.desc(),
            JobDescriptionAnalysisORM.id.desc(),
        )
        return self._session.scalars(statement).all()

    def get_by_id(self, analysis_id: int) -> JobDescriptionAnalysisORM | None:
        return self._session.get(JobDescriptionAnalysisORM, analysis_id)

    def update(self, analysis: JobDescriptionAnalysisORM) -> JobDescriptionAnalysisORM:
        self._session.flush()
        self._session.refresh(analysis)
        return analysis

    def delete(self, analysis_id: int) -> bool:
        analysis = self._session.get(JobDescriptionAnalysisORM, analysis_id)
        if analysis is None:
            return False

        self._session.delete(analysis)
        self._session.flush()
        return True

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
