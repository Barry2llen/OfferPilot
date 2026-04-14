import pytest
from sqlalchemy import text

from db.engine import DatabaseManager
from db.models import ModelProviderORM
from db.repositories import ModelSelectionRepository
from schemas.model_provider import ModelProvider
from schemas.model_selection import ModelSelection
from services import ModelSelectionService


@pytest.fixture
def initialized_database_manager(
    temporary_database_manager: DatabaseManager,
) -> DatabaseManager:
    temporary_database_manager.initialize_tables()
    return temporary_database_manager


def test_create_and_get_model_selection_schema(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        session.add(ModelProviderORM(name="default-openai", provider="openai"))
        session.flush()

        service = ModelSelectionService(ModelSelectionRepository(session))
        created = service.create(
            ModelSelection(
                provider=ModelProvider(
                    provider="OpenAI",
                    name="default-openai",
                ),
                model_name="gpt-4o-mini",
            )
        )
        fetched = service.get_by_id(created.id or 0)
        stored_row = session.execute(
            text(
                "SELECT provider_name, model_name FROM tb_model_selection "
                "WHERE id = :id"
            ),
            {"id": created.id},
        ).one()

    assert created.id is not None
    assert created.provider.name == "default-openai"
    assert created.provider.provider == "OpenAI"
    assert fetched is not None
    assert fetched.provider.name == "default-openai"
    assert fetched.provider.provider == "OpenAI"
    assert fetched.model_name == "gpt-4o-mini"
    assert stored_row == ("default-openai", "gpt-4o-mini")


def test_list_all_hydrates_provider_schema_values(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        session.add_all(
            [
                ModelProviderORM(name="anthropic-main", provider="anthropic"),
                ModelProviderORM(name="google-main", provider="google"),
            ]
        )
        session.flush()

        service = ModelSelectionService(ModelSelectionRepository(session))
        service.create(
            ModelSelection(
                provider=ModelProvider(
                    provider="Google",
                    name="google-main",
                ),
                model_name="gemini-2.5-pro",
            )
        )
        service.create(
            ModelSelection(
                provider=ModelProvider(
                    provider="Anthropic",
                    name="anthropic-main",
                ),
                model_name="claude-3-7-sonnet",
            )
        )

        selections = service.list_all()

    assert [
        (selection.provider.name, selection.provider.provider, selection.model_name)
        for selection in selections
    ] == [
        ("anthropic-main", "Anthropic", "claude-3-7-sonnet"),
        ("google-main", "Google", "gemini-2.5-pro"),
    ]


def test_update_model_selection_keeps_schema_boundary(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        session.add_all(
            [
                ModelProviderORM(name="openai-main", provider="openai"),
                ModelProviderORM(name="compatible-main", provider="openai compatible"),
            ]
        )
        session.flush()

        service = ModelSelectionService(ModelSelectionRepository(session))
        created = service.create(
            ModelSelection(
                provider=ModelProvider(
                    provider="OpenAI",
                    name="openai-main",
                ),
                model_name="gpt-4o-mini",
            )
        )

        updated = service.update(
            ModelSelection(
                id=created.id,
                provider=ModelProvider(
                    provider="OpenAI Compatible",
                    name="compatible-main",
                    base_url="https://compatible.example.com/v1",
                    api_key="secret-key",
                ),
                model_name="custom-model",
            )
        )
        stored_row = session.execute(
            text(
                "SELECT provider_name, model_name FROM tb_model_selection "
                "WHERE id = :id"
            ),
            {"id": created.id},
        ).one()

    assert updated.id == created.id
    assert updated.provider.name == "compatible-main"
    assert updated.provider.provider == "OpenAI Compatible"
    assert updated.model_name == "custom-model"
    assert stored_row == ("compatible-main", "custom-model")


def test_update_without_id_raises_value_error(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        session.add(ModelProviderORM(name="default-openai", provider="openai"))
        session.flush()

        service = ModelSelectionService(ModelSelectionRepository(session))

        with pytest.raises(ValueError, match="Model selection id is required"):
            service.update(
                ModelSelection(
                    provider=ModelProvider(
                        provider="OpenAI",
                        name="default-openai",
                    ),
                    model_name="gpt-4.1",
                )
            )


def test_create_missing_provider_raises_lookup_error(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        service = ModelSelectionService(ModelSelectionRepository(session))

        with pytest.raises(LookupError, match="Model provider not found"):
            service.create(
                ModelSelection(
                    provider=ModelProvider(
                        provider="OpenAI",
                        name="missing-provider",
                    ),
                    model_name="gpt-4.1",
                )
            )


def test_create_duplicate_model_selection_raises_value_error(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        session.add(ModelProviderORM(name="default-openai", provider="openai"))
        session.flush()

        service = ModelSelectionService(ModelSelectionRepository(session))
        selection = ModelSelection(
            provider=ModelProvider(
                provider="OpenAI",
                name="default-openai",
            ),
            model_name="gpt-4.1",
        )
        service.create(selection)

        with pytest.raises(ValueError, match="Model selection already exists"):
            service.create(selection)


def test_create_with_unsupported_provider_raises_value_error(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        session.add(ModelProviderORM(name="default-openai", provider="openai"))
        session.flush()

        service = ModelSelectionService(ModelSelectionRepository(session))

        with pytest.raises(ValueError, match="Unsupported provider value"):
            service.create(
                ModelSelection.model_construct(
                    provider=ModelProvider.model_construct(
                        provider="Unsupported Provider",
                        name="default-openai",
                    ),
                    model_name="gpt-4.1",
                )
            )


def test_delete_model_selection_returns_expected_flag(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        session.add(ModelProviderORM(name="default-openai", provider="openai"))
        session.flush()

        service = ModelSelectionService(ModelSelectionRepository(session))
        created = service.create(
            ModelSelection(
                provider=ModelProvider(
                    provider="OpenAI",
                    name="default-openai",
                ),
                model_name="gpt-4o-mini",
            )
        )

        deleted = service.delete(created.id or 0)
        deleted_again = service.delete(created.id or 0)
        fetched = service.get_by_id(created.id or 0)

    assert deleted is True
    assert deleted_again is False
    assert fetched is None
