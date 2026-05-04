from datetime import datetime

import pytest
from pydantic import ValidationError

from schemas.resume import (
    Resume,
    ResumeFactEx,
    ResumeFacts,
    ResumeSectionEx,
    ResumeSections,
)
from schemas.resume_document import ResumeDocument


def _build_resume_payload() -> dict:
    return {
        "raw_text": "张三\n高级后端开发工程师\nPython, FastAPI",
        "document": _build_document_payload(),
        "sections": [
            {
                "title": "技能",
                "content": "Python, FastAPI",
                "facts": [
                    {
                        "fact_type": "skill",
                        "text": "Python",
                        "evidence": "Python, FastAPI",
                        "keywords": ["Python"],
                    }
                ],
            }
        ],
    }


def _build_document_payload() -> dict:
    return {
        "id": 1,
        "file_path": "data/resumes/sample.pdf",
        "upload_time": "2026-04-18T17:00:00",
        "original_filename": "sample.pdf",
        "media_type": "application/pdf",
        "has_file": True,
        "preview_url": "/resumes/1/file",
    }


def test_resume_can_initialize_with_document_and_default_text_sections() -> None:
    document = ResumeDocument(
        id=1,
        file_path="data/resumes/sample.pdf",
        upload_time=datetime(2026, 4, 18, 17, 0, 0),
        original_filename="sample.pdf",
        media_type="application/pdf",
        has_file=True,
        preview_url="/resumes/1/file",
    )

    resume = Resume(document=document)

    assert resume.raw_text == ""
    assert resume.sections == []
    assert resume.document == document


def test_resume_can_round_trip_complete_payload() -> None:
    payload = _build_resume_payload()

    resume = Resume.model_validate(payload)
    restored = Resume.model_validate(resume.model_dump())

    assert restored.model_dump() == resume.model_dump()
    assert restored.raw_text.startswith("张三")
    assert restored.sections[0].title == "技能"
    assert restored.sections[0].facts[0].fact_type == "skill"
    assert restored.sections[0].facts[0].keywords == ["Python"]


def test_resume_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Resume.model_validate({"unknown_field": "unexpected"})


def test_resume_sections_schema_round_trips_llm_output_shape() -> None:
    sections = ResumeSections.model_validate(
        {
            "sections": [
                {
                    "title": "项目经历",
                    "content": "负责规则服务抽象设计与核心 API 开发",
                }
            ]
        }
    )

    assert sections.sections == [
        ResumeSectionEx(
            title="项目经历",
            content="负责规则服务抽象设计与核心 API 开发",
        )
    ]


def test_resume_facts_schema_round_trips_llm_output_shape() -> None:
    facts = ResumeFacts.model_validate(
        {
            "facts": [
                {
                    "fact_type": "achievement",
                    "text": "接口平均延迟下降 35%",
                    "evidence": "接口平均延迟下降 35%",
                    "keywords": ["延迟", "35%"],
                }
            ]
        }
    )

    assert facts.facts == [
        ResumeFactEx(
            fact_type="achievement",
            text="接口平均延迟下降 35%",
            evidence="接口平均延迟下降 35%",
            keywords=["延迟", "35%"],
        )
    ]


def test_resume_json_schema_contains_nested_sections_and_facts() -> None:
    schema = Resume.model_json_schema()

    assert schema["properties"]["sections"]["items"]["$ref"].endswith("ResumeSection")

    section_schema = schema["$defs"]["ResumeSection"]
    fact_schema = schema["$defs"]["ResumeFact"]

    assert section_schema["properties"]["facts"]["items"]["$ref"].endswith("ResumeFact")
    assert "The type of fact" in fact_schema["properties"]["fact_type"]["description"]
