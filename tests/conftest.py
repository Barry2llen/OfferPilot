from pathlib import Path

import pytest
from ruamel.yaml import YAML

from db.engine import DatabaseManager
from schemas.config import Config, SQLiteDatabaseConfig


@pytest.fixture
def yaml_loader() -> YAML:
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


@pytest.fixture
def sample_config(yaml_loader: YAML) -> Config:
    with open("config.example.yaml", "r", encoding="utf-8") as file:
        config = yaml_loader.load(file)
    return Config(**config)


@pytest.fixture
def temporary_sqlite_path(tmp_path: Path) -> Path:
    return tmp_path / "offer_pilot_test.db"


@pytest.fixture
def temporary_sqlite_config(temporary_sqlite_path: Path) -> SQLiteDatabaseConfig:
    return SQLiteDatabaseConfig(path=str(temporary_sqlite_path))


@pytest.fixture
def temporary_database_manager(
    temporary_sqlite_config: SQLiteDatabaseConfig,
) -> DatabaseManager:
    manager = DatabaseManager(temporary_sqlite_config)
    try:
        yield manager
    finally:
        manager.dispose()
