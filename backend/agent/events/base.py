
from typing import TypedDict, NotRequired

class BaseEvent(TypedDict):
    """
    Base class for custom events' data payload.
    """
    additional_data: NotRequired[dict]

class ErrorEvent(BaseEvent):
    """
    Event data for error events.
    """
    error: str

class ModelCallErrorEvent(ErrorEvent):
    """
    Event data for model call error events.
    """
    attempt: int
    max_attempts: int

class ToolCallErrorEvent(ErrorEvent):
    """
    Event data for tool call error events.
    """
    tool_name: str
    args: dict
    tool_call_id: str

class ProgressUpdateEvent(BaseEvent):
    """
    Event data for progress update events.
    """
    progress: float
    message: NotRequired[str | None]

__all__ = ["BaseEvent", "ErrorEvent", "ModelCallErrorEvent", "ToolCallErrorEvent", "ProgressUpdateEvent"]