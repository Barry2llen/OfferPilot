from .base import OfferPilotError


class AgentError(OfferPilotError):
    """Base exception for agent graph execution."""


class AgentStateError(AgentError, RuntimeError):
    """Raised when agent state violates graph invariants."""


class ModelCallExecutionError(AgentError, RuntimeError):
    """Raised when a model call cannot complete successfully."""


class ModelRequestConfigurationError(ModelCallExecutionError):
    """A provider rejected the model request configuration."""


def is_model_bad_request(error: BaseException) -> bool:
    return getattr(error, "status_code", None) == 400 or getattr(error, "code", None) == 400


__all__ = ["AgentError", "AgentStateError", "ModelCallExecutionError", "ModelRequestConfigurationError"]
