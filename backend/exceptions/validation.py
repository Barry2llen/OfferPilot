from .base import OfferPilotError

class ValidationError(OfferPilotError):
    """Base class for unexpected structure or content in structured data."""
    pass

__all__ = [
    "ValidationError"
]