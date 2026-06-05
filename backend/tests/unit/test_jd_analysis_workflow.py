import pytest

from agent.workflows.jd_analyzer.workflow import JdAnalysisWorkflow
from exceptions.job_description import JobDescriptionAnalysisValidationError
from schemas.config import Config
from schemas.job_description import JdFactEx, JdFactsEx, JobDescription
from schemas.model_provider import ModelProvider
from schemas.model_selection import ModelSelection
from services.jd_analysis_jobs import (
    _JD_ANALYSIS_EVENT_STREAM_OPTIONS,
    _keep_jd_analysis_workflow_event,
)


def _model_selection() -> ModelSelection:
    return ModelSelection(
        provider=ModelProvider(provider="OpenAI", name="default-openai"),
        model_name="gpt-4o-mini",
        supports_image_input=True,
    )


def _job_description() -> JobDescription:
    return JobDescription(
        raw_text="岗位职责：负责后端服务开发。",
        source_url="https://example.com/jobs/123",
        job_title="后端开发工程师",
    )


def test_construct_initial_state_keeps_all_jd_inputs(
    temporary_app_config: Config,
) -> None:
    workflow = JdAnalysisWorkflow(config=temporary_app_config)
    model = _model_selection()
    images = ["data:image/png;base64,ZmFrZQ=="]

    state = workflow._construct_initial_state(
        model=model,
        jd_text="岗位职责：负责后端服务开发。",
        source_url="https://example.com/jobs/123",
        images=images,
    )

    assert state == {
        "model": model,
        "messages": [],
        "jd_text": "岗位职责：负责后端服务开发。",
        "source_url": "https://example.com/jobs/123",
        "images": images,
    }


def test_get_result_returns_job_description(
    temporary_app_config: Config,
) -> None:
    workflow = JdAnalysisWorkflow(config=temporary_app_config)
    job_description = _job_description()

    result = workflow._get_result({"job_description": job_description})

    assert result is job_description


def test_get_result_requires_job_description(
    temporary_app_config: Config,
) -> None:
    workflow = JdAnalysisWorkflow(config=temporary_app_config)

    with pytest.raises(ValueError, match="Missing required fields: job_description"):
        workflow._get_result({"job_description": None})


def test_get_result_raises_jd_error_for_terminal_extraction_failure(
    temporary_app_config: Config,
) -> None:
    workflow = JdAnalysisWorkflow(config=temporary_app_config)

    with pytest.raises(JobDescriptionAnalysisValidationError, match="not a JD"):
        workflow._get_result({"jd_error": "not a JD"})


async def test_ainvoke_builds_initial_state_and_uses_graph_config(
    temporary_app_config: Config,
) -> None:
    workflow = JdAnalysisWorkflow(config=temporary_app_config)
    model = _model_selection()
    job_description = _job_description()
    captured: dict[str, object] = {}

    class FakeAgent:
        async def ainvoke(self, state, config):
            captured["state"] = state
            captured["config"] = config
            return {"job_description": job_description}

    workflow.agent = FakeAgent()

    result = await workflow.ainvoke(
        model=model,
        jd_text="岗位职责：负责后端服务开发。",
        source_url="https://example.com/jobs/123",
        images=None,
    )

    assert result is job_description
    assert captured["state"] == {
        "model": model,
        "messages": [],
        "jd_text": "岗位职责：负责后端服务开发。",
        "source_url": "https://example.com/jobs/123",
        "images": None,
    }
    assert captured["config"]["recursion_limit"] == temporary_app_config.graph_recursion_limit


async def test_astream_events_keeps_default_langchain_events(
    temporary_app_config: Config,
) -> None:
    workflow = JdAnalysisWorkflow(config=temporary_app_config)
    job_description = _job_description()
    seen_stream_events: list[str] = []
    captured: dict[str, object] = {}

    class FakeAgent:
        def astream_events(self, state, config, **kwargs):
            captured["kwargs"] = kwargs

            async def events():
                yield {
                    "event": "on_chain_stream",
                    "name": "inner",
                    "data": {"chunk": {"ignored": True}},
                }
                yield {
                    "event": "on_chain_end",
                    "name": "LangGraph",
                    "data": {"output": {"job_description": job_description}},
                }

            return events()

    workflow.agent = FakeAgent()

    result = await workflow.astream_events(
        model=_model_selection(),
        handlers={
            "on_chain_stream": lambda event: seen_stream_events.append(event["name"])
        },
    )

    assert result is job_description
    assert seen_stream_events == ["inner"]
    assert captured["kwargs"] == {"version": "v2"}


async def test_astream_events_applies_optional_event_filter_without_losing_final_state(
    temporary_app_config: Config,
) -> None:
    workflow = JdAnalysisWorkflow(config=temporary_app_config)
    job_description = _job_description()
    seen_events: list[str] = []
    captured: dict[str, object] = {}

    class FakeAgent:
        def astream_events(self, state, config, **kwargs):
            captured["kwargs"] = kwargs

            async def events():
                yield {
                    "event": "on_chain_stream",
                    "name": "inner",
                    "data": {"chunk": {"ignored": True}},
                }
                yield {
                    "event": "on_chain_end",
                    "name": "LangGraph",
                    "data": {"output": {"job_description": job_description}},
                }

            return events()

    workflow.agent = FakeAgent()

    result = await workflow.astream_events(
        model=_model_selection(),
        handlers={
            "on_chain_stream": lambda event: seen_events.append(event["event"]),
            "on_chain_end": lambda event: seen_events.append(event["event"]),
        },
        event_filter=lambda event: event["event"] == "on_chain_end",
        event_stream_options={"exclude_types": ["chat_model"]},
    )

    assert result is job_description
    assert seen_events == ["on_chain_end"]
    assert captured["kwargs"] == {
        "version": "v2",
        "exclude_types": ["chat_model"],
    }


def test_jd_analysis_event_filter_keeps_custom_and_chain_end_only() -> None:
    facts = JdFactsEx(
        facts=[
            JdFactEx(
                fact_type="skill",
                text="熟悉 Python",
                evidence="熟悉 Python",
                keywords=["Python"],
            )
        ]
    )

    assert _keep_jd_analysis_workflow_event(
        {"event": "on_custom_event", "name": "on_progress_update", "data": {}}
    )
    assert _keep_jd_analysis_workflow_event(
        {
            "event": "on_chain_end",
            "name": "LangGraph",
            "data": {"output": {"job_description": _job_description()}},
        }
    )
    assert not _keep_jd_analysis_workflow_event(
        {
            "event": "on_chat_model_end",
            "name": "ChatOpenAI",
            "data": {"output": {"parsed": facts}},
        }
    )
    assert not _keep_jd_analysis_workflow_event(
        {
            "event": "on_parser_end",
            "name": "PydanticOutputParser",
            "data": {"output": facts},
        }
    )
    assert _JD_ANALYSIS_EVENT_STREAM_OPTIONS == {
        "exclude_types": ["chat_model", "llm", "parser"]
    }
