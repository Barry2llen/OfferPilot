from typing import (
    Annotated,
    Protocol
)

from .reducers import (
    update_if_not_none
)

type Displace[T] = Annotated[T, update_if_not_none]

class MaybeCallable[T](Protocol):
    def __call__(self, *args, **kwargs) -> T: ...
    def __get__(self, instance, owner) -> T: ...

__all__ = [
    "Displace",
    "MaybeCallable"
]