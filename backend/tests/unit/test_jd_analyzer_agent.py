import asyncio

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.constants import END
from pydantic import ValidationError

from agent.agents.jd_analyzer import agent as jd_agent_module
from agent.agents.jd_analyzer import prompt as jd_prompt_module
from agent.agents.jd_analyzer import JdAnalyzerAgent
from agent.tools import web_search as web_search_module
from schemas.config import Config
from schemas.model_provider import ModelProvider
from schemas.model_selection import ModelSelection
from schemas.job_description import (
    JdFactEx,
    JdFactsEx,
    JdRequirementBlockEx,
    JobDescription,
    JobDescriptionEx,
)


_IMAGE_DATA_URL = "data:image/png;base64,ZmFrZS1pbWFnZQ=="


@tool
async def fake_get_content(url: str) -> str:
    """Return fake fetched content."""
    return f"content={url}"


def _model_selection(*, supports_image_input: bool) -> ModelSelection:
    return ModelSelection(
        provider=ModelProvider(provider="OpenAI", name="default-openai"),
        model_name="gpt-4o-mini",
        supports_image_input=supports_image_input,
    )


def test_job_description_ex_accepts_common_llm_aliases_and_ignores_extra_fields() -> None:
    result = JobDescriptionEx.model_validate(
        {
            "company": "示例科技",
            "title": "后端开发工程师",
            "location": "上海",
            "experience": "3年以上后端经验",
            "education": "本科及以上",
            "remote_policy": "不接受居家办公",
            "employment_type": "全职",
            "experience_level": None,
            "education_min": "本科",
            "keywords": ["Python"],
            "other_info": "ignored",
            "blocks": [
                {
                    "type": "must_have",
                    "title": "任职要求",
                    "content": "熟悉 Python。",
                    "other_info": "ignored",
                }
            ],
        }
    )

    assert result.company_name == "示例科技"
    assert result.job_title == "后端开发工程师"
    assert result.primary_location == "上海"
    assert result.experience_raw == "3年以上后端经验"
    assert result.education_raw == "本科及以上"
    assert result.remote_policy_raw == "不接受居家办公"
    assert result.employment_type_raw == "全职"
    assert result.years_experience_min == 3
    assert result.years_experience_max is None
    assert result.education_min_rank == 2
    assert result.blocks[0].block_type == "must_have"
    assert not hasattr(result, "remote_policy")
    assert not hasattr(result, "employment_type")
    assert not hasattr(result, "experience_level")
    assert not hasattr(result, "education_min")
    assert not hasattr(result, "keywords")
    assert not hasattr(result, "other_info")


def test_job_description_final_model_remains_strict() -> None:
    with pytest.raises(ValidationError):
        JobDescription.model_validate(
            {
                "raw_text": "岗位职责：负责后端开发。",
                "job_title": "后端开发工程师",
                "title": "后端开发工程师",
            }
        )


def test_jd_ex_models_normalize_empty_control_enum_fields() -> None:
    block = JdRequirementBlockEx.model_validate(
        {
            "block_type": "",
            "title": "其他",
            "content": "其他说明。",
        }
    )
    fact = JdFactEx.model_validate(
        {
            "fact_type": None,
            "importance": "",
            "text": "熟悉 Python。",
            "evidence": "熟悉 Python。",
        }
    )

    assert block.block_type == "other"
    assert fact.fact_type == "other"
    assert fact.importance == "unknown"


def test_job_description_models_preserve_raw_text_and_normalize_comparable_fields() -> None:
    result = JobDescriptionEx.model_validate(
        {
            "job_title": "后端开发工程师",
            "remote_policy_raw": "不接受居家办公",
            "employment_type_raw": "全职",
            "experience_raw": "3年以上软件开发经验",
            "years_experience_min": -1,
            "years_experience_max": 1,
            "education_raw": "本科及以上",
            "education_min_rank": None,
        }
    )

    assert result.remote_policy_raw == "不接受居家办公"
    assert result.employment_type_raw == "全职"
    assert result.experience_raw == "3年以上软件开发经验"
    assert result.years_experience_min == 3
    assert result.years_experience_max is None
    assert result.education_raw == "本科及以上"
    assert result.education_min_rank == 2


def test_job_description_final_model_accepts_legacy_persisted_fields() -> None:
    result = JobDescription.model_validate(
        {
            "raw_text": "岗位职责：负责后端开发。",
            "job_title": "后端开发工程师",
            "remote_policy": "onsite",
            "employment_type": "full_time",
            "experience_raw": "1-3年后端经验",
            "experience_level": "mid",
            "education_raw": "本科及以上",
            "education_min": "bachelor",
        }
    )

    assert result.remote_policy_raw == "onsite"
    assert result.employment_type_raw == "full_time"
    assert result.years_experience_min == 1
    assert result.years_experience_max == 3
    assert result.education_min_rank == 2
    assert not hasattr(result, "experience_level")


def test_jd_extraction_prompt_constrains_field_names_and_missing_values() -> None:
    prompt = jd_prompt_module.jd_extraction_system_prompt

    assert (
        "company_name, company_industry, company_size, job_title, job_level, "
        "job_family, primary_location, locations, remote_policy_raw, employment_type_raw, "
        "experience_raw, years_experience_min, years_experience_max, education_raw, "
        "education_min_rank, major_requirement, salary, benefits, blocks"
    ) in prompt
    assert (
        "title, location, experience, education, company, keywords, other_info, "
        "remote_policy, employment_type, experience_level, education_min"
    ) in prompt
    assert "block_type" in prompt
    assert "Do NOT output type" in prompt
    assert "For nullable string fields, use null" in prompt
    assert "For list fields, use []" in prompt
    assert "For enum fields, NEVER use null" not in prompt
    assert "Use \"unknown\"" not in prompt
    assert "remote_policy_raw" in prompt
    assert "education_min_rank means" in prompt
    assert "fixed English enum values" in prompt
    assert "use null or the default value" not in prompt


def test_jd_analyzer_graph_has_expected_nodes_and_edges() -> None:
    graph = JdAnalyzerAgent().get_graph()

    assert set(graph.nodes) == {
        "prepare_jd_source",
        "model_call",
        "parse_jd_text",
        "extract_structure",
        "extract_facts",
    }
    assert ("prepare_jd_source", "model_call") in graph.edges
    assert ("model_call", "parse_jd_text") in graph.edges
    assert ("extract_structure", "extract_facts") in graph.edges
    assert ("extract_facts", END) in graph.edges


def test_jd_analyzer_graph_can_compile() -> None:
    compiled_graph = JdAnalyzerAgent().get_agent()

    assert compiled_graph is not None


def test_jd_text_input_is_prepared_for_model_call() -> None:
    agent = JdAnalyzerAgent()

    result = agent._prepare_jd_source_node(
        {
            "jd_text": "岗位职责：负责后端开发",
            "model": _model_selection(supports_image_input=False),
        }
    )

    content = result["messages"][0].content
    assert isinstance(content, list)
    assert "[jd_text]\n岗位职责：负责后端开发" in content[0]["text"]


def test_prepare_jd_source_uses_image_blocks_for_vision_model() -> None:
    agent = JdAnalyzerAgent()

    result = agent._prepare_jd_source_node(
        {
            "jd_text": "任职要求：熟悉 Python。",
            "source_url": "https://example.com/jobs/123",
            "images": [_IMAGE_DATA_URL],
            "messages": [HumanMessage(content="请分析这个岗位。")],
            "model": _model_selection(supports_image_input=True),
        }
    )

    content = result["messages"][0].content
    assert isinstance(content, list)
    assert "https://example.com/jobs/123" in content[0]["text"]
    assert "任职要求：熟悉 Python。" in content[0]["text"]
    assert content[1] == {
        "type": "image_url",
        "image_url": {"url": _IMAGE_DATA_URL},
    }


def test_prepare_jd_source_ocr_images_for_text_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_images: list[str] = []

    def fake_extract_image_data_url_ocr(data_url: str) -> str:
        seen_images.append(data_url)
        return "OCR 岗位职责：负责后端开发。"

    monkeypatch.setattr(
        jd_agent_module.document_parser,
        "extract_image_data_url_ocr",
        fake_extract_image_data_url_ocr,
    )

    result = JdAnalyzerAgent()._prepare_jd_source_node(
        {
            "images": [_IMAGE_DATA_URL],
            "model": _model_selection(supports_image_input=False),
        }
    )

    content = result["messages"][0].content
    assert isinstance(content, list)
    assert seen_images == [_IMAGE_DATA_URL]
    assert all(block["type"] == "text" for block in content)
    assert "OCR 岗位职责：负责后端开发。" in content[1]["text"]


async def test_get_jd_source_tools_includes_marker_tools_when_web_fetch_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_tools(*names, config):
        return []

    monkeypatch.setattr(jd_agent_module, "get_tools", fake_get_tools)

    tools = await jd_agent_module._get_jd_source_tools(None)

    assert [tool.name for tool in tools] == [
        "mark_jd_extraction_success",
        "mark_jd_extraction_failure",
    ]


async def test_web_search_tools_can_be_awaited_repeatedly_with_cached_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def fake_load_web_search_tools(config: Config):
        nonlocal calls
        calls += 1
        return [fake_get_content]

    web_search_module.get_web_search_tools.cache_clear()
    monkeypatch.setattr(
        web_search_module,
        "_load_web_search_tools",
        fake_load_web_search_tools,
    )

    config = Config(exa_api_key="test-key")
    first = await web_search_module.get_web_search_tools(config)
    second = await web_search_module.get_web_search_tools(config)

    assert calls == 1
    assert first == second == [fake_get_content]

    web_search_module.get_web_search_tools.cache_clear()


async def test_web_search_tools_concurrent_first_load_is_shared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def fake_load_web_search_tools(config: Config):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return [fake_get_content]

    web_search_module.get_web_search_tools.cache_clear()
    monkeypatch.setattr(
        web_search_module,
        "_load_web_search_tools",
        fake_load_web_search_tools,
    )

    config = Config(exa_api_key="test-key")
    results = await asyncio.gather(
        web_search_module.get_web_search_tools(config),
        web_search_module.get_web_search_tools(config),
        web_search_module.get_web_search_tools(config),
    )

    assert calls == 1
    assert results == [[fake_get_content], [fake_get_content], [fake_get_content]]

    web_search_module.get_web_search_tools.cache_clear()


async def test_get_jd_source_tools_can_be_called_repeatedly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def fake_get_tools(*names, config):
        nonlocal calls
        calls += 1
        return [fake_get_content]

    monkeypatch.setattr(jd_agent_module, "get_tools", fake_get_tools)

    first = await jd_agent_module._get_jd_source_tools(None)
    second = await jd_agent_module._get_jd_source_tools(None)

    assert calls == 2
    assert [tool.name for tool in first] == [
        "fake_get_content",
        "mark_jd_extraction_success",
        "mark_jd_extraction_failure",
    ]
    assert [tool.name for tool in second] == [tool.name for tool in first]


def test_parse_jd_text_extracts_success_tool_result_and_source_url() -> None:
    agent = JdAnalyzerAgent()
    state = {
        "source_url": "https://example.com/jobs/123",
        "messages": [
            HumanMessage(content="请分析这个岗位。"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "mark_jd_extraction_success",
                        "args": {"jd_text": "岗位职责：负责后端开发"},
                        "id": "call-success",
                    }
                ],
            ),
            ToolMessage(
                content="岗位职责：负责后端开发",
                tool_call_id="call-success",
                name="mark_jd_extraction_success",
            ),
        ]
    }

    result = agent._parse_jd_text_node(state)

    assert result["jd_text"] == "岗位职责：负责后端开发"
    assert result["source_url"] == "https://example.com/jobs/123"


def test_parse_jd_text_does_not_programmatically_extract_source_url() -> None:
    agent = JdAnalyzerAgent()
    state = {
        "messages": [
            HumanMessage(content="https://example.com/jobs/123"),
            ToolMessage(
                content="岗位职责：负责后端开发",
                tool_call_id="call-success",
                name="mark_jd_extraction_success",
            ),
        ]
    }

    result = agent._parse_jd_text_node(state)

    assert result["jd_text"] == "岗位职责：负责后端开发"
    assert result["source_url"] is None


def test_parse_jd_text_marks_failure_tool_result_as_terminal() -> None:
    agent = JdAnalyzerAgent()
    result = agent._parse_jd_text_node(
        {
            "messages": [
                ToolMessage(
                    content="not a JD",
                    tool_call_id="call-failure",
                    name="mark_jd_extraction_failure",
                )
            ]
        }
    )

    assert result["jd_text"] is None
    assert result["jd_error"] == "not a JD"
    assert agent._should_continue(result) == "end"


def test_parse_jd_text_rejects_plain_ai_response_without_marker_tool() -> None:
    agent = JdAnalyzerAgent()
    result = agent._parse_jd_text_node(
        {"messages": [AIMessage(content="岗位职责：负责后端开发")]}
    )

    assert result["jd_text"] is None
    assert result["jd_error"] == "JD extraction failed: missing marker tool call."
    assert agent._should_continue(result) == "end"


async def test_extract_facts_retries_and_preserves_original_block_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls_by_title: dict[str, int] = {}
    repair_attempts_by_title: dict[str, int] = {}

    class FakeExtractor:
        async def ainvoke(self, messages, *, max_repair_attempts=0):
            block_text = messages[-1].content
            title = next(
                candidate
                for candidate in ("第一", "第二", "第三")
                if candidate in block_text
            )
            calls_by_title[title] = calls_by_title.get(title, 0) + 1
            repair_attempts_by_title[title] = max_repair_attempts
            if title == "第二" and calls_by_title[title] == 1:
                raise RuntimeError("temporary model failure")
            return JdFactsEx(
                facts=[
                    JdFactEx(
                        fact_type="skill",
                        text=f"{title} fact",
                        evidence=block_text,
                        keywords=[title],
                    )
                ]
            )

    monkeypatch.setattr(
        jd_agent_module,
        "load_structured_model",
        lambda model_selection, schema: FakeExtractor(),
    )

    blocks = [
        JdRequirementBlockEx(
            block_type="must_have",
            title="第一",
            content="熟悉 Python。",
        ),
        JdRequirementBlockEx(
            block_type="must_have",
            title="第二",
            content="熟悉 FastAPI。",
        ),
        JdRequirementBlockEx(
            block_type="responsibility",
            title="第三",
            content="负责服务端开发。",
        ),
    ]
    extracted = JobDescriptionEx(
        job_title="后端开发工程师",
        primary_location="上海",
        locations=["上海", "杭州"],
        remote_policy_raw="不接受居家办公",
        employment_type_raw="全职",
        experience_raw="3年以上后端开发经验",
        years_experience_min=3,
        years_experience_max=5,
        education_raw="本科及以上",
        major_requirement="计算机相关专业",
        blocks=blocks,
    )

    result = await JdAnalyzerAgent()._extract_facts_node(
        {
            "jd_extracted": extracted,
            "blocks": blocks,
            "jd_text": "raw jd",
            "source_url": None,
            "model": None,
        }
    )

    job_description = result["job_description"]
    assert job_description is not None
    assert [block.title for block in job_description.blocks] == ["第一", "第二", "第三"]
    assert [block.facts[0].text for block in job_description.blocks] == [
        "第一 fact",
        "第二 fact",
        "第三 fact",
    ]
    assert job_description.primary_location == "上海"
    assert job_description.locations == ["上海", "杭州"]
    assert job_description.raw_text == "raw jd"
    assert job_description.remote_policy_raw == "不接受居家办公"
    assert job_description.employment_type_raw == "全职"
    assert job_description.experience_raw == "3年以上后端开发经验"
    assert job_description.years_experience_min == 3
    assert job_description.years_experience_max == 5
    assert job_description.education_raw == "本科及以上"
    assert job_description.education_min_rank == 2
    assert job_description.major_requirement == "计算机相关专业"
    assert calls_by_title["第二"] == 2
    assert repair_attempts_by_title == {"第一": 2, "第二": 2, "第三": 2}
