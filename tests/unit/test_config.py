from pathlib import Path

import pytest
from pydantic import ValidationError
from ruamel.yaml import YAML

from schemas.config import Config, PostgreSQLDatabaseConfig, SQLiteDatabaseConfig, load_config


def test_config_validation_rejects_mixed_database_fields() -> None:
    wrong_config = {
        "database": {
            "type": "postgresql",
            "path": "./data/offer_pilot.db",
        }
    }

    with pytest.raises(ValidationError):
        Config(**wrong_config)


def test_default_config_uses_sqlite() -> None:
    config = Config()
    assert isinstance(config.database, SQLiteDatabaseConfig)
    assert config.database.type == "sqlite"
    assert config.database.path == "./data/offer_pilot.db"
    assert config.resume_upload_dir == "./data/resumes"


def test_config_loads_example(sample_config: Config) -> None:
    assert isinstance(sample_config.database, SQLiteDatabaseConfig)
    assert sample_config.database.type == "sqlite"
    assert sample_config.database.path == "./data/offer_pilot.db"
    assert sample_config.resume_upload_dir == "./data/resumes"


def test_postgresql_config_parses_correctly() -> None:
    config = Config(
        database={
            "type": "postgresql",
            "host": "127.0.0.1",
            "port": 5432,
            "database": "offer_pilot",
            "user": "postgres",
            "password": "secret",
        }
    )

    assert isinstance(config.database, PostgreSQLDatabaseConfig)
    assert config.database.driver == "psycopg"
    assert config.database.host == "127.0.0.1"


@pytest.mark.parametrize(
    ("filename", "payload"),
    [
        (
            "root-config.yaml",
            {
                "database": {
                    "type": "sqlite",
                    "path": "./data/root.db",
                }
            },
        ),
        (
            "legacy-config.yaml",
            {
                "offer_pilot": {
                    "database": {
                        "type": "sqlite",
                        "path": "./data/legacy.db",
                    }
                }
            },
        ),
    ],
)
def test_load_config_supports_root_and_legacy_shapes(
    workspace_tmp_dir: Path,
    yaml_loader: YAML,
    filename: str,
    payload: dict,
) -> None:
    config_path = workspace_tmp_dir / filename
    with config_path.open("w", encoding="utf-8") as file:
        yaml_loader.dump(payload, file)

    load_config.cache_clear()
    try:
        config = load_config(str(config_path))
    finally:
        load_config.cache_clear()

    assert isinstance(config.database, SQLiteDatabaseConfig)
    assert config.database.path in {"./data/root.db", "./data/legacy.db"}
