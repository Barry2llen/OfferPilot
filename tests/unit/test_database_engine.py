import os

import pytest
from sqlalchemy import text

from db.engine import DatabaseManager, build_database_url
from schemas.config import PostgreSQLDatabaseConfig, SQLiteDatabaseConfig


def test_build_database_url_for_sqlite(
    temporary_sqlite_config: SQLiteDatabaseConfig,
) -> None:
    assert build_database_url(temporary_sqlite_config).endswith(
        temporary_sqlite_config.path.replace("\\", "/")
    )


def test_build_database_url_for_postgresql() -> None:
    config = PostgreSQLDatabaseConfig(
        host="db.example.com",
        port=5432,
        database="offer_pilot",
        user="postgres",
        password="secret",
    )

    assert (
        build_database_url(config)
        == "postgresql+psycopg://postgres:secret@db.example.com:5432/offer_pilot"
    )


def test_database_manager_is_lazy_and_reuses_factory(
    temporary_sqlite_config: SQLiteDatabaseConfig,
) -> None:
    manager = DatabaseManager(temporary_sqlite_config)
    try:
        assert manager._engine is None
        assert manager._session_factory is None

        engine = manager.get_engine()
        session_factory = manager.get_session_factory()

        assert engine is manager.get_engine()
        assert session_factory is manager.get_session_factory()
    finally:
        manager.dispose()


def test_database_manager_session_scope_and_connection_check(
    temporary_database_manager: DatabaseManager,
) -> None:
    assert temporary_database_manager.check_connection() is True

    with temporary_database_manager.session_scope() as session:
        result = session.execute(text("SELECT 1")).scalar_one()

    assert result == 1


def test_initialize_tables_creates_expected_tables(
    temporary_database_manager: DatabaseManager,
) -> None:
    temporary_database_manager.initialize_tables()

    with temporary_database_manager.session_scope() as session:
        tables = {
            row[0]
            for row in session.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name IN "
                    "('tb_model_provider', 'tb_model_selection', 'tb_chat')"
                )
            )
        }

    assert tables == {"tb_model_provider", "tb_model_selection", "tb_chat"}


def test_initialize_tables_creates_expected_chat_columns(
    temporary_database_manager: DatabaseManager,
) -> None:
    temporary_database_manager.initialize_tables()

    with temporary_database_manager.session_scope() as session:
        columns = {
            row[1]
            for row in session.execute(text("PRAGMA table_info('tb_chat')"))
        }

    assert {"id", "title", "messages", "created_at", "updated_at"} <= columns


def test_initialize_tables_creates_expected_model_selection_constraints(
    temporary_database_manager: DatabaseManager,
) -> None:
    temporary_database_manager.initialize_tables()

    with temporary_database_manager.session_scope() as session:
        columns = {
            row[1]
            for row in session.execute(text("PRAGMA table_info('tb_model_selection')"))
        }
        foreign_keys = list(
            session.execute(text("PRAGMA foreign_key_list('tb_model_selection')"))
        )
        unique_indexes = [
            row[1]
            for row in session.execute(text("PRAGMA index_list('tb_model_selection')"))
            if row[2] == 1
        ]
        unique_index_columns = {
            row[2]
            for index_name in unique_indexes
            for row in session.execute(text(f"PRAGMA index_info('{index_name}')"))
        }

    assert {"id", "provider_name", "model_name"} <= columns
    assert any(
        row[2] == "tb_model_provider"
        and row[3] == "provider_name"
        and row[4] == "name"
        for row in foreign_keys
    )
    assert unique_index_columns == {"provider_name", "model_name"}


def test_database_manager_dispose_reinitializes_engine(
    temporary_sqlite_config: SQLiteDatabaseConfig,
) -> None:
    manager = DatabaseManager(temporary_sqlite_config)
    try:
        first_engine = manager.get_engine()
        manager.dispose()

        second_engine = manager.get_engine()
        assert first_engine is not second_engine
    finally:
        manager.dispose()


def test_postgresql_connection_check_optional() -> None:
    required_env = [
        "TEST_POSTGRES_HOST",
        "TEST_POSTGRES_DATABASE",
        "TEST_POSTGRES_USER",
        "TEST_POSTGRES_PASSWORD",
    ]
    if any(not os.getenv(key) for key in required_env):
        pytest.skip("PostgreSQL integration environment is not configured.")

    config = PostgreSQLDatabaseConfig(
        host=os.environ["TEST_POSTGRES_HOST"],
        port=int(os.getenv("TEST_POSTGRES_PORT", "5432")),
        database=os.environ["TEST_POSTGRES_DATABASE"],
        user=os.environ["TEST_POSTGRES_USER"],
        password=os.environ["TEST_POSTGRES_PASSWORD"],
        driver=os.getenv("TEST_POSTGRES_DRIVER", "psycopg"),
    )
    manager = DatabaseManager(config)
    try:
        assert manager.check_connection() is True
    finally:
        manager.dispose()
