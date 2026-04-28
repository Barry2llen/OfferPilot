from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ResumeDocumentORM
from exceptions import ResumeNotFoundError


class ResumeDocumentRepository:
    """Repository for tb_resume persistence."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, document: ResumeDocumentORM) -> ResumeDocumentORM:
        self._session.add(document)
        self._session.flush()
        self._session.refresh(document)
        return document

    def list_all(self) -> list[ResumeDocumentORM]:
        statement = select(ResumeDocumentORM).order_by(
            ResumeDocumentORM.upload_time.desc(),
            ResumeDocumentORM.id.desc(),
        )
        return self._session.scalars(statement).all()

    def get_by_id(self, document_id: int) -> ResumeDocumentORM | None:
        return self._session.get(ResumeDocumentORM, document_id)

    def update(self, document: ResumeDocumentORM) -> ResumeDocumentORM:
        orm_document = self._session.get(ResumeDocumentORM, document.id)
        if orm_document is None:
            raise ResumeNotFoundError(f"Resume not found: {document.id}")

        orm_document.file_path = document.file_path
        orm_document.original_filename = document.original_filename
        orm_document.media_type = document.media_type
        self._session.flush()
        self._session.refresh(orm_document)
        return orm_document

    def delete(self, document_id: int) -> bool:
        orm_document = self._session.get(ResumeDocumentORM, document_id)
        if orm_document is None:
            return False

        self._session.delete(orm_document)
        self._session.flush()
        return True

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
