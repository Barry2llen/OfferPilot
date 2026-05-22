from utils.logger import logger


def _patch_loguru_debug(monkeypatch, debug_messages: list[str]) -> None:
    loguru_logger_class = type(logger).__mro__[1]
    monkeypatch.setattr(
        loguru_logger_class,
        "debug",
        lambda self, message, *args, **kwargs: debug_messages.append(message),
    )


def test_logger_debug_is_skipped_when_debug_disabled(monkeypatch) -> None:
    debug_messages: list[str] = []

    monkeypatch.setattr("utils.logger._is_debug_enabled", lambda: False)
    _patch_loguru_debug(monkeypatch, debug_messages)

    logger.debug("hidden message")

    assert debug_messages == []


def test_logger_debug_runs_when_debug_enabled(monkeypatch) -> None:
    debug_messages: list[str] = []

    monkeypatch.setattr("utils.logger._is_debug_enabled", lambda: True)
    _patch_loguru_debug(monkeypatch, debug_messages)

    logger.debug("visible message")

    assert debug_messages == ["visible message"]
