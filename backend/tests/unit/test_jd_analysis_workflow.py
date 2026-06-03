import pytest

from agent.workflows.jd_analyzer.workflow import JdAnalysisWorkflow
from exceptions.job_description import JobDescriptionAnalysisValidationError
from schemas.config import Config
from schemas.job_description import JobDescription
from schemas.model_provider import ModelProvider
from schemas.model_selection import ModelSelection


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
