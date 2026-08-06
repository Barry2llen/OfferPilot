class ContextCompactionError(RuntimeError):
    """Raised when Supervisor cannot build a safe model context."""


__all__ = ["ContextCompactionError"]
