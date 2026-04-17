from db.models import ModelProviderORM
from db.repositories import ModelProviderRepository
from exceptions import UnsupportedModelProviderError
from schemas.model_provider import ModelProvider

_DOMAIN_TO_DATABASE_PROVIDER = {
    "OpenAI": "openai",
    "Google": "google",
    "Anthropic": "anthropic",
    "OpenAI Compatible": "openai compatible",
}
_DATABASE_TO_DOMAIN_PROVIDER = {
    database_value: domain_value
    for domain_value, database_value in _DOMAIN_TO_DATABASE_PROVIDER.items()
}


class ModelProviderService:
    """Service for schema-facing model provider operations."""

    def __init__(self, repository: ModelProviderRepository) -> None:
        self._repository = repository

    def list_all(self) -> list[ModelProvider]:
        return [self._to_schema(provider) for provider in self._repository.list_all()]

    def get_by_name(self, name: str) -> ModelProvider | None:
        provider = self._repository.get_by_name(name)
        if provider is None:
            return None
        return self._to_schema(provider)

    def create(self, provider: ModelProvider) -> ModelProvider:
        created = self._repository.create(self._to_orm(provider))
        return self._to_schema(created)

    def update(self, provider: ModelProvider) -> ModelProvider:
        updated = self._repository.update(self._to_orm(provider))
        return self._to_schema(updated)

    def delete(self, name: str) -> bool:
        return self._repository.delete(name)

    def _to_schema(self, provider: ModelProviderORM) -> ModelProvider:
        domain_provider = _DATABASE_TO_DOMAIN_PROVIDER.get(provider.provider)
        if domain_provider is None:
            raise UnsupportedModelProviderError(
                f"Unsupported provider value: {provider.provider}"
            )

        return ModelProvider(
            provider=domain_provider,
            name=provider.name,
            base_url=provider.base_url,
            api_key=provider.api_key,
        )

    def _to_orm(self, provider: ModelProvider) -> ModelProviderORM:
        database_provider = _DOMAIN_TO_DATABASE_PROVIDER.get(provider.provider)
        if database_provider is None:
            raise UnsupportedModelProviderError(
                f"Unsupported provider value: {provider.provider}"
            )

        return ModelProviderORM(
            name=provider.name,
            provider=database_provider,
            base_url=provider.base_url,
            api_key=provider.api_key,
        )
