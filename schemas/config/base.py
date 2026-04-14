from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from ruamel.yaml import YAML

from .database import DatabaseConfig, SQLiteDatabaseConfig
from utils.logger import logger


class Config(BaseModel):
    """Configuration for the application."""

    database: DatabaseConfig = Field(default_factory=SQLiteDatabaseConfig)


def _normalize_config_data(config_data: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(config_data, dict):
        return {}

    normalized = dict(config_data)
    legacy_config = normalized.get("offer_pilot")
    if "database" not in normalized and isinstance(legacy_config, dict):
        database_config = legacy_config.get("database")
        if database_config is not None:
            normalized["database"] = database_config

    return normalized


@lru_cache(maxsize=4)
def load_config(config_path: str = "config.yaml") -> Config:
    """Load configuration from a YAML file."""

    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)

    path = Path(config_path)
    if not path.exists():
        return Config()

    with path.open("r", encoding="utf-8") as file:
        config_data = yaml.load(file)

    try:
        return Config(**_normalize_config_data(config_data))
    except Exception as error:
        logger.error(f"Error loading config: {error}")
        return Config()


__all__ = ["Config", "load_config"]
