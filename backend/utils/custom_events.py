from langchain_core.callbacks.manager import (
    adispatch_custom_event,
    dispatch_custom_event,
)

from utils.logger import logger


def _is_missing_parent_run_error(error: RuntimeError) -> bool:
    return "parent run id" in str(error)


def _dispatch_custom_event_safely(name: str, data: object) -> None:
    try:
        dispatch_custom_event(name, data)
    except RuntimeError as error:
        if not _is_missing_parent_run_error(error):
            raise
        error_message = str(error)
        logger.debug(lambda: f"Skipping custom event {name}: {error_message}")


async def _adispatch_custom_event_safely(name: str, data: object) -> None:
    try:
        await adispatch_custom_event(name, data)
    except RuntimeError as error:
        if not _is_missing_parent_run_error(error):
            raise
        error_message = str(error)
        logger.debug(lambda: f"Skipping custom event {name}: {error_message}")
