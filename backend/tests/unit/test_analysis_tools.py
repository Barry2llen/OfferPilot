from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain.tools import ToolRuntime
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
    message_to_dict,
)
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel
from sqlalchemy import update

from agent.base import BaseAgentState
from agent.checkpointers import DatabaseCheckpointer
from agent.graphs.model_call import ModelCallGraph
from agent.interactions import (
    InteractionBroker,
    InteractionContext,
    ask_user,
    interaction_context,
)
from agent.tools.analysis import (
    AnalysisToolDependencies,
    _content_and_artifact,
    get_analysis_tools,
)
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
from schemas.model_provider import ModelProvider
from schemas.model_selection import ModelSelection
from schemas.resume import Resume
from schemas.resume_document import ResumeDocument
from services.analysis_job_events import AnalysisEventHub, AnalysisJobEvent
from services.chat_file_service import ChatFileService, UploadedChatFile
from services.chat_history_service import _message_text, _to_history_message
from services.chat_runs import ChatRunManager
from services.jd_analysis_jobs import JdAnalysisJobManager
from services.job_description_analysis_service import JobDescriptionAnalysisService
from services.resume_extraction_jobs import ResumeExtractionJobManager
from services.resume_service import ResumeService, UploadedResumeFile
from utils.custom_events import _adispatch_custom_event_safely


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


def _runtime(
    selection: FakeSelection, *, locale: str = "zh-CN"
) -> ToolRuntime[InteractionContext | None]:
    return ToolRuntime[InteractionContext | None](
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
    resume_schema = tools[0].args_schema
    jd_schema = tools[1].args_schema
    assert isinstance(resume_schema, type) and issubclass(resume_schema, BaseModel)
    assert isinstance(jd_schema, type) and issubclass(jd_schema, BaseModel)
    assert set(resume_schema.model_fields) == {
        "resume_id",
        "file_id",
        "runtime",
    }
    assert set(jd_schema.model_fields) == {
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
    assert result["result"]["raw_text"] == "parsed resume"
    assert "detail" not in result


def test_analysis_tool_keeps_full_detail_out_of_model_content() -> None:
    content, artifact = _content_and_artifact(
        {
            "resource_type": "job_description",
            "resource_id": 3,
            "job_id": "job-1",
            "status": "parsed",
            "detail": {
                "id": 3,
                "raw_text": "岗位原文",
                "result": {"job_title": "后端工程师"},
            },
        }
    )

    payload = json.loads(content)
    assert "detail" not in payload
    assert payload["result"] == {"job_title": "后端工程师"}
    assert artifact["detail"]["raw_text"] == "岗位原文"


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
    images = captured[2]["images"]
    assert isinstance(images, list)
    assert images[0].startswith("data:image/png;base64,")


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
            async def aget_state(self, config, **kwargs):
                return SimpleNamespace(next=(), values={}, tasks=())

            async def astream_events(self, state, config, *, version: str):
                assert state["model"].id == selection_id
                yield {
                    "event": "on_custom_event",
                    "name": "on_app_tool_start",
                    "run_id": "analysis-call",
                    "data": {
                        "tool_name": "analyze_resume",
                        "tool_call_id": "analysis-call",
                        "input": {"resume_id": 3},
                    },
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
                    "event": "on_custom_event",
                    "name": "on_app_tool_end",
                    "run_id": "analysis-call",
                    "data": {
                        "tool_name": "analyze_resume",
                        "tool_call_id": "analysis-call",
                        "output": {
                            "resource_type": "resume",
                            "resource_id": 3,
                            "status": "parsed",
                            "result": {"raw_text": "done"},
                        },
                    },
                }
                yield {
                    "event": "on_chain_end",
                    "data": {"output": {"messages": [AIMessage(content="完成")]}},
                }

        app.state.chat_runs.agent = FakeSupervisorAgent()
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
            async def aget_state(self, config, **kwargs):
                return SimpleNamespace(next=(), values={}, tasks=())

            async def astream_events(self, state, config, *, version: str):
                yield {
                    "event": "on_custom_event",
                    "name": "on_app_tool_start",
                    "run_id": "failed-analysis-call",
                    "data": {
                        "tool_name": "analyze_job_description",
                        "tool_call_id": "failed-analysis-call",
                        "input": {"jd_text": "失败 JD"},
                    },
                }
                yield {
                    "event": "on_custom_event",
                    "name": "on_app_tool_end",
                    "run_id": "failed-analysis-call",
                    "data": {
                        "tool_name": "analyze_job_description",
                        "tool_call_id": "failed-analysis-call",
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
                        ),
                    },
                }
                yield {
                    "event": "on_chain_end",
                    "data": {"output": {"messages": [AIMessage(content="失败")]}},
                }

        app.state.chat_runs.agent = FakeSupervisorAgent()
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


@pytest.fixture
async def analysis_env(
    temporary_app_config, temporary_database_manager
) -> AsyncGenerator[Any, None]:
    database = temporary_database_manager
    database.initialize_tables()
    service, hub = _dependencies(temporary_app_config, database)
    selection_id = _create_database_selection(database)
    env = SimpleNamespace(
        database=database,
        service=service,
        hub=hub,
        document=_create_resume(temporary_app_config, database),
        selection=ModelSelection(
            id=selection_id,
            model_name="test",
            provider=ModelProvider(provider="OpenAI", name="test-provider"),
        ),
    )
    try:
        yield env
    finally:
        await service.resume_jobs.shutdown()
        await service.jd_jobs.shutdown()
        await hub.close()


def _resume_detail(env):
    with env.database.get_session_factory()() as session:
        return env.service._resumes(session).get_resume(env.document.id)


async def _until(predicate) -> None:
    async with asyncio.timeout(5):
        while not predicate():
            await asyncio.sleep(0.005)


@pytest.mark.parametrize("kind", ["resume", "job_description"])
@pytest.mark.parametrize("failed", [False, True])
async def test_analysis_tool_waits_for_result_after_progress_queue_overflows(
    analysis_env: Any, monkeypatch: pytest.MonkeyPatch, kind: str, failed: bool
) -> None:
    env = analysis_env
    observer_ready = asyncio.Event()
    release_observer = asyncio.Event()
    burst_sent = asyncio.Event()
    finish = asyncio.Event()
    forwarded: list[dict[str, Any]] = []

    class Workflow:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def astream_events(
            self, selection: Any, *args: Any, **kwargs: Any
        ) -> Resume | JobDescription:
            await observer_ready.wait()
            for index in range(300):
                await kwargs["handlers"]["on_custom_event"](
                    {
                        "name": "on_progress_update",
                        "data": {
                            "progress": index / 300,
                            "message": "Extracted resume text.",
                        },
                    }
                )
            burst_sent.set()
            await finish.wait()
            if failed:
                raise RuntimeError("Burst workflow failed")
            if kind == "resume":
                return Resume(document=args[0], raw_text="completed after burst")
            return JobDescription(
                raw_text="completed after burst", job_title="Engineer"
            )

    async def forward_event(name: str, data: dict[str, Any]) -> None:
        if data["event"] in {"resume", "job_description"}:
            observer_ready.set()
            await release_observer.wait()
        forwarded.append(data)

    monkeypatch.setattr(
        "services.resume_extraction_jobs.ResumeExtractWorkflow"
        if kind == "resume"
        else "services.jd_analysis_jobs.JdAnalysisWorkflow",
        Workflow,
    )
    monkeypatch.setattr(
        "agent.tools.analysis._adispatch_custom_event_safely", forward_event
    )
    tool = get_analysis_tools(env.service)[kind == "job_description"]
    args = {"resume_id": env.document.id} if kind == "resume" else {"jd_text": "job"}
    task = asyncio.create_task(
        tool.ainvoke({**args, "runtime": _runtime(env.selection, locale="en-US")})
    )
    try:
        await asyncio.wait_for(burst_sent.wait(), 5)
        release_observer.set()
        await _until(
            lambda: (
                task.done() or any(item["event"] == "progress" for item in forwarded)
            )
        )
        assert not task.done(), "Slow observation must not end an active analysis"
        finish.set()
        output = await asyncio.wait_for(task, 5)
        assert isinstance(output, ToolMessage)
        assert output.status == ("error" if failed else "success")
        assert output.artifact["status"] == ("failed" if failed else "parsed")
        assert forwarded[-1]["event"] == ("error" if failed else "final")
        if kind == "resume":
            detail = _resume_detail(env)
            assert detail.parse_status == ("failed" if failed else "parsed")
            assert detail.parse_error == ("Burst workflow failed" if failed else None)
        else:
            with env.database.get_session_factory()() as session:
                detail = JobDescriptionAnalysisService(
                    JobDescriptionAnalysisRepository(session)
                ).get_analysis(output.artifact["resource_id"])
            assert detail.status == ("failed" if failed else "parsed")
            assert detail.error_message == ("Burst workflow failed" if failed else None)
    finally:
        release_observer.set()
        finish.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize(
    "kind,args",
    [
        ("resume", {}),
        ("resume", {"resume_id": -1}),
        ("resume", {"resume_id": 9999}),
        ("resume", {"file_id": "missing"}),
        ("resume", {"resume_id": 1, "file_id": "any"}),
        ("job_description", {}),
        ("job_description", {"jd_text": "  "}),
        ("job_description", {"file_ids": ["missing"]}),
    ],
)
async def test_invalid_tool_sources_leave_no_processing_record(
    analysis_env, kind, args
):
    env = analysis_env
    tool = get_analysis_tools(env.service)[kind == "job_description"]
    output = await tool.ainvoke({**args, "runtime": _runtime(env.selection)})
    assert isinstance(output, ToolMessage) and output.status == "error"
    assert _resume_detail(env).parse_status == "unparsed"
    with env.database.get_session_factory()() as session:
        assert JobDescriptionAnalysisRepository(session).list_all() == []


async def test_unsupported_file_sources_do_not_create_analysis_records(analysis_env):
    env = analysis_env
    file_id = _store_chat_file(env.service.config, env.database, "notes.txt", b"text")
    resume_tool, jd_tool = get_analysis_tools(env.service)
    resume = await _invoke(resume_tool, {"file_id": file_id}, env.selection)
    jd = await _invoke(jd_tool, {"file_ids": [file_id]}, env.selection)
    assert resume["status"] == jd["status"] == "failed"
    with env.database.get_session_factory()() as session:
        assert len(ResumeDocumentRepository(session).list_all()) == 1
        assert JobDescriptionAnalysisRepository(session).list_all() == []


async def test_busy_resume_keeps_existing_job_and_link(analysis_env, monkeypatch):
    env = analysis_env
    entered, release = asyncio.Event(), asyncio.Event()

    class Workflow:
        def __init__(self, **kwargs):
            pass

        async def astream_events(self, selection, resume_document, **kwargs):
            entered.set()
            await release.wait()
            return Resume(raw_text="original job", document=resume_document)

    monkeypatch.setattr(
        "services.resume_extraction_jobs.ResumeExtractWorkflow", Workflow
    )
    tool = get_analysis_tools(env.service)[0]
    first = asyncio.create_task(
        _invoke(tool, {"resume_id": env.document.id}, env.selection)
    )
    await entered.wait()
    active = env.service.resume_jobs.active_job(env.document.id)
    second = await tool.ainvoke(
        {"resume_id": env.document.id, "runtime": _runtime(env.selection)}
    )
    assert isinstance(second, ToolMessage) and second.status == "error"
    assert second.artifact["resource_id"] == env.document.id
    assert second.artifact["job_id"] == active.job_id
    assert second.artifact["status"] == "processing"
    assert _resume_detail(env).parse_status == "processing"
    release.set()
    assert (await first)["status"] == "parsed"
    assert _resume_detail(env).raw_text == "original job"


@pytest.mark.parametrize("kind", ["resume", "job_description"])
async def test_failed_launch_persists_and_broadcasts_failure(
    analysis_env, monkeypatch, kind
):
    env = analysis_env
    manager = env.service.resume_jobs if kind == "resume" else env.service.jd_jobs

    async def fail_start(**kwargs):
        raise RuntimeError("Could not launch workflow")

    monkeypatch.setattr(manager, "start", fail_start)
    args = {"resume_id": env.document.id} if kind == "resume" else {"jd_text": "job"}
    tool = get_analysis_tools(env.service)[kind == "job_description"]
    output = await _invoke(tool, args, env.selection)
    assert output["status"] == "failed" and output["resource_type"] == kind
    events = env.hub.stream(locale="en-US")
    snapshot = await anext(events)
    await events.aclose()
    assert '"status": "failed"' in snapshot
    if kind == "resume":
        assert _resume_detail(env).parse_status == "failed"
    else:
        with env.database.get_session_factory()() as session:
            detail = JobDescriptionAnalysisService(
                JobDescriptionAnalysisRepository(session)
            ).get_analysis(output["resource_id"])
        assert detail.status == "failed"


@pytest.mark.parametrize("kind", ["resume", "job_description"])
async def test_cancelled_tool_awaits_job_and_keeps_history_metadata(
    analysis_env, monkeypatch, kind
):
    env = analysis_env
    entered, cleaned = asyncio.Event(), asyncio.Event()

    class Workflow:
        def __init__(self, **kwargs):
            pass

        async def astream_events(self, *args, **kwargs):
            assert interaction_context.get() is None
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                cleaned.set()

    monkeypatch.setattr(
        "services.resume_extraction_jobs.ResumeExtractWorkflow"
        if kind == "resume"
        else "services.jd_analysis_jobs.JdAnalysisWorkflow",
        Workflow,
    )

    async def publish(*args):
        pass

    runtime = _runtime(env.selection)
    runtime.context = InteractionContext(InteractionBroker(publish), "run", "thread")
    args = {"resume_id": env.document.id} if kind == "resume" else {"jd_text": "job"}
    tool = get_analysis_tools(env.service)[kind == "job_description"]
    task = asyncio.create_task(tool.ainvoke({**args, "runtime": runtime}))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned.is_set()
    message = runtime.context.messages[-1]
    assert isinstance(message, ToolMessage) and message.status == "error"
    assert message.artifact["resource_type"] == kind
    if kind == "resume":
        assert _resume_detail(env).parse_status == "failed"
        assert _resume_detail(env).parse_error == "Analysis was cancelled."
    else:
        with env.database.get_session_factory()() as session:
            detail = JobDescriptionAnalysisService(
                JobDescriptionAnalysisRepository(session)
            ).get_analysis(message.artifact["resource_id"])
        assert (
            detail.status == "failed"
            and detail.error_message == "Analysis was cancelled."
        )


async def test_cancellation_before_job_coroutine_starts_still_persists_failure(
    analysis_env,
):
    env = analysis_env
    handle = await env.service.start_resume(
        selection=env.selection, resume_id=env.document.id, file_id=None, locale="en-US"
    )
    await handle.manager.cancel(handle.resource_id, handle.job_id)
    assert _resume_detail(env).parse_status == "failed"
    assert _resume_detail(env).parse_error == "Analysis was cancelled."


async def test_sqlite_writer_does_not_block_analysis_preparation_or_completion(
    analysis_env,
    temporary_async_database_manager,
    monkeypatch,
):
    env = analysis_env
    release = asyncio.Event()

    class Workflow:
        def __init__(self, **kwargs):
            pass

        async def astream_events(self, selection, resume_document, **kwargs):
            await release.wait()
            return Resume(document=resume_document, raw_text="concurrent result")

    monkeypatch.setattr(
        "services.resume_extraction_jobs.ResumeExtractWorkflow", Workflow
    )
    async with temporary_async_database_manager.session_scope() as session:
        await session.execute(update(ModelProviderORM).values(base_url="first-writer"))
        preparing = asyncio.create_task(
            env.service.start_resume(
                selection=env.selection,
                resume_id=env.document.id,
                file_id=None,
                locale="en-US",
            )
        )
        await asyncio.sleep(0.05)
    handle = await asyncio.wait_for(preparing, 3)
    async with temporary_async_database_manager.session_scope() as session:
        await session.execute(update(ModelProviderORM).values(base_url="second-writer"))
        release.set()
        await asyncio.sleep(0.05)
    async with asyncio.timeout(3):
        async for event in handle.manager.events(handle.resource_id, handle.job_id):
            if event.event == "final":
                break
    assert _resume_detail(env).raw_text == "concurrent result"


async def test_cancellation_waits_for_preparation_and_marks_its_record_failed(
    analysis_env, monkeypatch
):
    from services.analysis_service import AnalysisService

    env = analysis_env
    entered, release = threading.Event(), threading.Event()
    prepare = AnalysisService._prepare_resume

    def slow_prepare(self, *args):
        detail = prepare(self, *args)
        entered.set()
        assert release.wait(3)
        return detail

    async def publish(*args):
        pass

    monkeypatch.setattr(AnalysisService, "_prepare_resume", slow_prepare)
    runtime = _runtime(env.selection)
    runtime.context = InteractionContext(InteractionBroker(publish), "run", "thread")
    task = asyncio.create_task(
        get_analysis_tools(env.service)[0].ainvoke(
            {"resume_id": env.document.id, "runtime": runtime}
        )
    )
    assert await asyncio.to_thread(entered.wait, 3)
    task.cancel()
    await asyncio.sleep(0.01)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert _resume_detail(env).parse_status == "failed"
    message = runtime.context.messages[-1]
    assert (
        isinstance(message, ToolMessage)
        and message.artifact["resource_id"] == env.document.id
    )


async def test_replacement_finishes_old_tool_without_overwriting_new_result(
    analysis_env, monkeypatch
):
    env = analysis_env
    entered = asyncio.Event()

    class Workflow:
        def __init__(self, **kwargs):
            pass

        async def astream_events(self, selection, resume_document, **kwargs):
            if resume_document.original_filename != "replacement.pdf":
                entered.set()
                await asyncio.Event().wait()
            return Resume(document=resume_document, raw_text="replacement result")

    monkeypatch.setattr(
        "services.resume_extraction_jobs.ResumeExtractWorkflow", Workflow
    )
    first = asyncio.create_task(
        _invoke(
            get_analysis_tools(env.service)[0],
            {"resume_id": env.document.id},
            env.selection,
        )
    )
    await entered.wait()
    old = env.service.resume_jobs.active_job(env.document.id)
    with env.database.get_session_factory()() as session:
        service = env.service._resumes(session)
        service.replace_resume_file(
            env.document.id,
            UploadedResumeFile("replacement.pdf", "application/pdf", b"replacement"),
        )
        detail = service.begin_extraction(env.document.id, env.selection.id)
    new_id = await env.service.resume_jobs.start(
        resume_id=env.document.id,
        selection_id=env.selection.id,
        selection=env.selection,
        resume_document=ResumeDocument.model_validate(detail.model_dump()),
        initial_event=AnalysisJobEvent("resume", {"resume": detail}),
    )
    result = await asyncio.wait_for(first, 5)
    assert result["status"] == "failed" and result["job_id"] == old.job_id
    async for event in env.service.resume_jobs.events(env.document.id, new_id):
        if event.event == "final":
            break
    assert _resume_detail(env).raw_text == "replacement result"


async def test_cancel_after_persistence_preserves_successful_analysis(
    analysis_env, monkeypatch
):
    env = analysis_env

    class Workflow:
        def __init__(self, **kwargs):
            pass

        async def astream_events(self, selection, resume_document, **kwargs):
            return Resume(document=resume_document, raw_text="already completed")

    async def interrupt_final(name, data):
        if data.get("event") == "final":
            raise asyncio.CancelledError

    async def publish(*args):
        pass

    monkeypatch.setattr(
        "services.resume_extraction_jobs.ResumeExtractWorkflow", Workflow
    )
    monkeypatch.setattr(
        "agent.tools.analysis._adispatch_custom_event_safely", interrupt_final
    )
    runtime = _runtime(env.selection)
    runtime.context = InteractionContext(InteractionBroker(publish), "run", "thread")
    with pytest.raises(asyncio.CancelledError):
        await get_analysis_tools(env.service)[0].ainvoke(
            {"resume_id": env.document.id, "runtime": runtime}
        )
    assert _resume_detail(env).parse_status == "parsed"
    result = runtime.context.messages[-1]
    assert isinstance(result, ToolMessage) and result.status == "success"
    assert result.artifact["status"] == "parsed"


async def test_workflow_retry_exhaustion_has_no_chat_input_waiter(
    analysis_env, monkeypatch
):
    env = analysis_env

    class Workflow:
        def __init__(self, **kwargs):
            pass

        async def astream_events(self, selection, **kwargs):
            assert interaction_context.get() is None
            for attempt in range(1, 4):
                await kwargs["handlers"]["on_custom_event"](
                    {
                        "name": "on_model_call_error",
                        "data": {
                            "attempt": attempt,
                            "max_attempts": 3,
                            "error": "rate limit",
                        },
                    }
                )
            await ask_user(
                {"type": "error", "message": "Model call failed after 3 retries."}
            )

    monkeypatch.setattr("services.jd_analysis_jobs.JdAnalysisWorkflow", Workflow)
    output = await _invoke(
        get_analysis_tools(env.service)[1], {"jd_text": "job"}, env.selection
    )
    assert output["status"] == "failed"
    job = env.service.jd_jobs._by_id[output["job_id"]]
    assert [event.event for event in job.history] == [
        "job_description",
        "model_error",
        "model_error",
        "model_error",
        "error",
    ]
    assert "模型调用失败" in output["error"]


async def test_recovery_marks_interrupted_records_failed(analysis_env):
    env = analysis_env
    with env.database.get_session_factory()() as session:
        env.service._resumes(session).begin_extraction(
            env.document.id, env.selection.id
        )
        jd = JobDescriptionAnalysisService(
            JobDescriptionAnalysisRepository(session)
        ).create_processing(
            selection_id=env.selection.id, source_url=None, image_file_ids=[]
        )
    env.service.recover()
    assert _resume_detail(env).parse_status == "failed"
    with env.database.get_session_factory()() as session:
        recovered = JobDescriptionAnalysisRepository(session).get_by_id(jd.id)
        assert recovered is not None and recovered.status == "failed"
        assert recovered.completed_at is not None


async def test_analysis_snapshots_locale_reconnect_and_slow_subscriber():
    hub = AnalysisEventHub(subscriber_events=1)
    identity = {
        "resource_type": "resume",
        "resource_id": 2,
        "job_id": "j",
        "status": "processing",
    }
    stream = hub.stream(locale="en-US")
    assert '"tasks": []' in await anext(stream)
    await hub.publish(AnalysisJobEvent("resume", identity))
    await hub.publish(
        AnalysisJobEvent(
            "progress",
            {**identity, "progress": 0.5, "message": "Starting resume extraction."},
        )
    )
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    reconnect = hub.stream(locale="zh-CN")
    snapshot = await anext(reconnect)
    assert '"progress": 0.5' in snapshot and "开始解析简历" in snapshot
    await hub.publish(
        AnalysisJobEvent(
            "error",
            {**identity, "status": "failed", "detail": "Analysis was cancelled."},
        )
    )
    assert "分析已取消" in await anext(reconnect)
    await reconnect.aclose()
    english = hub.stream(locale="en-US")
    assert "Analysis was cancelled." in await anext(english)
    await english.aclose()
    await hub.close()


@pytest.mark.parametrize("cancel", [False, True])
async def test_native_chat_analysis_disconnect_replay_and_cancel(
    analysis_env, temporary_async_database_manager, monkeypatch, cancel
):
    env = analysis_env
    release = asyncio.Event()
    calls = []

    class Workflow:
        def __init__(self, **kwargs):
            pass

        async def astream_events(self, selection, resume_document, **kwargs):
            calls.append("started")
            assert interaction_context.get() is None
            await _adispatch_custom_event_safely(
                "on_app_tool_start",
                {"tool_name": "internal", "tool_call_id": "internal"},
            )
            await kwargs["handlers"]["on_custom_event"](
                {
                    "name": "on_progress_update",
                    "data": {"progress": 0.4, "message": "Extracted resume text."},
                }
            )
            await release.wait()
            return Resume(document=resume_document, raw_text="native result")

    class Model:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            if (
                isinstance(messages[-1], HumanMessage)
                and messages[-1].content == "analyze"
            ):
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "analysis",
                            "name": "analyze_resume",
                            "args": {"resume_id": env.document.id},
                        }
                    ],
                )
            return AIMessage(content="finished")

    monkeypatch.setattr(
        "services.resume_extraction_jobs.ResumeExtractWorkflow", Workflow
    )
    monkeypatch.setattr("agent.graphs.model_call.load_chat_model", lambda _: Model())
    inner = ModelCallGraph(
        config=env.service.config, tools=get_analysis_tools(env.service)
    ).get_compiled_graph()
    root = (
        StateGraph(BaseAgentState)
        .add_node("model_call", inner)
        .add_edge(START, "model_call")
        .add_edge("model_call", END)
    )
    manager = ChatRunManager(
        config=env.service.config,
        database=env.database,
        agent=root.compile(
            checkpointer=DatabaseCheckpointer(
                env.database, temporary_async_database_manager
            )
        ),
    )

    async def submit(prompt):
        return await manager.enqueue(
            key=prompt,
            fingerprint=prompt,
            thread_id="analysis-thread",
            prepare=lambda: {
                "prompt": prompt,
                "selection_id": env.selection.id,
                "locale": "en-US",
                "file_ids": [],
                "human_message": message_to_dict(
                    HumanMessage(content=prompt, id=prompt)
                ),
            },
        )

    try:
        row = await submit("analyze")
        run = manager.runs[row["run_id"]]
        await _until(
            lambda: any(item["event"] == "tool_progress" for item in run.projection)
        )
        stream = manager.stream(row["run_id"])
        snapshot = await anext(stream)
        await stream.aclose()
        assert "tool_progress" in snapshot and '"resource_id"' in snapshot
        assert _resume_detail(env).parse_status == "processing"
        if cancel:
            await manager.cancel(row["run_id"])
            assert _resume_detail(env).parse_status == "failed"
        else:
            release.set()
            await asyncio.wait_for(run.done.wait(), 5)
            assert _resume_detail(env).raw_text == "native result"
        terminal = [
            item
            for item in run.projection
            if item["event"] in {"tool_end", "tool_error"}
        ]
        assert len(terminal) == 1
        assert terminal[0]["data"]["output"]["resource_id"] == env.document.id
        assert terminal[0]["event"] == ("tool_error" if cancel else "tool_end")
        assert "internal" not in json.dumps(run.projection)
        snapshot_state = await manager.agent.aget_state(
            {"configurable": {"thread_id": "analysis-thread"}}
        )
        tool_message = next(
            message
            for message in snapshot_state.values["messages"]
            if isinstance(message, ToolMessage)
        )
        assert tool_message.artifact["resource_id"] == env.document.id
        assert (
            _to_history_message(tool_message).content["resource_id"] == env.document.id
        )
        if cancel:
            assert _message_text(tool_message) == "Analysis was cancelled."
        projection_count = len(run.projection)
        await manager.publish(
            row["run_id"],
            "tool_progress",
            {"tool_call_id": "analysis", "progress": 0.1},
        )
        assert len(run.projection) == projection_count
        next_row = await submit("next")
        await asyncio.wait_for(manager.runs[next_row["run_id"]].done.wait(), 5)
        assert (await manager.get(next_row["run_id"]))["status"] == "completed"
        assert calls == ["started"]
    finally:
        await manager.shutdown()
