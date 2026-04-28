
from typing import (
    NotRequired,
    TypedDict,
    Literal
)

type CommandType = Literal['prompt', 'continue', 'retry']

class BaseCommand(TypedDict):
    type: CommandType
    prompt: NotRequired[str | None]

__all__ = [
    "CommandType",
    "BaseCommand"
]
