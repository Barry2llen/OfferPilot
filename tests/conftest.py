import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from ruamel.yaml import YAML

from db.engine import DatabaseManager
from schemas.config import Config, SQLiteDatabaseConfig


load_dotenv(Path.cwd() / ".env", override=False)


@pytest.fixture
def workspace_tmp_dir() -> Path:
    base_dir = Path("dev") / "test-tmp"
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


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
def temporary_sqlite_path(workspace_tmp_dir: Path) -> Path:
    return workspace_tmp_dir / "offer_pilot_test.db"


@pytest.fixture
def temporary_sqlite_config(temporary_sqlite_path: Path) -> SQLiteDatabaseConfig:
    return SQLiteDatabaseConfig(path=str(temporary_sqlite_path))


@pytest.fixture
def temporary_resume_upload_dir(workspace_tmp_dir: Path) -> Path:
    return workspace_tmp_dir / "resumes"


@pytest.fixture
def temporary_app_config(
    temporary_sqlite_config: SQLiteDatabaseConfig,
    temporary_resume_upload_dir: Path,
) -> Config:
    return Config(
        database=temporary_sqlite_config,
        resume_upload_dir=str(temporary_resume_upload_dir),
    )


@pytest.fixture
def temporary_database_manager(
    temporary_sqlite_config: SQLiteDatabaseConfig,
) -> DatabaseManager:
    manager = DatabaseManager(temporary_sqlite_config)
    try:
        yield manager
    finally:
        manager.dispose()
