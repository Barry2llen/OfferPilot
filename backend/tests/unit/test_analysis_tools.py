from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from langchain.tools import ToolRuntime
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from agent.tools.analysis import AnalysisToolDependencies, get_analysis_tools
from db.models import ModelProviderORM, ModelSelectionORM
from db.repositories import (
    ChatFileRepository,
    ChatThreadFileRepository,
    JobDescriptionAnalysisRepository,
    ResumeDocumentRepository,
    ResumeExtractionRepository,
)
from main import create_app
from schemas.config import Config
from schemas.job_description import JobDescription
from schemas.resume import Resume
from schemas.resume_document import ResumeDocument
from services.analysis_job_events import AnalysisEventHub, AnalysisJobEvent
from services.chat_file_service import ChatFileService, UploadedChatFile
from services.jd_analysis_jobs import JdAnalysisJobManager
from services.job_description_analysis_service import JobDescriptionAnalysisService
from services.resume_extraction_jobs import ResumeExtractionJobManager
from services.resume_service import ResumeService, UploadedResumeFile


class FakeSelection:
    def __init__(self, selection_id: int = 7) -> None:
        self.id = selection_id


def _dependencies(
    config: Config,
    database,
) -> tuple[AnalysisToolDependencies, AnalysisEventHub]:
    event_hub = AnalysisEventHub()
    return (
        AnalysisToolDependencies(
            config=config,
            database=database,
            resume_jobs=ResumeExtractionJobManager(
                config=config,
                database=database,
                event_hub=event_hub,
            ),
            jd_jobs=JdAnalysisJobManager(
                config=config,
                database=database,
                event_hub=event_hub,
            ),
        ),
        event_hub,
    )


def _create_database_selection(database, *, supports_image_input: bool = False) -> int:
    with database.get_session_factory()() as session:
        session.add(ModelProviderORM(name="test-provider", provider="openai"))
        selection = ModelSelectionORM(
            provider_name="test-provider",
            model_name="test-model",
            supports_image_input=supports_image_input,
        )
        session.add(selection)
        session.commit()
        return selection.id


def _runtime(selection: FakeSelection, *, locale: str = "zh-CN") -> ToolRuntime:
    return ToolRuntime(
        state={"model": selection},
        context=None,
        config={"configurable": {"locale": locale}},
        stream_writer=lambda _: None,
        tool_call_id="analysis-call",
        store=None,
    )


async def _invoke(tool, args: dict, selection: FakeSelection) -> dict:
    output = await tool.ainvoke({**args, "runtime": _runtime(selection)})
    if isinstance(output, BaseMessage):
        artifact = getattr(output, "artifact", None)
        if isinstance(artifact, dict):
            return artifact
        return json.loads(str(output.content))
    if isinstance(output, tuple) and len(output) == 2:
        return output[1]
    if isinstance(output, str):
        return json.loads(output)
    raise AssertionError(f"Unexpected tool output: {output!r}")


def _resume_service(config: Config, database) -> ResumeService:
    with database.get_session_factory()() as session:
        return ResumeService(
            repository=ResumeDocumentRepository(session),
            extraction_repository=ResumeExtractionRepository(session),
            upload_dir=config.resume_upload_dir,
        )


def _create_resume(config: Config, database) -> ResumeDocument:
    with database.get_session_factory()() as session:
        service = ResumeService(
            repository=ResumeDocumentRepository(session),
            extraction_repository=ResumeExtractionRepository(session),
            upload_dir=config.resume_upload_dir,
        )
        return ResumeDocument.model_validate(
            service.create_from_file(
                UploadedResumeFile(
                    filename="existing-resume.pdf",
                    content_type="application/pdf",
                    content=b"resume",
                )
            ).model_dump()
        )


def _store_chat_file(config: Config, database, filename: str, content: bytes) -> str:
    with database.get_session_factory()() as session:
        service = ChatFileService(
            file_repository=ChatFileRepository(session),
            thread_file_repository=ChatThreadFileRepository(session),
            upload_dir=config.chat_file_upload_dir,
        )
        stored = service.store_files(
            [
                UploadedChatFile(
                    filename=filename,
                    content_type="application/pdf"
                    if filename.endswith(".pdf")
                    else "image/png",
                    content=content,
                )
            ]
        )
        session.commit()
        return stored.records[0].id


def test_analysis_tools_are_registered_with_explicit_inputs() -> None:
    tools = get_analysis_tools(None)  # type: ignore[arg-type]

    assert [item.name for item in tools] == [
        "analyze_resume",
        "analyze_job_description",
    ]
    assert set(tools[0].args_schema.model_fields) == {
        "resume_id",
        "file_id",
        "runtime",
    }
    assert set(tools[1].args_schema.model_fields) == {
        "jd_text",
        "source_url",
        "file_ids",
        "runtime",
    }


def test_resume_analysis_tool_reuses_existing_record_and_current_model(
    temporary_app_config: Config,
    temporary_database_manager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = temporary_database_manager
    database.initialize_tables()
    captured: dict[str, object] = {}

    class FakeResumeWorkflow:
        def __init__(self, config=None) -> None:
            self.config = config

        async def astream_events(self, selection, resume_document, handlers=None):
            captured["selection"] = selection
            if handlers and "on_custom_event" in handlers:
                await handlers["on_custom_event"](
                    {
                        "name": "on_progress_update",
                        "data": {"progress": 0.5, "message": "解析中"},
                    }
                )
            return Resume(raw_text="parsed resume", document=resume_document)

    monkeypatch.setattr(
        "services.resume_extraction_jobs.ResumeExtractWorkflow", FakeResumeWorkflow
    )
    selection_id = _create_database_selection(database)
    document = _create_resume(temporary_app_config, database)
    dependencies, event_hub = _dependencies(temporary_app_config, database)
    tool = get_analysis_tools(dependencies)[0]
    selection = FakeSelection(selection_id)

    async def scenario() -> dict:
        try:
            return await _invoke(tool, {"resume_id": document.id}, selection)
        finally:
            await dependencies.resume_jobs.shutdown()
            await dependencies.jd_jobs.shutdown()
            await event_hub.close()

    result = asyncio.run(scenario())

    assert captured["selection"] is selection
    assert result["resource_type"] == "resume"
    assert result["resource_id"] == document.id
    assert result["status"] == "parsed"
    assert result["detail"]["raw_text"] == "parsed resume"


def test_resume_analysis_tool_creates_record_from_file_id(
    temporary_app_config: Config,
    temporary_database_manager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = temporary_database_manager
    database.initialize_tables()

    class FakeResumeWorkflow:
        def __init__(self, config=None) -> None:
            self.config = config

        async def astream_events(self, selection, resume_document, handlers=None):
            return Resume(
                raw_text=resume_document.original_filename or "new resume",
                document=resume_document,
            )

    monkeypatch.setattr(
        "services.resume_extraction_jobs.ResumeExtractWorkflow", FakeResumeWorkflow
    )
    selection_id = _create_database_selection(database)
    file_id = _store_chat_file(
        temporary_app_config, database, "library-resume.pdf", b"library resume"
    )
    dependencies, event_hub = _dependencies(temporary_app_config, database)
    tool = get_analysis_tools(dependencies)[0]

    async def scenario() -> dict:
        try:
            return await _invoke(
                tool, {"file_id": file_id}, FakeSelection(selection_id)
            )
        finally:
            await dependencies.resume_jobs.shutdown()
            await dependencies.jd_jobs.shutdown()
            await event_hub.close()

    result = asyncio.run(scenario())

    assert result["status"] == "parsed"
    assert result["resource_id"] == 1
    with database.get_session_factory()() as session:
        detail = ResumeService(
            ResumeDocumentRepository(session),
            temporary_app_config.resume_upload_dir,
            ResumeExtractionRepository(session),
        ).get_resume(1)
    assert detail.original_filename == "library-resume.pdf"


def test_job_description_tool_accepts_text_url_and_image_file(
    temporary_app_config: Config,
    temporary_database_manager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = temporary_database_manager
    database.initialize_tables()
    captured: list[dict[str, object]] = []

    class FakeJdWorkflow:
        def __init__(self, config=None) -> None:
            self.config = config

        async def astream_events(
            self,
            selection,
            jd_text=None,
            source_url=None,
            images=None,
            handlers=None,
        ):
            captured.append(
                {
                    "selection": selection,
                    "jd_text": jd_text,
                    "source_url": source_url,
                    "images": images,
                }
            )
            return JobDescription(
                raw_text=jd_text or source_url or "图片 JD", source_url=source_url
            )

    monkeypatch.setattr("services.jd_analysis_jobs.JdAnalysisWorkflow", FakeJdWorkflow)
    selection_id = _create_database_selection(database)
    image_id = _store_chat_file(
        temporary_app_config, database, "jd.png", b"image bytes"
    )
    dependencies, event_hub = _dependencies(temporary_app_config, database)
    tool = get_analysis_tools(dependencies)[1]
    selection = FakeSelection(selection_id)

    async def scenario() -> tuple[dict, dict, dict]:
        try:
            text_result = await _invoke(tool, {"jd_text": "文本 JD"}, selection)
            url_result = await _invoke(
                tool, {"source_url": "https://example.com/job/1"}, selection
            )
            image_result = await _invoke(tool, {"file_ids": [image_id]}, selection)
            return text_result, url_result, image_result
        finally:
            await dependencies.resume_jobs.shutdown()
            await dependencies.jd_jobs.shutdown()
            await event_hub.close()

    text_result, url_result, image_result = asyncio.run(scenario())

    assert text_result["status"] == "parsed"
    assert url_result["status"] == "parsed"
    assert image_result["status"] == "parsed"
    assert captured[0]["selection"] is selection
    assert captured[0]["jd_text"] == "文本 JD"
    assert captured[1]["source_url"] == "https://example.com/job/1"
    assert captured[2]["images"][0].startswith("data:image/png;base64,")


def test_analysis_tool_returns_failed_status_and_persists_failure(
    temporary_app_config: Config,
    temporary_database_manager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = temporary_database_manager
    database.initialize_tables()

    class FailingJdWorkflow:
        def __init__(self, config=None) -> None:
            self.config = config

        async def astream_events(self, selection, **kwargs):
            raise RuntimeError("JD model failed")

    monkeypatch.setattr(
        "services.jd_analysis_jobs.JdAnalysisWorkflow", FailingJdWorkflow
    )
    selection_id = _create_database_selection(database)
    dependencies, event_hub = _dependencies(temporary_app_config, database)
    tool = get_analysis_tools(dependencies)[1]

    async def scenario() -> dict:
        try:
            return await _invoke(
                tool, {"jd_text": "失败 JD"}, FakeSelection(selection_id)
            )
        finally:
            await dependencies.resume_jobs.shutdown()
            await dependencies.jd_jobs.shutdown()
            await event_hub.close()

    result = asyncio.run(scenario())

    assert result["resource_type"] == "job_description"
    assert result["status"] == "failed"
    assert result["error"] == "JD model failed"
    with database.get_session_factory()() as session:
        detail = JobDescriptionAnalysisService(
            JobDescriptionAnalysisRepository(session)
        ).get_analysis(result["resource_id"])
    assert detail.status == "failed"
    assert detail.error_message == "JD model failed"


def test_analysis_job_continues_after_event_subscriber_disconnects(
    temporary_app_config: Config,
    temporary_database_manager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = temporary_database_manager
    database.initialize_tables()

    class SlowResumeWorkflow:
        def __init__(self, config=None) -> None:
            self.config = config

        async def astream_events(self, selection, resume_document, handlers=None):
            await asyncio.sleep(0.03)
            return Resume(
                raw_text="finished after disconnect", document=resume_document
            )

    monkeypatch.setattr(
        "services.resume_extraction_jobs.ResumeExtractWorkflow", SlowResumeWorkflow
    )
    selection_id = _create_database_selection(database)
    document = _create_resume(temporary_app_config, database)
    with database.get_session_factory()() as session:
        processing_detail = ResumeService(
            ResumeDocumentRepository(session),
            temporary_app_config.resume_upload_dir,
            ResumeExtractionRepository(session),
        ).begin_extraction(document.id, selection_id)
    processing = ResumeDocument.model_validate(processing_detail.model_dump())

    dependencies, event_hub = _dependencies(temporary_app_config, database)
    selection = FakeSelection(selection_id)

    async def scenario() -> None:
        try:
            job_id = await dependencies.resume_jobs.start(
                resume_id=document.id,
                selection_id=selection.id,
                selection=selection,
                resume_document=processing,
                initial_event=AnalysisJobEvent("resume", {"resume": processing}),
            )
            events = dependencies.resume_jobs.events(document.id, job_id)
            assert (await anext(events)).event == "resume"
            await events.aclose()
            await asyncio.sleep(0.08)
        finally:
            await dependencies.resume_jobs.shutdown()
            await dependencies.jd_jobs.shutdown()
            await event_hub.close()

    asyncio.run(scenario())

    with database.get_session_factory()() as session:
        detail = ResumeService(
            ResumeDocumentRepository(session),
            temporary_app_config.resume_upload_dir,
            ResumeExtractionRepository(session),
        ).get_resume(document.id)
    assert detail.parse_status == "parsed", detail.parse_error
    assert detail.raw_text == "finished after disconnect"


def _create_model_selection(client: TestClient) -> int:
    provider = client.post(
        "/model-providers", json={"provider": "OpenAI", "name": "test-provider"}
    )
    selection = client.post(
        "/model-selections",
        json={"provider_name": "test-provider", "model_name": "test-model"},
    )
    assert provider.status_code == 200
    assert selection.status_code == 200
    return selection.json()["id"]


def test_chat_sse_emits_analysis_progress_and_structured_tool_output(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)

        class FakeSupervisorAgent:
            async def astream_events(self, state, config, *, version: str):
                assert state["model"].id == selection_id
                yield {
                    "event": "on_tool_start",
                    "name": "analyze_resume",
                    "run_id": "analysis-call",
                    "data": {"input": {"resume_id": 3}},
                }
                yield {
                    "event": "on_custom_event",
                    "name": "on_analysis_job_event",
                    "data": {
                        "tool_name": "analyze_resume",
                        "tool_call_id": "analysis-call",
                        "resource_type": "resume",
                        "resource_id": 3,
                        "event": "progress",
                        "progress": 0.5,
                        "message": "解析中",
                    },
                }
                yield {
                    "event": "on_tool_start",
                    "name": "mark_jd_extraction_success",
                    "run_id": "nested-analysis-call",
                    "parent_ids": ["analysis-call"],
                    "data": {"input": {"jd_text": "内部文本"}},
                }
                yield {
                    "event": "on_tool_end",
                    "name": "mark_jd_extraction_success",
                    "run_id": "nested-analysis-call",
                    "parent_ids": ["analysis-call"],
                    "data": {"output": "内部结果"},
                }
                yield {
                    "event": "on_tool_end",
                    "name": "analyze_resume",
                    "run_id": "analysis-call",
                    "data": {
                        "output": {
                            "resource_type": "resume",
                            "resource_id": 3,
                            "status": "parsed",
                            "result": {"raw_text": "done"},
                        }
                    },
                }
                yield {
                    "event": "on_chain_end",
                    "data": {"output": {"messages": [AIMessage(content="完成")]}},
                }

        client.app.state.supervisor_agent = FakeSupervisorAgent()
        response = client.post(
            "/ai/chat/stream",
            json={
                "selection_id": selection_id,
                "prompt": "分析简历",
                "thread_id": "analysis-sse",
            },
        )

    assert response.status_code == 200
    assert "event: tool_start" in response.text
    assert '"tool_call_id": "analysis-call"' in response.text
    assert "event: tool_progress" in response.text
    assert '"progress": 0.5' in response.text
    assert "event: tool_end" in response.text
    assert '"status": "parsed"' in response.text
    assert "mark_jd_extraction_success" not in response.text


def test_chat_sse_emits_structured_analysis_tool_failure(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)

        class FakeSupervisorAgent:
            async def astream_events(self, state, config, *, version: str):
                yield {
                    "event": "on_tool_start",
                    "name": "analyze_job_description",
                    "run_id": "failed-analysis-call",
                    "data": {"input": {"jd_text": "失败 JD"}},
                }
                yield {
                    "event": "on_tool_end",
                    "name": "analyze_job_description",
                    "run_id": "failed-analysis-call",
                    "data": {
                        "output": ToolMessage(
                            content=json.dumps(
                                {
                                    "resource_type": "job_description",
                                    "resource_id": 5,
                                    "status": "failed",
                                    "error": "模型失败",
                                },
                                ensure_ascii=False,
                            ),
                            tool_call_id="failed-analysis-call",
                            name="analyze_job_description",
                        )
                    },
                }
                yield {
                    "event": "on_chain_end",
                    "data": {"output": {"messages": [AIMessage(content="失败")]}},
                }

        client.app.state.supervisor_agent = FakeSupervisorAgent()
        response = client.post(
            "/ai/chat/stream",
            json={
                "selection_id": selection_id,
                "prompt": "分析岗位",
                "thread_id": "analysis-sse-failed",
            },
        )

    assert response.status_code == 200
    assert "event: tool_error" in response.text
    assert '"resource_type": "job_description"' in response.text
    assert '"status": "failed"' in response.text


def test_analysis_events_endpoint_is_documented(temporary_app_config: Config) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        openapi = client.get("/openapi.json")

    assert openapi.status_code == 200
    assert "/analysis/events" in openapi.json()["paths"]
