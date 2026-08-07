from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import ChatThreadFileORM


class ChatThreadFileRepository:
    """Repository for tb_chat_thread_file associations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, record: ChatThreadFileORM) -> ChatThreadFileORM:
        self._session.add(record)
        self._session.flush()
        self._session.refresh(record)
        return record

    def get(self, thread_id: str, file_id: str) -> ChatThreadFileORM | None:
        statement = select(ChatThreadFileORM).where(
            ChatThreadFileORM.thread_id == thread_id,
            ChatThreadFileORM.file_id == file_id,
        )
        return self._session.scalar(statement)

    def list_by_thread(self, thread_id: str) -> list[ChatThreadFileORM]:
        statement = (
            select(ChatThreadFileORM)
            .where(ChatThreadFileORM.thread_id == thread_id)
            .order_by(
                ChatThreadFileORM.created_at.asc(), ChatThreadFileORM.file_id.asc()
            )
        )
        return self._session.scalars(statement).all()

    def delete_by_thread(self, thread_id: str) -> list[str]:
        rows = self.list_by_thread(thread_id)
        for row in rows:
            self._session.delete(row)
        self._session.flush()
        return [row.file_id for row in rows]

    def count_by_thread(self, thread_id: str) -> int:
        statement = (
            select(func.count())
            .select_from(ChatThreadFileORM)
            .where(ChatThreadFileORM.thread_id == thread_id)
        )
        return int(self._session.scalar(statement) or 0)

    def has_image_mode(self, thread_id: str) -> bool:
        statement = select(ChatThreadFileORM.file_id).where(
            ChatThreadFileORM.thread_id == thread_id,
            ChatThreadFileORM.injection_mode == "image",
        )
        return self._session.scalar(statement) is not None

    def count_references_for_file(self, file_id: str) -> int:
        statement = (
            select(func.count())
            .select_from(ChatThreadFileORM)
            .where(ChatThreadFileORM.file_id == file_id)
        )
        return int(self._session.scalar(statement) or 0)
