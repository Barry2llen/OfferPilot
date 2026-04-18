import asyncio
import os
from collections.abc import Mapping

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables.schema import StreamEvent

from agent.workflows.resume_advice import resume_advice
from db.engine import DatabaseManager
from db.repositories import ResumeDocumentRepository
from exceptions import ResumeNotFoundError
from schemas.config import Config, load_config
from schemas.model_selection import ModelSelection, ModelProvider
from schemas.resume_document import ResumeDocument
from services.document_parser_service import DocumentParserService
from services.resume_service import ResumeService
from utils.stream import render_stream_events


@pytest.fixture
def debug_config(monkeypatch: pytest.MonkeyPatch) -> Config:
    config = load_config().model_copy(update={"debug": True})
    monkeypatch.setattr("schemas.config.load_config", lambda config_path="config.yaml": config)
    monkeypatch.setattr("schemas.config.base.load_config", lambda config_path="config.yaml": config)
    return config


@pytest.fixture
def live_database_manager(debug_config: Config) -> DatabaseManager:
    manager = DatabaseManager(debug_config.database)
    try:
        yield manager
    finally:
        manager.dispose()


def _build_live_model_selection() -> ModelSelection:
    api_key = os.getenv("GEMINI_API_KEY")
    assert api_key, "GEMINI_API_KEY is not set."
    model_provider = ModelProvider(
        provider="Google",
        name="test",
        api_key=api_key,
    )
    return ModelSelection(
        id=1,
        provider=model_provider,
        model_name="models/gemini-3-flash-preview",
        supports_image_input=True,
    )


def _has_non_empty_content(message: AIMessage) -> bool:
    content = message.content
    if isinstance(content, str):
        return bool(content.strip())
    return bool(content)


async def _render_resume_advice_events_to_completion(graph) -> dict:
    final_state: dict | None = None

    def _capture_final_state(event: StreamEvent) -> None:
        nonlocal final_state
        if event["event"] != "on_chain_end":
            return

        output = event["data"].get("output")
        if isinstance(output, Mapping) and output.get("messages"):
            final_state = dict(output)

    await render_stream_events(
        graph.astream_events({}),
        on_event=_capture_final_state,
    )

    assert final_state is not None, "Workflow stream finished without a final state."
    return final_state


def test_resume_advice_workflow_invokes_live_model_with_real_resume_service_record(
    live_database_manager: DatabaseManager,
    debug_config: Config,
) -> None:
    if os.getenv("RUN_LIVE_LLM_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_LLM_TESTS=1 to run live LLM workflow tests.")

    with live_database_manager.session_scope() as session:
        service = ResumeService(
            repository=ResumeDocumentRepository(session),
            parser=DocumentParserService(),
            upload_dir=debug_config.resume_upload_dir,
        )
        try:
            resume_detail = service.get_resume(1)
        except ResumeNotFoundError:
            pytest.skip("Configured database does not contain a resume record with id=1.")

    resume = ResumeDocument.model_validate(resume_detail.model_dump())
    graph = resume_advice(
        resume=resume,
        model=_build_live_model_selection(),
        config=debug_config,
        user_prompt="帮我优化一下简历"
    )

    result = asyncio.run(_render_resume_advice_events_to_completion(graph))

    assert "messages" in result
    assert result["messages"]

    last_message = result["messages"][-1]
    assert isinstance(last_message, AIMessage)
    assert last_message.type == "ai"
    assert _has_non_empty_content(last_message)
