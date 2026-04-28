from .base import OfferPilotError


class DatabaseError(OfferPilotError):
    """Base exception for database configuration and lifecycle errors."""


class DatabaseConfigurationError(DatabaseError, TypeError):
    """Raised when database configuration is invalid."""


__all__ = ["DatabaseConfigurationError", "DatabaseError"]
