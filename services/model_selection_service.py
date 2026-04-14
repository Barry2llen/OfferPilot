from db.models import ModelProviderORM, ModelSelectionORM
from db.repositories import ModelSelectionRepository
from schemas.model_provider import ModelProvider
from schemas.model_selection import ModelSelection
from services.model_provider_service import (
    _DATABASE_TO_DOMAIN_PROVIDER,
    _DOMAIN_TO_DATABASE_PROVIDER,
)


class ModelSelectionService:
    """Service for schema-facing model selection operations."""

    def __init__(self, repository: ModelSelectionRepository) -> None:
        self._repository = repository

    def list_all(self) -> list[ModelSelection]:
        return [self._to_schema(selection) for selection in self._repository.list_all()]

    def get_by_id(self, selection_id: int) -> ModelSelection | None:
        selection = self._repository.get_by_id(selection_id)
        if selection is None:
            return None
        return self._to_schema(selection)

    def create(self, selection: ModelSelection) -> ModelSelection:
        created = self._repository.create(self._to_orm(selection))
        return self._to_schema(created)

    def update(self, selection: ModelSelection) -> ModelSelection:
        if selection.id is None:
            raise ValueError("Model selection id is required for update")

        updated = self._repository.update(self._to_orm(selection))
        return self._to_schema(updated)

    def delete(self, selection_id: int) -> bool:
        return self._repository.delete(selection_id)

    def _to_schema(self, selection: ModelSelectionORM) -> ModelSelection:
        return ModelSelection(
            id=selection.id,
            provider=self._to_provider_schema(selection.provider),
            model_name=selection.model_name,
        )

    def _to_orm(self, selection: ModelSelection) -> ModelSelectionORM:
        self._require_supported_provider(selection.provider)
        return ModelSelectionORM(
            id=selection.id,
            provider_name=selection.provider.name,
            model_name=selection.model_name,
        )

    def _to_provider_schema(self, provider: ModelProviderORM) -> ModelProvider:
        provider_name = provider.provider
        domain_provider = _DATABASE_TO_DOMAIN_PROVIDER.get(provider_name)
        if domain_provider is None:
            raise ValueError(f"Unsupported provider value: {provider_name}")

        return ModelProvider(
            provider=domain_provider,
            name=provider.name,
            base_url=provider.base_url,
            api_key=provider.api_key,
        )

    def _require_supported_provider(self, provider: ModelProvider) -> None:
        database_provider = _DOMAIN_TO_DATABASE_PROVIDER.get(provider.provider)
        if database_provider is None:
            raise ValueError(f"Unsupported provider value: {provider.provider}")
