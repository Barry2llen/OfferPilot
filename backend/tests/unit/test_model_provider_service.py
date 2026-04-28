import pytest
from sqlalchemy import text

from db.engine import DatabaseManager
from db.repositories import ModelProviderRepository
from exceptions import UnsupportedModelProviderError
from schemas.model_provider import ModelProvider
from services import ModelProviderService


@pytest.fixture
def initialized_database_manager(
    temporary_database_manager: DatabaseManager,
) -> DatabaseManager:
    temporary_database_manager.initialize_tables()
    return temporary_database_manager


def test_create_and_get_model_provider_schema(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        service = ModelProviderService(ModelProviderRepository(session))
        created = service.create(
            ModelProvider(
                provider="OpenAI",
                name="default-openai",
            )
        )
        fetched = service.get_by_name("default-openai")
        stored_provider = session.execute(
            text(
                "SELECT provider FROM tb_model_provider "
                "WHERE name = :name"
            ),
            {"name": "default-openai"},
        ).scalar_one()

    assert created.provider == "OpenAI"
    assert fetched is not None
    assert fetched.provider == "OpenAI"
    assert stored_provider == "openai"


def test_create_deepseek_model_provider_schema(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        service = ModelProviderService(ModelProviderRepository(session))
        created = service.create(
            ModelProvider(
                provider="DeepSeek",
                name="default-deepseek",
                api_key="sk-deepseek",
            )
        )
        fetched = service.get_by_name("default-deepseek")
        stored_provider = session.execute(
            text(
                "SELECT provider FROM tb_model_provider "
                "WHERE name = :name"
            ),
            {"name": "default-deepseek"},
        ).scalar_one()

    assert created.provider == "DeepSeek"
    assert fetched is not None
    assert fetched.provider == "DeepSeek"
    assert stored_provider == "deepseek"


def test_list_all_returns_domain_provider_values(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        service = ModelProviderService(ModelProviderRepository(session))
        service.create(
            ModelProvider(
                provider="Google",
                name="z-provider",
                base_url="https://google.example.com",
            )
        )
        service.create(
            ModelProvider(
                provider="Anthropic",
                name="a-provider",
                api_key="test-key",
            )
        )

        providers = service.list_all()

    assert [provider.name for provider in providers] == ["a-provider", "z-provider"]
    assert providers[0].provider == "Anthropic"
    assert providers[1].provider == "Google"


def test_update_model_provider_keeps_schema_boundary(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        service = ModelProviderService(ModelProviderRepository(session))
        service.create(
            ModelProvider(
                provider="OpenAI",
                name="updatable-provider",
            )
        )

        updated = service.update(
            ModelProvider(
                provider="OpenAI Compatible",
                name="updatable-provider",
                base_url="https://compatible.example.com/v1",
                api_key="secret-key",
            )
        )
        stored_row = session.execute(
            text(
                "SELECT provider, base_url, api_key "
                "FROM tb_model_provider WHERE name = :name"
            ),
            {"name": "updatable-provider"},
        ).one()

    assert updated.provider == "OpenAI Compatible"
    assert updated.base_url == "https://compatible.example.com/v1"
    assert updated.api_key == "secret-key"
    assert stored_row == (
        "openai compatible",
        "https://compatible.example.com/v1",
        "secret-key",
    )


def test_delete_model_provider_returns_expected_flag(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        service = ModelProviderService(ModelProviderRepository(session))
        service.create(
            ModelProvider(
                provider="Anthropic",
                name="deletable-provider",
            )
        )

        deleted = service.delete("deletable-provider")
        deleted_again = service.delete("deletable-provider")
        fetched = service.get_by_name("deletable-provider")

    assert deleted is True
    assert deleted_again is False
    assert fetched is None


def test_create_with_unsupported_provider_raises_domain_error(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        service = ModelProviderService(ModelProviderRepository(session))

        with pytest.raises(
            UnsupportedModelProviderError,
            match="Unsupported provider value",
        ):
            service.create(
                ModelProvider.model_construct(
                    provider="Unsupported Provider",
                    name="invalid-provider",
                )
            )
