from __future__ import annotations

import asyncio
import sys
from typing import Any

_CONNECTION_RESET_WINERROR = 10054
_PROACTOR_CONNECTION_LOST_CALLBACK = "_call_connection_lost"
_HANDLER_MARKER = "_offerpilot_windows_connection_reset_filter"


def install_windows_connection_reset_filter(
    loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    """Suppress a benign Windows Proactor connection-reset traceback.

    Browsers can close short-lived HTTP connections before Windows asyncio's
    Proactor transport finishes its connection-lost shutdown callback. Python
    then logs the reset as an unhandled callback exception even though the
    request already completed successfully.
    """

    if sys.platform != "win32":
        return

    target_loop = loop or asyncio.get_running_loop()
    previous_handler = target_loop.get_exception_handler()
    if getattr(previous_handler, _HANDLER_MARKER, False):
        return

    def exception_handler(
        current_loop: asyncio.AbstractEventLoop,
        context: dict[str, Any],
    ) -> None:
        if _is_proactor_connection_reset(context):
            return

        if previous_handler is not None:
            previous_handler(current_loop, context)
            return

        current_loop.default_exception_handler(context)

    setattr(exception_handler, _HANDLER_MARKER, True)
    target_loop.set_exception_handler(exception_handler)


def _is_proactor_connection_reset(context: dict[str, Any]) -> bool:
    exception = context.get("exception")
    if not isinstance(exception, ConnectionResetError):
        return False
    if getattr(exception, "winerror", None) != _CONNECTION_RESET_WINERROR:
        return False

    message = str(context.get("message") or "")
    if _PROACTOR_CONNECTION_LOST_CALLBACK in message:
        return True

    handle = context.get("handle")
    if handle is None:
        return False

    callback = getattr(handle, "_callback", None)
    callback_name = getattr(callback, "__name__", "")
    callback_qualname = getattr(callback, "__qualname__", "")
    if callback_name == _PROACTOR_CONNECTION_LOST_CALLBACK:
        return True
    if _PROACTOR_CONNECTION_LOST_CALLBACK in callback_qualname:
        return True

    return _PROACTOR_CONNECTION_LOST_CALLBACK in repr(handle)


__all__ = ["install_windows_connection_reset_filter"]
