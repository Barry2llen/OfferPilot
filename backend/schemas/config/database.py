from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class BaseDatabaseConfig(BaseModel):
    """Shared runtime settings for relational databases."""

    model_config = ConfigDict(extra="forbid")

    echo: bool = False
    pool_pre_ping: bool = True
    pool_size: int | None = None
    max_overflow: int | None = None


class SQLiteDatabaseConfig(BaseDatabaseConfig):
    """Configuration for SQLite database."""

    type: Literal["sqlite"] = "sqlite"
    path: str = "./data/offer_pilot.db"


class PostgreSQLDatabaseConfig(BaseDatabaseConfig):
    """Configuration for PostgreSQL database."""

    type: Literal["postgresql"] = "postgresql"
    host: str
    port: int = 5432
    database: str
    user: str
    password: str
    driver: str = "psycopg"


DatabaseConfig = Annotated[
    SQLiteDatabaseConfig | PostgreSQLDatabaseConfig,
    Field(discriminator="type"),
]


__all__ = [
    "BaseDatabaseConfig",
    "DatabaseConfig",
    "PostgreSQLDatabaseConfig",
    "SQLiteDatabaseConfig",
]
