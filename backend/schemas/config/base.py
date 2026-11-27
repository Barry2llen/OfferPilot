from functools import lru_cache
from math import floor
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from ruamel.yaml import YAML

from utils.logger import logger

from .database import DatabaseConfig, SQLiteDatabaseConfig


class WebSearchConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["auto", "fast", "instant", "deep", "deep-lite", "deep-reasoning"] = (
        "auto"
    )
    max_characters: int = 2000
    guiding_query: str | None = None


class CorsConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    allow_origins: tuple[str, ...] = Field(default_factory=lambda: ("*",))
    allow_credentials: bool = False
    allow_methods: tuple[str, ...] = Field(default_factory=lambda: ("*",))
    allow_headers: tuple[str, ...] = Field(default_factory=lambda: ("*",))


class ContextCompactionConfig(BaseModel):
    """Temporary model-view context compaction settings."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    default_max_context_tokens: int = Field(default=128_000, ge=1)
    reserved_output_tokens: int = Field(default=20_000, ge=0)
    safety_margin_tokens: int = Field(default=10_000, ge=0)
    trigger_input_ratio: float = Field(
        default=0.80,
        gt=0,
        lt=1,
        description="Fraction of the hard input limit that triggers proactive summarization.",
        examples=[0.80],
    )
    target_input_ratio: float = Field(
        default=0.60,
        gt=0,
        lt=1,
        description="Fraction of the hard input limit targeted by proactive summarization.",
        examples=[0.60],
    )
    summary_max_tokens: int = Field(
        default=4_000,
        gt=0,
        strict=True,
        description="Maximum total generation tokens for one summary request, including thinking where applicable.",
        examples=[4000],
    )
    keep_recent_turns: int = Field(default=4, ge=0)
    tool_result_max_characters: int = Field(default=6_000, ge=1)
    compact_historical_attachments: bool = True
    model_context_windows: dict[str, int] = Field(default_factory=dict)

    @field_validator("model_context_windows")
    @classmethod
    def _validate_model_context_windows(cls, value: dict[str, int]) -> dict[str, int]:
        if any(not key.strip() for key in value):
            raise ValueError("model_context_windows keys must not be blank.")
        if any(window <= 0 for window in value.values()):
            raise ValueError("model_context_windows values must be positive.")
        return dict(value)

    @model_validator(mode="after")
    def _validate_capacity(self) -> "ContextCompactionConfig":
        input_watermarks(
            self.default_max_context_tokens
            - self.reserved_output_tokens
            - self.safety_margin_tokens,
            self.trigger_input_ratio,
            self.target_input_ratio,
        )
        return self

    def __hash__(self) -> int:
        return hash(
            (
                self.enabled,
                self.default_max_context_tokens,
                self.reserved_output_tokens,
                self.safety_margin_tokens,
                self.trigger_input_ratio,
                self.target_input_ratio,
                self.summary_max_tokens,
                self.keep_recent_turns,
                self.tool_result_max_characters,
                self.compact_historical_attachments,
                tuple(sorted(self.model_context_windows.items())),
            )
        )


def input_watermarks(
    hard_limit: int, trigger_ratio: float, target_ratio: float
) -> tuple[int, int]:
    if not 0 < target_ratio < trigger_ratio < 1:
        raise ValueError("Expected 0 < target_input_ratio < trigger_input_ratio < 1.")
    trigger = floor(hard_limit * trigger_ratio)
    target = floor(hard_limit * target_ratio)
    if not 0 < target < trigger < hard_limit:
        raise ValueError(
            "Context window, output reserve and safety margin must leave distinct "
            f"positive input watermarks (target={target}, trigger={trigger}, hard={hard_limit})."
        )
    return trigger, target


class ChatRunsConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_active: int = Field(default=8, ge=1)
    max_queued_per_thread: int = Field(default=20, ge=1)
    max_pending_inputs: int = Field(default=32, ge=1)
    input_timeout_seconds: float | None = Field(default=None, gt=0)
    replay_events: int = Field(default=2048, ge=1)
    replay_bytes: int = Field(default=4 * 1024 * 1024, ge=1)
    subscriber_events: int = Field(default=256, ge=1)
    terminal_retention_seconds: float = Field(default=1800, gt=0)


class Config(BaseModel, frozen=True):
    """Configuration for the application."""

    database: DatabaseConfig = Field(default_factory=SQLiteDatabaseConfig)
    web_search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    cors: CorsConfig = Field(default_factory=CorsConfig)
    chat_runs: ChatRunsConfig = Field(default_factory=ChatRunsConfig)
    context_compaction: ContextCompactionConfig = Field(
        default_factory=ContextCompactionConfig
    )

    resume_upload_dir: str = "./data/resumes"
    chat_file_upload_dir: str = "./data/chat_files"

    debug: bool = False

    model_call_retry_attempts: int = 3
    graph_recursion_limit: int = Field(
        default=100,
        ge=1,
        description="LangGraph runtime recursion_limit config value.",
    )

    exa_api_key: str | None = None


def _normalize_config_data(config_data: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(config_data, dict):
        return {}

    normalized = dict(config_data)
    legacy_config = normalized.get("offer_pilot")
    if "database" not in normalized and isinstance(legacy_config, dict):
        database_config = legacy_config.get("database")
        if database_config is not None:
            normalized["database"] = database_config

    if "web_search" not in normalized and isinstance(legacy_config, dict):
        web_search_config = legacy_config.get("web_search")
        if web_search_config is not None:
            normalized["web_search"] = web_search_config

    if "cors" not in normalized and isinstance(legacy_config, dict):
        cors_config = legacy_config.get("cors")
        if cors_config is not None:
            normalized["cors"] = cors_config

    return normalized


@lru_cache(maxsize=1)
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
    except ValidationError as error:
        if any(item["loc"][:1] == ("context_compaction",) for item in error.errors()):
            raise
        logger.error(f"Error loading config: {error}")
        return Config()


def reload_config(config_path: str = "config.yaml") -> Config:
    """Clear the config cache to force reloading on next access."""
    load_config.cache_clear()
    return load_config(config_path)


__all__ = [
    "Config",
    "ContextCompactionConfig",
    "CorsConfig",
    "load_config",
    "reload_config",
]
