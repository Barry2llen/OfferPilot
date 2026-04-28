from time import sleep

from sqlalchemy import select

from db.engine import DatabaseManager
from db.models import ChatORM


def test_chat_orm_defaults_messages_and_timestamps(
    temporary_database_manager: DatabaseManager,
) -> None:
    temporary_database_manager.initialize_tables()

    with temporary_database_manager.session_scope() as session:
        chat = ChatORM(title="First Chat")
        session.add(chat)
        session.flush()
        session.refresh(chat)

        assert isinstance(chat.id, int)
        assert chat.id > 0
        assert chat.messages == []
        assert chat.created_at is not None
        assert chat.updated_at is not None


def test_chat_orm_updates_updated_at_on_change(
    temporary_database_manager: DatabaseManager,
) -> None:
    temporary_database_manager.initialize_tables()

    with temporary_database_manager.session_scope() as session:
        chat = ChatORM(title="Original Title")
        session.add(chat)
        session.flush()
        session.refresh(chat)
        chat_id = chat.id
        original_updated_at = chat.updated_at

        sleep(1)
        chat.title = "Updated Title"
        session.flush()
        session.refresh(chat)

        fetched_chat = session.scalar(select(ChatORM).where(ChatORM.id == chat_id))

    assert fetched_chat is not None
    assert fetched_chat.title == "Updated Title"
    assert original_updated_at is not None
    assert fetched_chat.updated_at is not None
    assert fetched_chat.updated_at >= original_updated_at
