from .base import OfferPilotError


class ModelError(OfferPilotError):
    """Base exception for model configuration and execution setup."""


class UnsupportedModelProviderError(ModelError, ValueError):
    """Raised when a model provider value is not supported."""


class ModelProviderAlreadyExistsError(ModelError, ValueError):
    """Raised when creating a duplicate model provider."""


class ModelProviderNotFoundError(ModelError, LookupError):
    """Raised when a model provider cannot be found."""


class ModelSelectionAlreadyExistsError(ModelError, ValueError):
    """Raised when creating a duplicate model selection."""


class ModelSelectionNotFoundError(ModelError, LookupError):
    """Raised when a model selection cannot be found."""


class ModelSelectionValidationError(ModelError, ValueError):
    """Raised when model selection input is invalid."""


class ChatModelLoadError(ModelError):
    """Raised when a chat model cannot be initialized."""


__all__ = [
    "ChatModelLoadError",
    "ModelError",
    "ModelProviderAlreadyExistsError",
    "ModelProviderNotFoundError",
    "ModelSelectionAlreadyExistsError",
    "ModelSelectionNotFoundError",
    "ModelSelectionValidationError",
    "UnsupportedModelProviderError",
]
