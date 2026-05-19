from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class JdSchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---- Ex 后缀：LLM 直接产出的结构 ----

JdRequirementType = Literal[
    "must_have",
    "nice_to_have",
    "responsibility",
]


class JdFactEx(JdSchemaModel):
    """A specific fact extracted from a JD block, symmetric to ResumeFactEx for matching."""

    fact_type: str = Field(
        description=(
            "Fact type, e.g. skill, experience, education, certificate, "
            "language, domain_knowledge, soft_skill, responsibility, benefit."
        ),
        examples=["skill"],
    )
    text: str = Field(
        description="Fact text, kept close to the original wording.",
        examples=["熟悉 Python 和 FastAPI 开发。"],
    )
    evidence: str = Field(
        description="Original snippet from the JD that supports this fact.",
        examples=["熟悉 Python 和 FastAPI 开发，具备服务端项目经验。"],
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="Keywords including technologies, roles, tools, domains, certifications.",
        examples=[["Python", "FastAPI"]],
    )


class JdRequirementBlockEx(JdSchemaModel):
    """A semantically continuous block from a JD (responsibility / requirement / nice-to-have)."""

    block_type: JdRequirementType = Field(
        description="Block category.",
        examples=["must_have"],
    )
    title: str = Field(
        description="Short heading copied or minimally summarized from the source.",
        examples=["岗位职责"],
    )
    content: str = Field(
        description="Original text of the block.",
        examples=["负责后端核心服务开发与维护，参与系统架构设计。"],
    )


class JdSalaryEx(JdSchemaModel):
    """Structured salary information extracted from a JD."""

    raw: str = Field(
        default="",
        description="Original salary string, e.g. '25-40K·15薪'.",
        examples=["25-40K·15薪"],
    )
    min_monthly: float | None = Field(
        default=None,
        description="Minimum monthly base in 千元 (k).",
        examples=[25],
    )
    max_monthly: float | None = Field(
        default=None,
        description="Maximum monthly base in 千元 (k).",
        examples=[40],
    )
    months_per_year: float | None = Field(
        default=None,
        description="Months paid per year, e.g. 13, 14, 15.",
        examples=[15],
    )
    currency: str | None = Field(
        default=None,
        description="Salary currency code when available.",
        examples=["CNY"],
    )


class JobDescriptionEx(JdSchemaModel):
    """Flat structured fields extracted from a JD in one model call."""

    # Company & position
    company_name: str | None = Field(
        default=None,
        description="Company name.",
        examples=["示例科技有限公司"],
    )
    company_industry: str | None = Field(
        default=None,
        description="Industry of the company.",
        examples=["企业服务"],
    )
    company_size: str | None = Field(
        default=None,
        description="Company size description, e.g. '500-1000人'.",
        examples=["500-1000人"],
    )
    job_title: str = Field(
        default="",
        description="Position title, original wording.",
        examples=["后端开发工程师"],
    )
    job_level: str | None = Field(
        default=None,
        description="Seniority level, e.g. P6, Senior, Lead.",
        examples=["Senior"],
    )
    job_family: str | None = Field(
        default=None,
        description="Job family, e.g. backend, frontend, data, ai, devops.",
        examples=["backend"],
    )

    # Work conditions
    location: str | None = Field(
        default=None,
        description="Work location.",
        examples=["上海"],
    )
    remote_policy: Literal["onsite", "hybrid", "remote", "unknown"] = Field(
        default="unknown",
        description="Remote work policy.",
        examples=["hybrid"],
    )
    employment_type: Literal["full_time", "part_time", "intern", "contract", "unknown"] = Field(
        default="unknown",
        description="Employment type.",
        examples=["full_time"],
    )

    years_experience_min: int | None = Field(
        default=None,
        description="Minimum years of experience required.",
        examples=[3],
    )
    years_experience_max: int | None = Field(
        default=None,
        description="Maximum years of experience.",
        examples=[5],
    )
    education_min: Literal["college", "bachelor", "master", "phd", "unknown"] = Field(
        default="unknown",
        description="Minimum education requirement.",
        examples=["bachelor"],
    )

    salary: JdSalaryEx | None = Field(
        default=None,
        description="Salary information.",
    )
    benefits: list[str] = Field(
        default_factory=list,
        description="List of benefits mentioned.",
        examples=[["五险一金", "年终奖"]],
    )

    # Text blocks (preserving original text, symmetric to Resume sections)
    blocks: list[JdRequirementBlockEx] = Field(
        default_factory=list,
        description="Requirement/responsibility blocks from the JD.",
    )


class JdFactsEx(JdSchemaModel):
    """Container for facts extracted from a single JD block."""

    facts: list[JdFactEx] = Field(
        default_factory=list,
        description="List of extracted facts.",
    )


# ---- 不带 Ex 后缀：聚合后的最终结果 ----


class JdFact(JdFactEx):
    pass


class JdRequirementBlock(JdRequirementBlockEx):
    facts: list[JdFact] = Field(
        default_factory=list,
        description="Facts extracted from this JD block.",
    )


class JobDescription(JdSchemaModel):
    """Aggregated JD model: flat fields + blocks with facts. Symmetric to Resume."""

    raw_text: str = Field(
        default="",
        description="Original JD text used for analysis.",
        examples=["岗位职责：负责后端服务开发。任职要求：熟悉 Python。"],
    )
    source_url: str | None = Field(
        default=None,
        description="JD source URL for tracing.",
        examples=["https://example.com/jobs/123"],
    )

    # Flat fields
    company_name: str | None = Field(
        default=None,
        description="Company name.",
        examples=["示例科技有限公司"],
    )
    company_industry: str | None = Field(
        default=None,
        description="Industry of the company.",
        examples=["企业服务"],
    )
    company_size: str | None = Field(
        default=None,
        description="Company size description.",
        examples=["500-1000人"],
    )
    job_title: str = Field(
        default="",
        description="Position title, original wording.",
        examples=["后端开发工程师"],
    )
    job_level: str | None = Field(
        default=None,
        description="Seniority level.",
        examples=["Senior"],
    )
    job_family: str | None = Field(
        default=None,
        description="Job family.",
        examples=["backend"],
    )
    location: str | None = Field(
        default=None,
        description="Work location.",
        examples=["上海"],
    )
    remote_policy: Literal["onsite", "hybrid", "remote", "unknown"] = Field(
        default="unknown",
        description="Remote work policy.",
        examples=["hybrid"],
    )
    employment_type: Literal["full_time", "part_time", "intern", "contract", "unknown"] = Field(
        default="unknown",
        description="Employment type.",
        examples=["full_time"],
    )
    years_experience_min: int | None = Field(
        default=None,
        description="Minimum years of experience required.",
        examples=[3],
    )
    years_experience_max: int | None = Field(
        default=None,
        description="Maximum years of experience.",
        examples=[5],
    )
    education_min: Literal["college", "bachelor", "master", "phd", "unknown"] = Field(
        default="unknown",
        description="Minimum education requirement.",
        examples=["bachelor"],
    )
    salary: JdSalaryEx | None = Field(
        default=None,
        description="Salary information.",
    )
    benefits: list[str] = Field(
        default_factory=list,
        description="List of benefits mentioned.",
        examples=[["五险一金", "年终奖"]],
    )

    # Structured blocks + facts, symmetric to Resume.sections
    blocks: list[JdRequirementBlock] = Field(
        default_factory=list,
        description="Structured JD blocks with extracted facts.",
    )


__all__ = [
    "JobDescription",
    "JobDescriptionEx",
    "JdRequirementBlock",
    "JdRequirementBlockEx",
    "JdRequirementType",
    "JdFact",
    "JdFactEx",
    "JdFactsEx",
    "JdSalaryEx",
]
