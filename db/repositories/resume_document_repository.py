from sqlalchemy.orm import Session

from db.models import ResumeDocumentORM


class ResumeDocumentRepository:
    """Repository for tb_resume persistence."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, document: ResumeDocumentORM) -> ResumeDocumentORM:
        self._session.add(document)
        self._session.flush()
        self._session.refresh(document)
        return document

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
