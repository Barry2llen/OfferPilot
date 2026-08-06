from __future__ import annotations

from .models import CompactionResult


class ContextCompactionError(RuntimeError):
    """Raised when Supervisor cannot build a safe model context."""

    def __init__(
        self,
        message: str,
        *,
        partial_result: CompactionResult | None = None,
    ) -> None:
        super().__init__(message)
        self.partial_result = partial_result

    def with_partial_result(self, partial_result: CompactionResult) -> ContextCompactionError:
        if self.partial_result is None:
            self.partial_result = partial_result
        return self


__all__ = ["ContextCompactionError"]
