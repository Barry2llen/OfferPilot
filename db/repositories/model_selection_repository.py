from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from db.models import ModelProviderORM, ModelSelectionORM


class ModelSelectionRepository:
    """Repository for tb_model_selection CRUD operations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_all(self) -> list[ModelSelectionORM]:
        statement = (
            select(ModelSelectionORM)
            .options(joinedload(ModelSelectionORM.provider))
            .order_by(
                ModelSelectionORM.provider_name.asc(),
                ModelSelectionORM.model_name.asc(),
                ModelSelectionORM.id.asc(),
            )
        )
        return self._session.scalars(statement).all()

    def get_by_id(self, selection_id: int) -> ModelSelectionORM | None:
        statement = (
            select(ModelSelectionORM)
            .options(joinedload(ModelSelectionORM.provider))
            .where(ModelSelectionORM.id == selection_id)
        )
        return self._session.scalar(statement)

    def create(self, selection: ModelSelectionORM) -> ModelSelectionORM:
        self._ensure_provider_exists(selection.provider_name)
        self._ensure_unique(selection.provider_name, selection.model_name)

        self._session.add(selection)
        self._session.flush()
        self._session.refresh(selection)
        return self.get_by_id(selection.id) or selection

    def update(self, selection: ModelSelectionORM) -> ModelSelectionORM:
        orm_selection = self._session.get(ModelSelectionORM, selection.id)
        if orm_selection is None:
            raise LookupError(f"Model selection not found: {selection.id}")

        self._ensure_provider_exists(selection.provider_name)
        self._ensure_unique(
            selection.provider_name,
            selection.model_name,
            exclude_id=orm_selection.id,
        )

        orm_selection.provider_name = selection.provider_name
        orm_selection.model_name = selection.model_name
        orm_selection.supports_image_input = selection.supports_image_input
        self._session.flush()
        self._session.refresh(orm_selection)
        return self.get_by_id(orm_selection.id) or orm_selection

    def delete(self, selection_id: int) -> bool:
        orm_selection = self._session.get(ModelSelectionORM, selection_id)
        if orm_selection is None:
            return False

        self._session.delete(orm_selection)
        self._session.flush()
        return True

    def _ensure_provider_exists(self, provider_name: str) -> None:
        if self._session.get(ModelProviderORM, provider_name) is None:
            raise LookupError(f"Model provider not found: {provider_name}")

    def _ensure_unique(
        self,
        provider_name: str,
        model_name: str,
        exclude_id: int | None = None,
    ) -> None:
        statement = select(ModelSelectionORM).where(
            ModelSelectionORM.provider_name == provider_name,
            ModelSelectionORM.model_name == model_name,
        )
        existing = self._session.scalar(statement)
        if existing is None:
            return
        if exclude_id is not None and existing.id == exclude_id:
            return

        raise ValueError(
            "Model selection already exists: "
            f"{provider_name}/{model_name}"
        )
