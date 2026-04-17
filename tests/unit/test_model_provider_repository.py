import pytest
from sqlalchemy import text

from db.models import ModelProviderORM
from db.engine import DatabaseManager
from db.repositories import ModelProviderRepository
from exceptions import (
    ModelProviderAlreadyExistsError,
    ModelProviderNotFoundError,
)


@pytest.fixture
def initialized_database_manager(
    temporary_database_manager: DatabaseManager,
) -> DatabaseManager:
    temporary_database_manager.initialize_tables()
    return temporary_database_manager


def test_create_and_get_model_provider(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        repository = ModelProviderRepository(session)
        created = repository.create(
            ModelProviderORM(
                name="default-openai",
                provider="openai",
            )
        )
        fetched = repository.get_by_name("default-openai")

        stored_provider = session.execute(
            text(
                "SELECT provider FROM tb_model_provider "
                "WHERE name = :name"
            ),
            {"name": "default-openai"},
        ).scalar_one()

    assert created.provider == "openai"
    assert fetched is not None
    assert fetched.provider == "openai"
    assert fetched.base_url is None
    assert fetched.api_key is None
    assert stored_provider == "openai"


def test_list_all_returns_name_sorted_records(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        repository = ModelProviderRepository(session)
        repository.create(
            ModelProviderORM(
                name="z-provider",
                provider="google",
                base_url="https://google.example.com",
            )
        )
        repository.create(
            ModelProviderORM(
                name="a-provider",
                provider="anthropic",
                api_key="test-key",
            )
        )

        providers = repository.list_all()

    assert [provider.name for provider in providers] == ["a-provider", "z-provider"]
    assert providers[0].provider == "anthropic"
    assert providers[0].base_url is None
    assert providers[0].api_key == "test-key"
    assert providers[1].provider == "google"
    assert providers[1].base_url == "https://google.example.com"
    assert providers[1].api_key is None


def test_create_duplicate_model_provider_raises_domain_error(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        repository = ModelProviderRepository(session)
        provider = ModelProviderORM(
            name="shared-name",
            provider="openai compatible",
            base_url="https://compatible.example.com",
        )
        repository.create(provider)

        with pytest.raises(
            ModelProviderAlreadyExistsError,
            match="Model provider already exists",
        ):
            repository.create(provider)


def test_update_model_provider_updates_non_primary_fields(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        repository = ModelProviderRepository(session)
        repository.create(
            ModelProviderORM(
                name="updatable-provider",
                provider="openai",
            )
        )

        updated = repository.update(
            ModelProviderORM(
                name="updatable-provider",
                provider="openai compatible",
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

    assert updated.provider == "openai compatible"
    assert updated.base_url == "https://compatible.example.com/v1"
    assert updated.api_key == "secret-key"
    assert stored_row == (
        "openai compatible",
        "https://compatible.example.com/v1",
        "secret-key",
    )


def test_update_missing_model_provider_raises_domain_error(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        repository = ModelProviderRepository(session)

        with pytest.raises(ModelProviderNotFoundError, match="Model provider not found"):
            repository.update(
                ModelProviderORM(
                    name="missing-provider",
                    provider="google",
                )
            )


def test_delete_model_provider_returns_expected_flag(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        repository = ModelProviderRepository(session)
        repository.create(
            ModelProviderORM(
                name="deletable-provider",
                provider="anthropic",
            )
        )

        deleted = repository.delete("deletable-provider")
        deleted_again = repository.delete("deletable-provider")
        fetched = repository.get_by_name("deletable-provider")

    assert deleted is True
    assert deleted_again is False
    assert fetched is None


def test_initialize_tables_does_not_depend_on_sql_snapshot_file(
    temporary_database_manager: DatabaseManager,
) -> None:
    temporary_database_manager.initialize_tables("sql/does-not-need-to-exist.sql")

    with temporary_database_manager.session_scope() as session:
        tables = {
            row[0]
            for row in session.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name IN "
                    "('tb_model_provider', 'tb_model_selection', 'tb_chat')"
                )
            )
        }

    assert tables == {"tb_model_provider", "tb_model_selection", "tb_chat"}
