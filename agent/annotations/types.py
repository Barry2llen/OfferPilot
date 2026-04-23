from typing import Annotated, Callable

from .reducers import (
    update_if_not_none
)

type Displace[T] = Annotated[T | None, update_if_not_none[T | None]]
type MaybeCallable[T] = T | Callable[..., T]

__all__ = [
    Displace,
    MaybeCallable
]