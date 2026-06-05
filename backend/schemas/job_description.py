from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class JdSchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JdLlmOutputModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


def _fallback_if_empty(value: object, fallback: str) -> object:
    if value is None:
        return fallback
    if isinstance(value, str) and not value.strip():
        return fallback
    return value


# ---- 基础枚举 ----

type JdBlockType = Literal[
    "job_summary",
    "responsibility",
    "must_have",
    "nice_to_have",
    "benefit",
    "company_intro",
    "team_intro",
    "work_condition",
    "hiring_process",
    "other",
]

type JdFactType = Literal[
    "skill",
    "tool",
    "framework",
    "programming_language",
    "experience",
    "education",
    "major",
    "certificate",
    "language",
    "domain_knowledge",
    "soft_skill",
    "responsibility",
    "benefit",
    "work_condition",
    "company_info",
    "other",
]

type JdFactImportance = Literal[
    "must_have",
    "nice_to_have",
    "responsibility",
    "unknown",
]

type RemotePolicy = Literal["onsite", "hybrid", "remote", "unknown"]
type EmploymentType = Literal["full_time", "part_time", "intern", "contract", "unknown"]
type EducationLevel = Literal["college", "bachelor", "master", "phd", "unknown"]
type ExperienceLevel = Literal[
    "intern",
    "new_grad",
    "junior",
    "mid",
    "senior",
    "lead",
    "unknown",
]


# ---- Ex 后缀：LLM 直接产出的结构 ----


class JdFactEx(JdLlmOutputModel):
    """A specific fact extracted from a JD block, symmetric to ResumeFactEx for matching."""

    fact_type: JdFactType = Field(
        default="other",
        description="Normalized fact type for matching and downstream analysis.",
        examples=["skill"],
    )
    custom_fact_type: str | None = Field(
        default=None,
        description=(
            "Original or more specific fact type when fact_type is 'other', "
            "or when the model needs to preserve a nuanced category."
        ),
        examples=["distributed_system_experience"],
    )
    importance: JdFactImportance = Field(
        default="unknown",
        description=(
            "Importance of this fact in the JD. Put requirement strength here instead "
            "of only on the block, because one block may contain both must-have and nice-to-have items."
        ),
        examples=["must_have"],
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

    @field_validator("fact_type", mode="before")
    @classmethod
    def _normalize_fact_type(cls, value: object) -> object:
        return _fallback_if_empty(value, "other")

    @field_validator("importance", mode="before")
    @classmethod
    def _normalize_importance(cls, value: object) -> object:
        return _fallback_if_empty(value, "unknown")


class JdRequirementBlockEx(JdLlmOutputModel):
    """A semantically continuous block from a JD, preserving source text."""

    block_type: JdBlockType = Field(
        default="other",
        validation_alias=AliasChoices("block_type", "type"),
        description="Normalized block category.",
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

    @field_validator("block_type", mode="before")
    @classmethod
    def _normalize_block_type(cls, value: object) -> object:
        return _fallback_if_empty(value, "other")


class JdSalaryEx(JdLlmOutputModel):
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


class JdSalary(JdSchemaModel):
    """Strict salary information used by the final business JD model."""

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


class JobDescriptionFields(JdSchemaModel):
    """Common flat fields shared by LLM extraction output and final aggregated JD model."""

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
        description="Seniority level from the source or normalized by the model, e.g. P6, Senior, Lead.",
        examples=["Senior"],
    )
    job_family: str | None = Field(
        default=None,
        description="Job family, e.g. backend, frontend, data, ai, devops.",
        examples=["backend"],
    )

    # Work conditions
    primary_location: str | None = Field(
        default=None,
        description="Primary display location when the JD has one obvious main location.",
        examples=["上海"],
    )
    locations: list[str] = Field(
        default_factory=list,
        description="All work locations mentioned in the JD.",
        examples=[["北京", "上海", "深圳"]],
    )
    remote_policy: RemotePolicy = Field(
        default="unknown",
        description="Remote work policy.",
        examples=["hybrid"],
    )
    employment_type: EmploymentType = Field(
        default="unknown",
        description="Employment type.",
        examples=["full_time"],
    )

    # Experience & education
    experience_raw: str | None = Field(
        default=None,
        description="Original experience requirement text, e.g. '3年以上', '1-3年', '应届生可投'.",
        examples=["3年以上后端开发经验"],
    )
    years_experience_min: int | None = Field(
        default=None,
        description="Minimum years of experience required when it can be safely normalized.",
        examples=[3],
    )
    years_experience_max: int | None = Field(
        default=None,
        description="Maximum years of experience when explicitly mentioned.",
        examples=[5],
    )
    experience_level: ExperienceLevel = Field(
        default="unknown",
        description="Normalized experience level inferred from the JD.",
        examples=["mid"],
    )
    education_raw: str | None = Field(
        default=None,
        description="Original education requirement text, e.g. '本科及以上', '计算机相关专业优先'.",
        examples=["本科及以上，计算机相关专业优先"],
    )
    education_min: EducationLevel = Field(
        default="unknown",
        description="Minimum education requirement when it can be safely normalized.",
        examples=["bachelor"],
    )
    major_requirement: str | None = Field(
        default=None,
        description="Major or discipline requirement mentioned in the JD.",
        examples=["计算机、软件工程或相关专业"],
    )

    # Compensation & benefits
    salary: JdSalary | None = Field(
        default=None,
        description="Salary information.",
    )
    benefits: list[str] = Field(
        default_factory=list,
        description="List of benefits mentioned.",
        examples=[["五险一金", "年终奖"]],
    )


class JobDescriptionEx(JdLlmOutputModel):
    """Flat structured fields and text blocks extracted from a JD in one model call."""

    # Company & position
    company_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("company_name", "company"),
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
        validation_alias=AliasChoices("job_title", "title"),
        description="Position title, original wording.",
        examples=["后端开发工程师"],
    )
    job_level: str | None = Field(
        default=None,
        description="Seniority level from the source or normalized by the model, e.g. P6, Senior, Lead.",
        examples=["Senior"],
    )
    job_family: str | None = Field(
        default=None,
        description="Job family, e.g. backend, frontend, data, ai, devops.",
        examples=["backend"],
    )

    # Work conditions
    primary_location: str | None = Field(
        default=None,
        validation_alias=AliasChoices("primary_location", "location"),
        description="Primary display location when the JD has one obvious main location.",
        examples=["上海"],
    )
    locations: list[str] = Field(
        default_factory=list,
        description="All work locations mentioned in the JD.",
        examples=[["北京", "上海", "深圳"]],
    )
    remote_policy: RemotePolicy = Field(
        default="unknown",
        description="Remote work policy.",
        examples=["hybrid"],
    )
    employment_type: EmploymentType = Field(
        default="unknown",
        description="Employment type.",
        examples=["full_time"],
    )

    # Experience & education
    experience_raw: str | None = Field(
        default=None,
        validation_alias=AliasChoices("experience_raw", "experience"),
        description="Original experience requirement text, e.g. '3年以上', '1-3年', '应届生可投'.",
        examples=["3年以上后端开发经验"],
    )
    years_experience_min: int | None = Field(
        default=None,
        description="Minimum years of experience required when it can be safely normalized.",
        examples=[3],
    )
    years_experience_max: int | None = Field(
        default=None,
        description="Maximum years of experience when explicitly mentioned.",
        examples=[5],
    )
    experience_level: ExperienceLevel = Field(
        default="unknown",
        description="Normalized experience level inferred from the JD.",
        examples=["mid"],
    )
    education_raw: str | None = Field(
        default=None,
        validation_alias=AliasChoices("education_raw", "education"),
        description="Original education requirement text, e.g. '本科及以上', '计算机相关专业优先'.",
        examples=["本科及以上，计算机相关专业优先"],
    )
    education_min: EducationLevel = Field(
        default="unknown",
        description="Minimum education requirement when it can be safely normalized.",
        examples=["bachelor"],
    )
    major_requirement: str | None = Field(
        default=None,
        description="Major or discipline requirement mentioned in the JD.",
        examples=["计算机、软件工程或相关专业"],
    )

    # Compensation & benefits
    salary: JdSalaryEx | None = Field(
        default=None,
        description="Salary information.",
    )
    benefits: list[str] = Field(
        default_factory=list,
        description="List of benefits mentioned.",
        examples=[["五险一金", "年终奖"]],
    )
    blocks: list[JdRequirementBlockEx] = Field(
        default_factory=list,
        description="Requirement/responsibility blocks from the JD.",
    )

    @field_validator(
        "remote_policy",
        "employment_type",
        "experience_level",
        "education_min",
        mode="before",
    )
    @classmethod
    def _normalize_unknown_enum(cls, value: object) -> object:
        return _fallback_if_empty(value, "unknown")


class JdFactsEx(JdLlmOutputModel):
    """Container for facts extracted from a single JD block."""

    facts: list[JdFactEx] = Field(
        default_factory=list,
        description="List of extracted facts.",
    )


# ---- 不带 Ex 后缀：聚合后的最终结果 ----


class JdFact(JdSchemaModel):
    """A strict fact extracted from a JD block."""

    fact_type: JdFactType = Field(
        description="Normalized fact type for matching and downstream analysis.",
        examples=["skill"],
    )
    custom_fact_type: str | None = Field(
        default=None,
        description=(
            "Original or more specific fact type when fact_type is 'other', "
            "or when the model needs to preserve a nuanced category."
        ),
        examples=["distributed_system_experience"],
    )
    importance: JdFactImportance = Field(
        default="unknown",
        description=(
            "Importance of this fact in the JD. Put requirement strength here instead "
            "of only on the block, because one block may contain both must-have and nice-to-have items."
        ),
        examples=["must_have"],
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


class JdRequirementBlock(JdSchemaModel):
    """A strict semantically continuous block from a JD."""

    block_type: JdBlockType = Field(
        description="Normalized block category.",
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
    facts: list[JdFact] = Field(
        default_factory=list,
        description="Facts extracted from this JD block.",
    )


class JobDescription(JobDescriptionFields):
    """Aggregated JD model: raw text + flat fields + blocks with facts. Symmetric to Resume."""

    raw_text: str = Field(
        default="",
        description="Original JD text used for analysis. This remains the source of truth.",
        examples=["岗位职责：负责后端服务开发。任职要求：熟悉 Python。"],
    )
    source_url: str | None = Field(
        default=None,
        description="JD source URL for tracing.",
        examples=["https://example.com/jobs/123"],
    )
    blocks: list[JdRequirementBlock] = Field(
        default_factory=list,
        description="Structured JD blocks with extracted facts.",
    )


__all__ = [
    "JobDescription",
    "JobDescriptionEx",
    "JobDescriptionFields",
    "JdBlockType",
    "JdRequirementBlock",
    "JdRequirementBlockEx",
    "JdFact",
    "JdFactEx",
    "JdFactsEx",
    "JdFactImportance",
    "JdFactType",
    "JdSalary",
    "JdSalaryEx",
    "RemotePolicy",
    "EmploymentType",
    "EducationLevel",
    "ExperienceLevel",
]
