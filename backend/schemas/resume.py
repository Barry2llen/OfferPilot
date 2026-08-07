from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .resume_document import ResumeDocument


class ResumeSchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# Ex means extracted. Information extracted by LLMs.


class ResumeFactEx(ResumeSchemaModel):
    """A specific fact extracted from a resume section, such as a skill or project experience."""

    section_id: str = Field(
        description="Stable ID of the flat resume section row this fact belongs to.",
        examples=["section_1"],
    )

    fact_type: str = Field(
        description="The type of fact, such as skill, project, achievement, education, company, responsibility, certificate, or award."
    )

    text: str = Field(
        description="The extracted fact description, kept as close to the original text as possible."
    )

    evidence: str = Field(
        description="The original text snippet that supports this fact."
    )

    keywords: list[str] = Field(
        default_factory=list,
        description="Keywords related to this fact, including technical keywords, company names, job titles, and similar terms.",
    )


class ResumeSectionEx(ResumeSchemaModel):
    """A section split from a resume, such as education or work experience."""

    section_id: str = Field(
        description="Stable ID for this flat section row. Facts must refer to this value.",
        examples=["section_1"],
    )

    title: str = Field(
        description="The title of the resume section, such as Education or Work Experience.",
        examples=["教育经历"],
    )

    content: str = Field(
        description="The original text content of the resume section.",
        examples=["2015-2019 本科，计算机科学与技术，清华大学"],
    )


class ResumeFacts(ResumeSchemaModel):
    facts: list[ResumeFactEx] = Field(
        default_factory=list,
        description="Flat list of extracted facts from the resume.",
    )


class ResumeSections(ResumeSchemaModel):
    sections: list[ResumeSectionEx] = Field(
        default_factory=list,
        description="Flat list of extracted sections from the resume.",
    )


class ResumeFact(ResumeSchemaModel):
    """A final business resume fact nested under a section."""

    fact_type: str = Field(
        description="The type of fact, such as skill, project, achievement, education, company, responsibility, certificate, or award."
    )

    text: str = Field(
        description="The extracted fact description, kept as close to the original text as possible."
    )

    evidence: str = Field(
        description="The original text snippet that supports this fact."
    )

    keywords: list[str] = Field(
        default_factory=list,
        description="Keywords related to this fact, including technical keywords, company names, job titles, and similar terms.",
    )


class ResumeSection(ResumeSchemaModel):
    """A final business resume section with nested facts."""

    title: str = Field(
        description="The title of the resume section, such as Education or Work Experience.",
        examples=["教育经历"],
    )

    content: str = Field(
        description="The original text content of the resume section.",
        examples=["2015-2019 本科，计算机科学与技术，清华大学"],
    )

    facts: list[ResumeFact] = Field(default_factory=list)


class Resume(ResumeSchemaModel):
    raw_text: str = Field(default="")

    document: ResumeDocument = Field(default_factory=ResumeDocument)

    sections: list[ResumeSection] = Field(default_factory=list)


__all__ = [
    "Resume",
    "ResumeSection",
    "ResumeFact",
    "ResumeSectionEx",
    "ResumeFactEx",
    "ResumeFacts",
    "ResumeSections",
]
