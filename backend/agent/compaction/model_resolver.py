from __future__ import annotations

import asyncio
from typing import Any

from db.engine import DatabaseManager
from db.repositories import (
    ContextCompactionSettingsRepository,
    ModelSelectionRepository,
)
from schemas.model_selection import ModelSelection
from services.context_compaction_settings_service import (
    ContextCompactionSettingsService,
)
from services.model_selection_service import ModelSelectionService

from ..base import GraphRuntime
from .errors import ContextCompactionError
from .protocols import CompactionModelResolver


def resolve_runtime_model_selection(runtime: GraphRuntime) -> ModelSelection:
    selection: Any = runtime.state.get("model")
    if callable(selection):
        selection = selection(state=runtime.state)
    if not isinstance(selection, ModelSelection):
        raise ContextCompactionError(
            "The current runtime model selection is unavailable for auto-compaction."
        )
    return selection


class RuntimeCompactionModelResolver(CompactionModelResolver):
    async def aresolve(self, runtime: GraphRuntime) -> ModelSelection:
        return resolve_runtime_model_selection(runtime)


class DatabaseCompactionModelResolver(CompactionModelResolver):
    """Resolve the optional global model setting without blocking the event loop."""

    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    async def aresolve(self, runtime: GraphRuntime) -> ModelSelection:
        fallback = resolve_runtime_model_selection(runtime)
        return await asyncio.to_thread(self._resolve_sync, fallback)

    def _resolve_sync(self, fallback: ModelSelection) -> ModelSelection:
        with self.database.session_scope() as session:
            selection_repository = ModelSelectionRepository(session)
            settings = ContextCompactionSettingsService(
                ContextCompactionSettingsRepository(session),
                selection_repository,
            ).get()
            if settings.model_selection_id is None:
                return fallback

            selected = ModelSelectionService(selection_repository).get_by_id(
                settings.model_selection_id
            )
            if selected is None:
                return fallback

            return selected


__all__ = [
    "DatabaseCompactionModelResolver",
    "RuntimeCompactionModelResolver",
    "resolve_runtime_model_selection",
]
