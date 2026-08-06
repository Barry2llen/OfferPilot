from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ContextCompactionSettingsORM


class ContextCompactionSettingsRepository:
    """Repository for the singleton context compaction setting."""

    _SINGLETON_ID = 1

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self) -> ContextCompactionSettingsORM | None:
        return self._session.scalar(
            select(ContextCompactionSettingsORM).where(
                ContextCompactionSettingsORM.id == self._SINGLETON_ID
            )
        )

    def get_or_create(self) -> ContextCompactionSettingsORM:
        settings = self.get()
        if settings is not None:
            return settings

        settings = ContextCompactionSettingsORM(id=self._SINGLETON_ID)
        self._session.add(settings)
        self._session.flush()
        return settings

    def set_model_selection_id(self, model_selection_id: int | None) -> ContextCompactionSettingsORM:
        settings = self.get_or_create()
        settings.model_selection_id = model_selection_id
        self._session.flush()
        self._session.refresh(settings)
        return settings


__all__ = ["ContextCompactionSettingsRepository"]
