import pytest
from sqlalchemy import text

from db.engine import DatabaseManager
from db.models import ModelProviderORM, ModelSelectionORM
from db.repositories import ModelSelectionRepository
from exceptions import (
    ModelProviderNotFoundError,
    ModelSelectionAlreadyExistsError,
    ModelSelectionNotFoundError,
)


@pytest.fixture
def initialized_database_manager(
    temporary_database_manager: DatabaseManager,
) -> DatabaseManager:
    temporary_database_manager.initialize_tables()
    return temporary_database_manager


def test_create_and_get_model_selection(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        session.add(ModelProviderORM(name="default-openai", provider="openai"))
        session.flush()

        repository = ModelSelectionRepository(session)
        created = repository.create(
            ModelSelectionORM(
                provider_name="default-openai",
                model_name="gpt-4o-mini",
                supports_image_input=True,
            )
        )
        fetched = repository.get_by_id(created.id)
        stored_row = session.execute(
            text(
                "SELECT provider_name, model_name, supports_image_input FROM tb_model_selection "
                "WHERE id = :id"
            ),
            {"id": created.id},
        ).one()

    assert created.id > 0
    assert created.provider_name == "default-openai"
    assert created.provider.name == "default-openai"
    assert fetched is not None
    assert fetched.model_name == "gpt-4o-mini"
    assert fetched.supports_image_input is True
    assert fetched.provider.provider == "openai"
    assert stored_row == ("default-openai", "gpt-4o-mini", 1)


def test_list_all_returns_provider_and_model_sorted_records(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        session.add_all(
            [
                ModelProviderORM(name="b-provider", provider="google"),
                ModelProviderORM(name="a-provider", provider="anthropic"),
            ]
        )
        session.flush()

        repository = ModelSelectionRepository(session)
        repository.create(
            ModelSelectionORM(
                provider_name="b-provider",
                model_name="gemini-2.5-pro",
                supports_image_input=True,
            )
        )
        repository.create(
            ModelSelectionORM(
                provider_name="a-provider",
                model_name="claude-3-7-sonnet",
            )
        )

        selections = repository.list_all()

    assert [
        (
            selection.provider_name,
            selection.model_name,
            selection.supports_image_input,
        )
        for selection in selections
    ] == [
        ("a-provider", "claude-3-7-sonnet", False),
        ("b-provider", "gemini-2.5-pro", True),
    ]


def test_create_duplicate_model_selection_raises_domain_error(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        session.add(ModelProviderORM(name="shared-provider", provider="openai"))
        session.flush()

        repository = ModelSelectionRepository(session)
        repository.create(
            ModelSelectionORM(
                provider_name="shared-provider",
                model_name="gpt-4.1",
            )
        )

        with pytest.raises(
            ModelSelectionAlreadyExistsError,
            match="Model selection already exists",
        ):
            repository.create(
                ModelSelectionORM(
                    provider_name="shared-provider",
                    model_name="gpt-4.1",
                )
            )


def test_create_missing_provider_raises_domain_error(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        repository = ModelSelectionRepository(session)

        with pytest.raises(ModelProviderNotFoundError, match="Model provider not found"):
            repository.create(
                ModelSelectionORM(
                    provider_name="missing-provider",
                    model_name="gpt-4.1",
                )
            )


def test_update_model_selection_updates_provider_and_model_name(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        session.add_all(
            [
                ModelProviderORM(name="openai-default", provider="openai"),
                ModelProviderORM(name="anthropic-default", provider="anthropic"),
            ]
        )
        session.flush()

        repository = ModelSelectionRepository(session)
        created = repository.create(
            ModelSelectionORM(
                provider_name="openai-default",
                model_name="gpt-4o-mini",
            )
        )

        updated = repository.update(
            ModelSelectionORM(
                id=created.id,
                provider_name="anthropic-default",
                model_name="claude-3-7-sonnet",
                supports_image_input=True,
            )
        )
        stored_row = session.execute(
            text(
                "SELECT provider_name, model_name, supports_image_input FROM tb_model_selection "
                "WHERE id = :id"
            ),
            {"id": created.id},
        ).one()

    assert updated.id == created.id
    assert updated.provider_name == "anthropic-default"
    assert updated.provider.name == "anthropic-default"
    assert updated.model_name == "claude-3-7-sonnet"
    assert updated.supports_image_input is True
    assert stored_row == ("anthropic-default", "claude-3-7-sonnet", 1)


def test_update_missing_model_selection_raises_domain_error(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        session.add(ModelProviderORM(name="default-openai", provider="openai"))
        session.flush()

        repository = ModelSelectionRepository(session)

        with pytest.raises(
            ModelSelectionNotFoundError,
            match="Model selection not found",
        ):
            repository.update(
                ModelSelectionORM(
                    id=999,
                    provider_name="default-openai",
                    model_name="gpt-4.1",
                )
            )


def test_delete_model_selection_returns_expected_flag(
    initialized_database_manager: DatabaseManager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        session.add(ModelProviderORM(name="default-openai", provider="openai"))
        session.flush()

        repository = ModelSelectionRepository(session)
        created = repository.create(
            ModelSelectionORM(
                provider_name="default-openai",
                model_name="gpt-4o-mini",
            )
        )

        deleted = repository.delete(created.id)
        deleted_again = repository.delete(created.id)
        fetched = repository.get_by_id(created.id)

    assert deleted is True
    assert deleted_again is False
    assert fetched is None
