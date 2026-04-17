
from typing import Annotated, Callable

from .reducer import update_if_not_none

type Displace[T] = Annotated[T, update_if_not_none[T]]
type MaybeCallable[T] = T | Callable[..., T]

__all__ = [
    Displace,
    MaybeCallable
]