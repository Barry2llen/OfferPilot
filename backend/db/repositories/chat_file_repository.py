from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import ChatFileORM, ChatThreadFileORM


class ChatFileRepository:
    """Repository for tb_chat_file persistence and listing."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, record: ChatFileORM) -> ChatFileORM:
        self._session.add(record)
        self._session.flush()
        self._session.refresh(record)
        return record

    def get_by_id(self, file_id: str) -> ChatFileORM | None:
        return self._session.get(ChatFileORM, file_id)

    def list_all_with_reference_count(self) -> list[tuple[ChatFileORM, int]]:
        statement = (
            select(ChatFileORM, func.count(ChatThreadFileORM.file_id))
            .outerjoin(ChatThreadFileORM, ChatThreadFileORM.file_id == ChatFileORM.id)
            .group_by(ChatFileORM.id)
            .order_by(ChatFileORM.created_at.desc(), ChatFileORM.id.desc())
        )
        return [
            (record, int(reference_count))
            for record, reference_count in self._session.execute(statement).all()
        ]

    def get_with_reference_count(self, file_id: str) -> tuple[ChatFileORM, int] | None:
        statement = (
            select(ChatFileORM, func.count(ChatThreadFileORM.file_id))
            .outerjoin(ChatThreadFileORM, ChatThreadFileORM.file_id == ChatFileORM.id)
            .where(ChatFileORM.id == file_id)
            .group_by(ChatFileORM.id)
        )
        row = self._session.execute(statement).first()
        if row is None:
            return None
        record, reference_count = row
        return record, int(reference_count)

    def delete(self, file_id: str) -> bool:
        record = self._session.get(ChatFileORM, file_id)
        if record is None:
            return False

        self._session.delete(record)
        self._session.flush()
        return True
