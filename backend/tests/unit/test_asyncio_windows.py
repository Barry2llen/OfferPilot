from __future__ import annotations

from collections.abc import Callable
from typing import Any

import utils.asyncio_windows as asyncio_windows


class FakeLoop:
    def __init__(self, handler: Callable[[Any, dict[str, Any]], None] | None = None) -> None:
        self.handler = handler
        self.default_contexts: list[dict[str, Any]] = []

    def get_exception_handler(self) -> Callable[[Any, dict[str, Any]], None] | None:
        return self.handler

    def set_exception_handler(
        self,
        handler: Callable[[Any, dict[str, Any]], None],
    ) -> None:
        self.handler = handler

    def default_exception_handler(self, context: dict[str, Any]) -> None:
        self.default_contexts.append(context)


class WinConnectionResetError(ConnectionResetError):
    @property
    def winerror(self) -> int:
        return 10054


class OtherWinConnectionResetError(ConnectionResetError):
    @property
    def winerror(self) -> int:
        return 10053


def test_windows_proactor_connection_reset_is_suppressed(monkeypatch) -> None:
    monkeypatch.setattr(asyncio_windows.sys, "platform", "win32")
    loop = FakeLoop()

    asyncio_windows.install_windows_connection_reset_filter(loop)  # type: ignore[arg-type]
    assert loop.handler is not None
    loop.handler(
        loop,
        {
            "message": "Exception in callback _ProactorBasePipeTransport._call_connection_lost()",
            "exception": WinConnectionResetError(),
        },
    )

    assert loop.default_contexts == []


def test_non_windows_platform_does_not_install_filter(monkeypatch) -> None:
    monkeypatch.setattr(asyncio_windows.sys, "platform", "linux")
    loop = FakeLoop()

    asyncio_windows.install_windows_connection_reset_filter(loop)  # type: ignore[arg-type]

    assert loop.handler is None


def test_non_matching_connection_reset_uses_default_handler(monkeypatch) -> None:
    monkeypatch.setattr(asyncio_windows.sys, "platform", "win32")
    loop = FakeLoop()
    context = {
        "message": "Exception in callback other_callback()",
        "exception": WinConnectionResetError(),
    }

    asyncio_windows.install_windows_connection_reset_filter(loop)  # type: ignore[arg-type]
    assert loop.handler is not None
    loop.handler(loop, context)

    assert loop.default_contexts == [context]


def test_other_winerror_uses_default_handler(monkeypatch) -> None:
    monkeypatch.setattr(asyncio_windows.sys, "platform", "win32")
    loop = FakeLoop()
    context = {
        "message": "Exception in callback _ProactorBasePipeTransport._call_connection_lost()",
        "exception": OtherWinConnectionResetError(),
    }

    asyncio_windows.install_windows_connection_reset_filter(loop)  # type: ignore[arg-type]
    assert loop.handler is not None
    loop.handler(loop, context)

    assert loop.default_contexts == [context]


def test_existing_handler_receives_unmatched_exceptions(monkeypatch) -> None:
    monkeypatch.setattr(asyncio_windows.sys, "platform", "win32")
    handled_contexts: list[dict[str, Any]] = []

    def previous_handler(_loop: Any, context: dict[str, Any]) -> None:
        handled_contexts.append(context)

    loop = FakeLoop(previous_handler)
    context = {
        "message": "Exception in callback other_callback()",
        "exception": RuntimeError("boom"),
    }

    asyncio_windows.install_windows_connection_reset_filter(loop)  # type: ignore[arg-type]
    assert loop.handler is not None
    loop.handler(loop, context)

    assert handled_contexts == [context]
    assert loop.default_contexts == []


def test_repeated_install_does_not_wrap_handler_again(monkeypatch) -> None:
    monkeypatch.setattr(asyncio_windows.sys, "platform", "win32")
    handled_contexts: list[dict[str, Any]] = []

    def previous_handler(_loop: Any, context: dict[str, Any]) -> None:
        handled_contexts.append(context)

    loop = FakeLoop(previous_handler)
    context = {
        "message": "Exception in callback other_callback()",
        "exception": RuntimeError("boom"),
    }

    asyncio_windows.install_windows_connection_reset_filter(loop)  # type: ignore[arg-type]
    first_installed_handler = loop.handler
    asyncio_windows.install_windows_connection_reset_filter(loop)  # type: ignore[arg-type]
    assert loop.handler is first_installed_handler
    assert loop.handler is not None
    loop.handler(loop, context)

    assert handled_contexts == [context]
