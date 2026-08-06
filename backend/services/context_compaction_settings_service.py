from db.models import ContextCompactionSettingsORM
from db.repositories import (
    ContextCompactionSettingsRepository,
    ModelSelectionRepository,
)
from exceptions import ModelSelectionNotFoundError
from schemas.context_compaction import ContextCompactionSettingsResponse


class ContextCompactionSettingsService:
    """Schema-facing access to the global auto-compaction model setting."""

    def __init__(
        self,
        settings_repository: ContextCompactionSettingsRepository,
        model_selection_repository: ModelSelectionRepository | None = None,
    ) -> None:
        self._settings_repository = settings_repository
        self._model_selection_repository = model_selection_repository

    def get(self) -> ContextCompactionSettingsResponse:
        settings = self._settings_repository.get()
        return self._to_schema(settings)

    def update(self, model_selection_id: int | None) -> ContextCompactionSettingsResponse:
        if model_selection_id is not None:
            if self._model_selection_repository is None:
                raise RuntimeError("Model selection repository is required for an update.")
            if self._model_selection_repository.get_by_id(model_selection_id) is None:
                raise ModelSelectionNotFoundError(
                    f"Model selection not found: {model_selection_id}"
                )

        settings = self._settings_repository.set_model_selection_id(model_selection_id)
        return self._to_schema(settings)

    @staticmethod
    def _to_schema(
        settings: ContextCompactionSettingsORM | None,
    ) -> ContextCompactionSettingsResponse:
        return ContextCompactionSettingsResponse(
            model_selection_id=(
                settings.model_selection_id if settings is not None else None
            )
        )

__all__ = ["ContextCompactionSettingsService"]
