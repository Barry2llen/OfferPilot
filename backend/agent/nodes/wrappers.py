from functools import wraps
from inspect import iscoroutinefunction
from typing import Callable

from utils.logger import logger


def require_fields(
    *required_fields: str,
    index: int | str = 0,
) -> Callable:
    """
    Decorator to ensure that the specified fields are present in the state before executing the node function.
    """

    def decorator(func: Callable):
        def _validate_fields(*args, **kwargs) -> None:
            if isinstance(index, int):
                state = args[index]
            elif isinstance(index, str):
                state = kwargs.get(index)
                if state is None:
                    logger.error(
                        f"State not found in kwargs with key '{index}' for node '{func.__name__}'"
                    )
                    raise ValueError(f"State not found in kwargs with key '{index}'")
            else:
                raise ValueError("Index must be an integer or a string.")
            missing_fields = [
                field
                for field in required_fields
                if field not in state or state[field] is None
            ]
            if missing_fields:
                logger.error(
                    f"Missing required fields for node '{func.__name__}': {missing_fields}"
                )
                raise ValueError(
                    f"Missing required fields: {', '.join(missing_fields)}"
                )

        if iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                _validate_fields(*args, **kwargs)
                return await func(*args, **kwargs)

            return async_wrapper

        @wraps(func)
        def wrapper(*args, **kwargs):
            _validate_fields(*args, **kwargs)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def requires_permission():
    """
    Decorate a tool call function to check for necessary permissions before execution.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):

            return func(*args, **kwargs)

        return wrapper

    return decorator
