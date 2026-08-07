import sys
from typing import Any, Callable, overload, override

from loguru import logger as _logger


def _is_debug_enabled() -> bool:
    """Read debug config lazily to avoid circular imports during startup."""

    try:
        from schemas.config import load_config

        return load_config().debug
    except Exception:
        return False


class LoggerProxy(type(_logger)):
    """Proxy Loguru logger and gate debug logs by runtime config."""

    def __init__(self, wrapped_logger) -> None:
        self.__dict__.update(wrapped_logger.__dict__)

    @overload
    def debug(self, message: Callable[[], Any], *args: Any, **kwargs: Any) -> None: ...

    @overload
    def debug(self, message: Any, *args: Any, **kwargs: Any) -> None: ...

    @override
    def debug(
        self, message: Any | Callable[[], Any], *args: Any, **kwargs: Any
    ) -> None:
        if _is_debug_enabled():
            super().debug(
                message if not callable(message) else message(), *args, **kwargs
            )


_logger.remove()
_logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {message}",
)
_logger.add("./logs/runtime.log", rotation="10 MB")

logger = LoggerProxy(_logger)


__all__ = ["logger"]
