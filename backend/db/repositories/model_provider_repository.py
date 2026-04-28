from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ModelProviderORM
from exceptions import (
    ModelProviderAlreadyExistsError,
    ModelProviderNotFoundError,
)


class ModelProviderRepository:
    """Repository for tb_model_provider CRUD operations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_all(self) -> list[ModelProviderORM]:
        statement = select(ModelProviderORM).order_by(ModelProviderORM.name.asc())
        return self._session.scalars(statement).all()

    def get_by_name(self, name: str) -> ModelProviderORM | None:
        return self._session.get(ModelProviderORM, name)

    def create(self, provider: ModelProviderORM) -> ModelProviderORM:
        if self.get_by_name(provider.name) is not None:
            raise ModelProviderAlreadyExistsError(
                f"Model provider already exists: {provider.name}"
            )

        self._session.add(provider)
        self._session.flush()
        return provider

    def update(self, provider: ModelProviderORM) -> ModelProviderORM:
        orm_provider = self._session.get(ModelProviderORM, provider.name)
        if orm_provider is None:
            raise ModelProviderNotFoundError(
                f"Model provider not found: {provider.name}"
            )

        orm_provider.provider = provider.provider
        orm_provider.base_url = provider.base_url
        orm_provider.api_key = provider.api_key
        self._session.flush()
        return orm_provider

    def delete(self, name: str) -> bool:
        orm_provider = self._session.get(ModelProviderORM, name)
        if orm_provider is None:
            return False

        self._session.delete(orm_provider)
        self._session.flush()
        return True
