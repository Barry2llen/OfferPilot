
from typing import (
    NotRequired,
    TypedDict,
    Literal
)

type CommandType = Literal['prompt', 'continue', 'retry', 'query']
type QueryChoice = Literal['firstChoice', 'secondChoice', 'thirdChoice', 'other']

class BaseCommand(TypedDict):
    type: CommandType
    prompt: NotRequired[str | None]
    choice: NotRequired[QueryChoice]
    note: NotRequired[str | None]

__all__ = [
    "CommandType",
    "QueryChoice",
    "BaseCommand"
]
