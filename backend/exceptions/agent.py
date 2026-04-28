from .base import OfferPilotError


class AgentError(OfferPilotError):
    """Base exception for agent graph execution."""


class AgentStateError(AgentError, RuntimeError):
    """Raised when agent state violates graph invariants."""


class ModelCallExecutionError(AgentError, RuntimeError):
    """Raised when a model call cannot complete successfully."""


__all__ = ["AgentError", "AgentStateError", "ModelCallExecutionError"]
