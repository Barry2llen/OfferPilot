import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.constants import END

from agent.agents.jd_analyzer import agent as jd_agent_module
from agent.agents.jd_analyzer import JdAnalyzerAgent
from schemas.model_provider import ModelProvider
from schemas.model_selection import ModelSelection
from schemas.job_description import (
    JdFactEx,
    JdFactsEx,
    JdRequirementBlockEx,
    JobDescriptionEx,
)


_IMAGE_DATA_URL = "data:image/png;base64,ZmFrZS1pbWFnZQ=="


def _model_selection(*, supports_image_input: bool) -> ModelSelection:
    return ModelSelection(
        provider=ModelProvider(provider="OpenAI", name="default-openai"),
        model_name="gpt-4o-mini",
        supports_image_input=supports_image_input,
    )


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
    assert agent._should_continue(result) == "end"


def test_parse_jd_text_rejects_plain_ai_response_without_marker_tool() -> None:
    agent = JdAnalyzerAgent()
    result = agent._parse_jd_text_node(
        {"messages": [AIMessage(content="岗位职责：负责后端开发")]}
    )

    assert result["jd_text"] is None
    assert agent._should_continue(result) == "end"


async def test_extract_facts_retries_and_preserves_original_block_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls_by_title: dict[str, int] = {}

    class FakeExtractor:
        async def ainvoke(self, messages):
            block_text = messages[-1].content
            title = next(
                candidate
                for candidate in ("第一", "第二", "第三")
                if candidate in block_text
            )
            calls_by_title[title] = calls_by_title.get(title, 0) + 1
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
    assert job_description.experience_raw == "3年以上后端开发经验"
    assert job_description.years_experience_min == 3
    assert job_description.years_experience_max == 5
    assert job_description.education_raw == "本科及以上"
    assert job_description.major_requirement == "计算机相关专业"
    assert calls_by_title["第二"] == 2
