from sqlalchemy.orm import Session

from db.models import ResumeExtractionORM


class ResumeExtractionRepository:
    """Repository for tb_resume_extraction persistence."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_resume_id(self, resume_id: int) -> ResumeExtractionORM | None:
        return self._session.get(ResumeExtractionORM, resume_id)

    def upsert(self, extraction: ResumeExtractionORM) -> ResumeExtractionORM:
        existing = self.get_by_resume_id(extraction.resume_id)
        if existing is None:
            self._session.add(extraction)
            self._session.flush()
            self._session.refresh(extraction)
            return extraction

        existing.status = extraction.status
        existing.raw_text = extraction.raw_text
        existing.sections = extraction.sections
        existing.summary = extraction.summary
        existing.error_message = extraction.error_message
        existing.model_selection_id = extraction.model_selection_id
        existing.completed_at = extraction.completed_at
        self._session.flush()
        self._session.refresh(existing)
        return existing

    def delete_by_resume_id(self, resume_id: int) -> bool:
        existing = self.get_by_resume_id(resume_id)
        if existing is None:
            return False

        self._session.delete(existing)
        self._session.flush()
        return True

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
