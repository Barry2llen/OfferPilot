from langgraph.constants import END, START

from agent.agents.resume_extractor import ResumeExtractorAgent
from agent.agents.resume_extractor.prompt import (
    facts_extraction_system_prompt,
    section_extraction_system_prompt,
)


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


def test_resume_extractor_prompts_are_structured_and_grounded() -> None:
    assert "ResumeSections" in section_extraction_system_prompt
    assert "Do not" in section_extraction_system_prompt
    assert "Preserve the original" in section_extraction_system_prompt

    assert "ResumeFacts" in facts_extraction_system_prompt
    assert "fact_type" in facts_extraction_system_prompt
    assert "evidence" in facts_extraction_system_prompt
    assert "Use only the input section" in facts_extraction_system_prompt
