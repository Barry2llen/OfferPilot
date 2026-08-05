from datetime import datetime
import inspect

import pytest
from langgraph.constants import END, START

import agent.agents.resume_extractor.agent as resume_agent_module
from agent.agents.resume_extractor import ResumeExtractorAgent
from agent.agents.resume_extractor.model import TextValidation
from agent.agents.resume_extractor.prompt import (
    facts_extraction_system_prompt,
    section_extraction_system_prompt,
)
from schemas.config import Config
from schemas.resume import ResumeFactEx, ResumeFacts, ResumeSectionEx, ResumeSections
from schemas.resume_document import ResumeDocument


class RecordingExtractor:
    def __init__(self, result: object) -> None:
        self.result = result
        self.ainvoke_calls: list[dict[str, object]] = []

    def invoke(self, _messages: object) -> object:
        raise AssertionError("Structured extraction should use ainvoke")

    async def ainvoke(
        self,
        messages: object,
        *,
        max_repair_attempts: int = 0,
    ) -> object:
        self.ainvoke_calls.append(
            {"messages": messages, "max_repair_attempts": max_repair_attempts}
        )
        return self.result


class RecordingStructuredModelLoader:
    def __init__(self, extractor: RecordingExtractor) -> None:
        self.extractor = extractor
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        model_selection: object,
        schema: object,
        *,
        method: object = None,
    ) -> RecordingExtractor:
        self.calls.append(
            {
                "model_selection": model_selection,
                "schema": schema,
                "method": method,
            }
        )
        return self.extractor


class FakeResumeDocument:
    def extract_text(self) -> str:
        return "resume text"

    def convert_resume_to_image_base64(self) -> list[str]:
        return []

    def extract_text_ocr(self) -> str:
        raise AssertionError("OCR should not be used for valid extracted text")


def test_resume_extractor_graph_has_expected_nodes_and_edges() -> None:
    graph = ResumeExtractorAgent().get_graph()

    assert set(graph.nodes) == {"set_up", "extract_section", "extract_facts"}
    assert graph.edges == {
        (START, "set_up"),
        ("set_up", "extract_section"),
        ("extract_section", "extract_facts"),
        ("extract_facts", END),
    }


def test_resume_extractor_graph_can_compile() -> None:
    compiled_graph = ResumeExtractorAgent().get_agent()

    assert compiled_graph is not None


def test_set_up_node_remains_async_after_require_fields_decoration() -> None:
    assert inspect.iscoroutinefunction(ResumeExtractorAgent()._set_up_node)


def test_resume_extractor_prompts_are_structured_and_grounded() -> None:
    assert "ResumeSections" in section_extraction_system_prompt
    assert "section_id" in section_extraction_system_prompt
    assert "Do not" in section_extraction_system_prompt
    assert "Preserve the original" in section_extraction_system_prompt

    assert "ResumeFacts" in facts_extraction_system_prompt
    assert "section_id" in facts_extraction_system_prompt
    assert "fact_type" in facts_extraction_system_prompt
    assert "evidence" in facts_extraction_system_prompt
    assert "Use only the input section" in facts_extraction_system_prompt


async def test_set_up_node_uses_structured_ainvoke(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extractor = RecordingExtractor(TextValidation(is_valid=True, reason="ok"))
    loader = RecordingStructuredModelLoader(extractor)

    monkeypatch.setattr(
        resume_agent_module,
        "load_structured_model",
        loader,
    )

    model_selection = object()
    result = await ResumeExtractorAgent(
        config=Config(model_call_retry_attempts=4)
    )._set_up_node(
        {
            "resume_document": FakeResumeDocument(),
            "model": model_selection,
        }
    )

    assert result["resume_text"] == "resume text"
    assert result["resume_images"] == []
    assert loader.calls == [
        {
            "model_selection": model_selection,
            "schema": TextValidation,
            "method": resume_agent_module.RESUME_STRUCTURED_OUTPUT_METHOD,
        }
    ]
    assert extractor.ainvoke_calls[0]["max_repair_attempts"] == 3


async def test_compiled_graph_executes_decorated_async_set_up_node(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extractor = RecordingExtractor(TextValidation(is_valid=True, reason="ok"))
    loader = RecordingStructuredModelLoader(extractor)

    monkeypatch.setattr(
        resume_agent_module,
        "load_structured_model",
        loader,
    )

    graph = ResumeExtractorAgent(
        config=Config(model_call_retry_attempts=4)
    ).get_compiled_graph(interrupt_after=["set_up"])

    result = await graph.ainvoke(
        {
            "resume_document": FakeResumeDocument(),
            "model": object(),
            "messages": [],
        },
        {"recursion_limit": 20},
    )

    assert result["resume_text"] == "resume text"
    assert result["resume_images"] == []
    assert extractor.ainvoke_calls[0]["max_repair_attempts"] == 3


async def test_extract_section_node_uses_structured_ainvoke(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extractor = RecordingExtractor(
        ResumeSections(
            sections=[
                ResumeSectionEx(
                    section_id="section_1",
                    title="技能",
                    content="Python",
                )
            ]
        )
    )
    loader = RecordingStructuredModelLoader(extractor)

    monkeypatch.setattr(
        resume_agent_module,
        "load_structured_model",
        loader,
    )

    model_selection = object()
    result = await ResumeExtractorAgent(
        config=Config(model_call_retry_attempts=2)
    )._extract_section_node(
        {
            "resume_text": "resume text",
            "model": model_selection,
        }
    )

    assert result["sections"][0].title == "技能"
    assert loader.calls == [
        {
            "model_selection": model_selection,
            "schema": ResumeSections,
            "method": resume_agent_module.RESUME_STRUCTURED_OUTPUT_METHOD,
        }
    ]
    assert extractor.ainvoke_calls[0]["max_repair_attempts"] == 1


async def test_extract_facts_node_uses_structured_ainvoke(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extractor = RecordingExtractor(
        ResumeFacts(
            facts=[
                ResumeFactEx(
                    section_id="section_1",
                    fact_type="skill",
                    text="Python",
                    evidence="Python",
                    keywords=["Python"],
                )
            ]
        )
    )
    loader = RecordingStructuredModelLoader(extractor)

    monkeypatch.setattr(
        resume_agent_module,
        "load_structured_model",
        loader,
    )

    model_selection = object()
    result = await ResumeExtractorAgent(
        config=Config(model_call_retry_attempts=5)
    )._extract_facts_node(
        {
            "sections": [
                ResumeSectionEx(
                    section_id="section_1",
                    title="技能",
                    content="Python",
                )
            ],
            "resume_text": "resume text",
            "resume_document": ResumeDocument(
                id=1,
                upload_time=datetime(2026, 1, 1),
                has_file=False,
            ),
            "model": model_selection,
        }
    )

    assert result["resume"].sections[0].facts[0].text == "Python"
    assert not hasattr(result["resume"].sections[0], "section_id")
    assert loader.calls == [
        {
            "model_selection": model_selection,
            "schema": ResumeFacts,
            "method": resume_agent_module.RESUME_STRUCTURED_OUTPUT_METHOD,
        }
    ]
    assert extractor.ainvoke_calls[0]["max_repair_attempts"] == 4
