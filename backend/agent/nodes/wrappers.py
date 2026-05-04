from functools import wraps
from typing import Callable, Generator

from utils.logger import logger

def require_fields(
    *required_fields: str,
    index: int | str = 0,
) -> Callable:
    """
    Decorator to ensure that the specified fields are present in the state before executing the node function.
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if isinstance(index, int):
                state = args[index]
            elif isinstance(index, str):
                state = kwargs.get(index)
                if state is None:
                    logger.error(f"State not found in kwargs with key '{index}' for node '{func.__name__}'")
                    raise ValueError(f"State not found in kwargs with key '{index}'")
            else:
                raise ValueError("Index must be an integer or a string.")
            missing_fields = [field for field in required_fields if field not in state or state[field] is None]
            if missing_fields:
                logger.error(f"Missing required fields for node '{func.__name__}': {missing_fields}")
                raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")
            return func(*args, **kwargs)
        return wrapper
    return decorator

def retry(
    max_retries: int,
) -> Callable:
    """
    Decorator to retry a function if exceptions occur.
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    yield func(*args, **kwargs), attempt
                except Exception as e:
                    yield e, attempt
            logger.debug(f"Function '{func.__name__}' failed after {max_retries} retries.")
            return None, max_retries
        return wrapper
    return decorator