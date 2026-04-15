
from typing import (
    Literal,
    TypedDict
)

type InteruptType = Literal['error', 'question', 'warning', 'other']

class BaseInterupt(TypedDict):
    type: InteruptType = 'other'
    message: str


__all__ = [
    BaseInterupt,
    InteruptType
]