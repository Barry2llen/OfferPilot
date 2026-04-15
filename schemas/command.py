
from typing import (
    TypedDict,
    Literal
)

type CommandType = Literal['prompt', 'continue', 'retry']

class BaseCommand(TypedDict):
    type: CommandType
    prompt: str | None = None

__all__ = [
    CommandType,
    BaseCommand
]