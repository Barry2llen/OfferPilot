from .base import OfferPilotError


class ChatFileError(OfferPilotError):
    """Base exception for chat file operations."""


class ChatFileValidationError(ChatFileError, ValueError):
    """Raised when a chat file input is invalid."""


class ChatFileNotFoundError(ChatFileError, LookupError):
    """Raised when a chat file record cannot be found."""


class EmptyChatFileContentError(ChatFileValidationError):
    """Raised when the provided chat file content is empty."""


class UnsupportedChatFileError(ChatFileValidationError):
    """Raised when the uploaded chat file type is not supported."""


class ChatFileProcessingError(ChatFileError):
    """Raised when a chat file cannot be processed."""


class ChatThreadImageInputRequiredError(ChatFileValidationError):
    """Raised when a thread requires a vision-capable model."""


__all__ = [
    "ChatFileError",
    "ChatFileNotFoundError",
    "ChatFileProcessingError",
    "ChatFileValidationError",
    "ChatThreadImageInputRequiredError",
    "EmptyChatFileContentError",
    "UnsupportedChatFileError",
]
