import pytest
from sqlalchemy import text

from agent.base import GraphRuntime
from agent.compaction import DatabaseCompactionModelResolver
from db.engine import DatabaseManager
from db.models import ModelProviderORM, ModelSelectionORM
from db.repositories import (
    ContextCompactionSettingsRepository,
    ModelSelectionRepository,
)
from schemas.model_provider import ModelProvider
from schemas.model_selection import ModelSelection
from services.context_compaction_settings_service import (
    ContextCompactionSettingsService,
)


@pytest.fixture
def initialized_database_manager(
    temporary_database_manager: DatabaseManager,
) -> DatabaseManager:
    temporary_database_manager.initialize_tables()
    return temporary_database_manager


def test_context_compaction_settings_is_singleton_and_model_deletion_clears_reference(
    initialized_database_manager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        session.add(ModelProviderORM(name="default-openai", provider="openai"))
        session.flush()
        selection = ModelSelectionRepository(session).create(
            ModelSelectionORM(
                provider_name="default-openai",
                model_name="gpt-4o-mini",
            )
        )
        settings_repository = ContextCompactionSettingsRepository(session)
        service = ContextCompactionSettingsService(
            settings_repository,
            ModelSelectionRepository(session),
        )
        updated = service.update(selection.id)
        session.delete(selection)
        session.flush()
        refreshed = service.get()

        stored_rows = session.execute(
            text("SELECT id, model_selection_id FROM tb_context_compaction_settings")
        ).all()

    assert updated.model_selection_id == selection.id
    assert refreshed.model_selection_id is None
    assert stored_rows == [(1, None)]


async def test_database_compaction_model_resolver_uses_dynamic_setting_or_current_model(
    initialized_database_manager,
) -> None:
    with initialized_database_manager.session_scope() as session:
        session.add(ModelProviderORM(name="default-openai", provider="openai"))
        session.flush()
        current = ModelSelectionRepository(session).create(
            ModelSelectionORM(
                provider_name="default-openai",
                model_name="gpt-4o-mini",
            )
        )
        compaction = ModelSelectionRepository(session).create(
            ModelSelectionORM(
                provider_name="default-openai",
                model_name="gpt-4.1-mini",
            )
        )
        ContextCompactionSettingsService(
            ContextCompactionSettingsRepository(session),
            ModelSelectionRepository(session),
        ).update(compaction.id)

    current_model = ModelSelection(
        id=current.id,
        provider=ModelProvider(
            provider="OpenAI",
            name="default-openai",
        ),
        model_name=current.model_name,
    )
    runtime = GraphRuntime(
        state={"messages": [], "model": current_model},
        additional_args=(),
        additional_keywords={},
    )
    resolver = DatabaseCompactionModelResolver(initialized_database_manager)

    selected = await resolver.aresolve(runtime)
    assert selected.model_name == "gpt-4.1-mini"

    with initialized_database_manager.session_scope() as session:
        ContextCompactionSettingsService(
            ContextCompactionSettingsRepository(session),
            ModelSelectionRepository(session),
        ).update(None)

    fallback = await resolver.aresolve(runtime)
    assert fallback == current_model
