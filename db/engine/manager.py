from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.event import listen
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from db.models import Base
from exceptions import DatabaseConfigurationError
from schemas.config import load_config
from schemas.config.database import (
    DatabaseConfig,
    PostgreSQLDatabaseConfig,
    SQLiteDatabaseConfig,
)
from utils.logger import logger


def build_database_url(config: DatabaseConfig) -> str:
    """Build a SQLAlchemy database URL from typed config."""

    if isinstance(config, SQLiteDatabaseConfig):
        if config.path == ":memory:":
            return "sqlite:///:memory:"

        normalized_path = config.path.replace("\\", "/")
        return f"sqlite:///{normalized_path}"

    if isinstance(config, PostgreSQLDatabaseConfig):
        return (
            f"postgresql+{config.driver}://"
            f"{config.user}:{config.password}@{config.host}:{config.port}/{config.database}"
        )

    raise DatabaseConfigurationError(
        f"Unsupported database config type: {type(config)!r}"
    )


class DatabaseManager:
    """Lazy database engine/session manager."""

    def __init__(self, config: DatabaseConfig) -> None:
        self.config = config
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    def _build_engine_kwargs(self) -> dict[str, object]:
        engine_kwargs: dict[str, object] = {"echo": self.config.echo}

        if isinstance(self.config, SQLiteDatabaseConfig):
            engine_kwargs["poolclass"] = NullPool
            return engine_kwargs

        engine_kwargs["pool_pre_ping"] = self.config.pool_pre_ping
        if self.config.pool_size is not None:
            engine_kwargs["pool_size"] = self.config.pool_size
        if self.config.max_overflow is not None:
            engine_kwargs["max_overflow"] = self.config.max_overflow

        return engine_kwargs

    def _ensure_sqlite_parent_dir(self) -> None:
        if not isinstance(self.config, SQLiteDatabaseConfig):
            return
        if self.config.path == ":memory:":
            return

        database_path = Path(self.config.path)
        if database_path.parent and not database_path.parent.exists():
            database_path.parent.mkdir(parents=True, exist_ok=True)

    def get_engine(self) -> Engine:
        if self._engine is None:
            self._ensure_sqlite_parent_dir()
            self._engine = create_engine(
                build_database_url(self.config),
                **self._build_engine_kwargs(),
            )
            if isinstance(self.config, SQLiteDatabaseConfig):
                listen(self._engine, "connect", _enable_sqlite_foreign_keys)

        return self._engine

    def get_session_factory(self) -> sessionmaker[Session]:
        if self._session_factory is None:
            self._session_factory = sessionmaker(
                bind=self.get_engine(),
                autoflush=False,
                expire_on_commit=False,
            )

        return self._session_factory

    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        session = self.get_session_factory()()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def check_connection(self) -> bool:
        with self.get_engine().connect() as connection:
            return connection.execute(text("SELECT 1")).scalar_one() == 1

    def initialize_tables(self, sql_path: str = "sql/tables.sql") -> None:
        Base.metadata.create_all(self.get_engine())
        logger.info(f"Initialized database tables from ORM metadata; schema snapshot: {sql_path}")

    def dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()

        self._engine = None
        self._session_factory = None


_database_manager: DatabaseManager | None = None


def configure_database_manager(config: DatabaseConfig | None = None) -> DatabaseManager:
    global _database_manager

    target_config = config or load_config().database
    if _database_manager is None:
        _database_manager = DatabaseManager(target_config)
    elif _database_manager.config != target_config:
        _database_manager.dispose()
        _database_manager = DatabaseManager(target_config)

    return _database_manager


def get_database_manager() -> DatabaseManager:
    return configure_database_manager()


def get_db_session() -> Generator[Session, None, None]:
    session = get_database_manager().get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def dispose_database_manager() -> None:
    global _database_manager

    if _database_manager is not None:
        _database_manager.dispose()
        _database_manager = None


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _: object) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


__all__ = [
    "DatabaseManager",
    "build_database_url",
    "configure_database_manager",
    "dispose_database_manager",
    "get_database_manager",
    "get_db_session",
]
