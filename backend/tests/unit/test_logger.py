from utils.logger import logger


def test_logger_debug_is_skipped_when_debug_disabled(monkeypatch) -> None:
    debug_messages: list[str] = []

    monkeypatch.setattr("utils.logger._is_debug_enabled", lambda: False)
    monkeypatch.setattr(
        "utils.logger._logger.debug",
        lambda message, *args, **kwargs: debug_messages.append(message),
    )

    logger.debug("hidden message")

    assert debug_messages == []


def test_logger_debug_runs_when_debug_enabled(monkeypatch) -> None:
    debug_messages: list[str] = []

    monkeypatch.setattr("utils.logger._is_debug_enabled", lambda: True)
    monkeypatch.setattr(
        "utils.logger._logger.debug",
        lambda message, *args, **kwargs: debug_messages.append(message),
    )

    logger.debug("visible message")

    assert debug_messages == ["visible message"]
