from .base import OfferPilotError


class JobDescriptionAnalysisError(OfferPilotError):
    """Base exception for JD analysis operations."""


class JobDescriptionAnalysisNotFoundError(JobDescriptionAnalysisError, LookupError):
    """Raised when a JD analysis record cannot be found."""


class JobDescriptionAnalysisValidationError(JobDescriptionAnalysisError, ValueError):
    """Raised when JD analysis input is invalid."""


__all__ = [
    "JobDescriptionAnalysisError",
    "JobDescriptionAnalysisNotFoundError",
    "JobDescriptionAnalysisValidationError",
]
