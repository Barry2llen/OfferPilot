import sys
from typing import Any

from loguru import logger as _logger


def _is_debug_enabled() -> bool:
    """Read debug config lazily to avoid circular imports during startup."""

    try:
        from schemas.config import load_config

        return load_config().debug
    except Exception:
        return False


class LoggerProxy:
    """Proxy Loguru logger and gate debug logs by runtime config."""

    def __init__(self, wrapped_logger: Any) -> None:
        self._wrapped_logger = wrapped_logger

    def debug(self, message: Any, *args: Any, **kwargs: Any) -> Any | None:
        if not _is_debug_enabled():
            return None
        return self._wrapped_logger.debug(message, *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped_logger, name)


_logger.remove()
_logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {message}",
)
_logger.add("./logs/runtime.log", rotation="10 MB")

logger = LoggerProxy(_logger)


__all__ = ["logger"]
