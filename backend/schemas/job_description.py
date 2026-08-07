from __future__ import annotations

import re
from typing import Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


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


def _empty_to_none(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _to_non_negative_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        if value.is_integer() and value >= 0:
            return int(value)
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdecimal():
            parsed = int(stripped)
            return parsed if parsed >= 0 else None
    return None


_EDUCATION_RANK_BY_LEGACY_VALUE = {
    "college": 1,
    "bachelor": 2,
    "master": 3,
    "phd": 4,
}


def _normalize_education_min_rank(value: object, raw: str | None = None) -> int | None:
    explicit_rank = _to_non_negative_int(value)
    if explicit_rank is not None:
        return explicit_rank if 1 <= explicit_rank <= 4 else None

    for candidate in (value, raw):
        if not isinstance(candidate, str):
            continue
        text = candidate.strip().lower()
        if not text:
            continue
        if text in _EDUCATION_RANK_BY_LEGACY_VALUE:
            return _EDUCATION_RANK_BY_LEGACY_VALUE[text]
        if "不限" in text or "无要求" in text:
            return None
        if "大专" in text or "专科" in text or "college" in text:
            return 1
        if "本科" in text or "学士" in text or "bachelor" in text:
            return 2
        if "硕士" in text or "研究生" in text or "master" in text:
            return 3
        if "博士" in text or "phd" in text or "doctor" in text:
            return 4
    return None


def _normalize_experience_bounds(
    years_min: object,
    years_max: object,
    raw: str | None = None,
) -> tuple[int | None, int | None]:
    normalized_min = _to_non_negative_int(years_min)
    normalized_max = _to_non_negative_int(years_max)

    if raw:
        text = raw.strip()
        if "不限" in text or "经验不限" in text:
            normalized_min = normalized_min if normalized_min is not None else None
            normalized_max = normalized_max if normalized_max is not None else None
        elif "应届" in text or "无经验" in text:
            normalized_min = 0 if normalized_min is None else normalized_min
        else:
            range_match = re.search(r"(\d+)\s*(?:-|~|－|—|至|到)\s*(\d+)\s*年", text)
            if range_match:
                normalized_min = int(range_match.group(1))
                normalized_max = int(range_match.group(2))
            else:
                min_match = re.search(
                    r"(?:至少|不少于|不低于)?\s*(\d+)\s*(?:年\s*(?:以上|及以上)|\+\s*年?|\+)",
                    text,
                )
                if min_match:
                    normalized_min = int(min_match.group(1))
                elif normalized_min is None:
                    bare_match = re.search(
                        r"(\d+)\s*年(?:经验|工作经验|开发经验)?", text
                    )
                    if bare_match:
                        normalized_min = int(bare_match.group(1))

    if (
        normalized_min is not None
        and normalized_max is not None
        and normalized_max < normalized_min
    ):
        normalized_max = None
    return normalized_min, normalized_max


def _apply_legacy_jd_field_aliases(data: object) -> object:
    if not isinstance(data, dict):
        return data
    data = dict(data)
    if "remote_policy_raw" not in data and "remote_policy" in data:
        data["remote_policy_raw"] = data.pop("remote_policy")
    else:
        data.pop("remote_policy", None)
    if "employment_type_raw" not in data and "employment_type" in data:
        data["employment_type_raw"] = data.pop("employment_type")
    else:
        data.pop("employment_type", None)
    if "education_min_rank" not in data and "education_min" in data:
        data["education_min_rank"] = data.pop("education_min")
    else:
        data.pop("education_min", None)
    data.pop("experience_level", None)
    return data


def _apply_llm_jd_field_aliases(data: object) -> object:
    data = _apply_legacy_jd_field_aliases(data)
    if not isinstance(data, dict):
        return data
    data = dict(data)
    salary = data.pop("salary", None)
    if isinstance(salary, dict):
        data.setdefault("salary_raw", salary.get("raw"))
        data.setdefault("salary_min_monthly", salary.get("min_monthly"))
        data.setdefault("salary_max_monthly", salary.get("max_monthly"))
        data.setdefault("salary_months_per_year", salary.get("months_per_year"))
        data.setdefault("salary_currency", salary.get("currency"))
    return data


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

type JdFactType = str

type JdFactImportance = Literal[
    "must_have",
    "nice_to_have",
    "responsibility",
    "unknown",
]

# ---- Ex 后缀：LLM 直接产出的结构 ----


class JdFactEx(JdLlmOutputModel):
    """A specific fact extracted from a JD block, symmetric to ResumeFactEx for matching."""

    block_id: str = Field(
        description="Stable ID of the flat JD block row this fact belongs to.",
        examples=["block_1"],
    )
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

    block_id: str = Field(
        description="Stable ID for this flat JD block row. Facts must refer to this value.",
        examples=["block_1"],
    )
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
        description="Original salary string, e.g. '25-40K per month with 15 payments'.",
        examples=["25-40K·15薪"],
    )
    min_monthly: float | None = Field(
        default=None,
        description="Minimum monthly base in thousands of currency units (k).",
        examples=[25],
    )
    max_monthly: float | None = Field(
        default=None,
        description="Maximum monthly base in thousands of currency units (k).",
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
        description="Original salary string, e.g. '25-40K per month with 15 payments'.",
        examples=["25-40K·15薪"],
    )
    min_monthly: float | None = Field(
        default=None,
        description="Minimum monthly base in thousands of currency units (k).",
        examples=[25],
    )
    max_monthly: float | None = Field(
        default=None,
        description="Maximum monthly base in thousands of currency units (k).",
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
        description="Company size description, e.g. '500-1000 employees'.",
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
    remote_policy_raw: str | None = Field(
        default=None,
        validation_alias=AliasChoices("remote_policy_raw", "remote_policy"),
        description="Original remote work policy text as written in the JD.",
        examples=["不接受居家办公"],
    )
    employment_type_raw: str | None = Field(
        default=None,
        validation_alias=AliasChoices("employment_type_raw", "employment_type"),
        description="Original employment type text as written in the JD.",
        examples=["全职"],
    )

    # Experience & education
    experience_raw: str | None = Field(
        default=None,
        description="Original experience requirement text, e.g. '3+ years', '1-3 years', or 'open to new graduates'.",
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
    education_raw: str | None = Field(
        default=None,
        description="Original education requirement text, e.g. 'bachelor degree or above' or 'computer science preferred'.",
        examples=["本科及以上，计算机相关专业优先"],
    )
    education_min_rank: int | None = Field(
        default=None,
        description=(
            "Local normalized minimum education rank when safely known: "
            "1=college, 2=bachelor, 3=master, 4=phd."
        ),
        examples=[2],
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

    @model_validator(mode="before")
    @classmethod
    def _map_legacy_fields(cls, data: object) -> object:
        return _apply_legacy_jd_field_aliases(data)

    @field_validator(
        "remote_policy_raw",
        "employment_type_raw",
        "experience_raw",
        "education_raw",
        "major_requirement",
        mode="before",
    )
    @classmethod
    def _normalize_optional_text(cls, value: object) -> object:
        return _empty_to_none(value)

    @field_validator("education_min_rank", mode="before")
    @classmethod
    def _normalize_education_rank_input(cls, value: object) -> object:
        return _normalize_education_min_rank(value)

    @model_validator(mode="after")
    def _normalize_comparable_fields(self) -> JobDescriptionFields:
        years_min, years_max = _normalize_experience_bounds(
            self.years_experience_min,
            self.years_experience_max,
            self.experience_raw,
        )
        self.years_experience_min = years_min
        self.years_experience_max = years_max
        self.education_min_rank = _normalize_education_min_rank(
            self.education_min_rank,
            self.education_raw,
        )
        return self


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
        description="Company size description, e.g. '500-1000 employees'.",
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
    remote_policy_raw: str | None = Field(
        default=None,
        validation_alias=AliasChoices("remote_policy_raw", "remote_policy"),
        description="Original remote work policy text as written in the JD.",
        examples=["不接受居家办公"],
    )
    employment_type_raw: str | None = Field(
        default=None,
        validation_alias=AliasChoices("employment_type_raw", "employment_type"),
        description="Original employment type text as written in the JD.",
        examples=["全职"],
    )

    # Experience & education
    experience_raw: str | None = Field(
        default=None,
        validation_alias=AliasChoices("experience_raw", "experience"),
        description="Original experience requirement text, e.g. '3+ years', '1-3 years', or 'open to new graduates'.",
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
    education_raw: str | None = Field(
        default=None,
        validation_alias=AliasChoices("education_raw", "education"),
        description="Original education requirement text, e.g. 'bachelor degree or above' or 'computer science preferred'.",
        examples=["本科及以上，计算机相关专业优先"],
    )
    education_min_rank: int | None = Field(
        default=None,
        validation_alias=AliasChoices("education_min_rank", "education_min"),
        description=(
            "Local normalized minimum education rank when safely known: "
            "1=college, 2=bachelor, 3=master, 4=phd."
        ),
        examples=[2],
    )
    major_requirement: str | None = Field(
        default=None,
        description="Major or discipline requirement mentioned in the JD.",
        examples=["计算机、软件工程或相关专业"],
    )

    # Compensation & benefits
    salary_raw: str = Field(
        default="",
        description="Original salary string, e.g. '25-40K per month with 15 payments'.",
        examples=["25-40K·15薪"],
    )
    salary_min_monthly: float | None = Field(
        default=None,
        description="Minimum monthly base in thousands of currency units (k).",
        examples=[25],
    )
    salary_max_monthly: float | None = Field(
        default=None,
        description="Maximum monthly base in thousands of currency units (k).",
        examples=[40],
    )
    salary_months_per_year: float | None = Field(
        default=None,
        description="Months paid per year, e.g. 13, 14, 15.",
        examples=[15],
    )
    salary_currency: str | None = Field(
        default=None,
        description="Salary currency code when available.",
        examples=["CNY"],
    )
    benefits: list[str] = Field(
        default_factory=list,
        description="List of benefits mentioned.",
        examples=[["五险一金", "年终奖"]],
    )
    blocks: list[JdRequirementBlockEx] = Field(
        default_factory=list,
        description="Flat requirement/responsibility block rows from the JD.",
    )

    @model_validator(mode="before")
    @classmethod
    def _map_legacy_fields(cls, data: object) -> object:
        return _apply_llm_jd_field_aliases(data)

    @field_validator(
        "remote_policy_raw",
        "employment_type_raw",
        "experience_raw",
        "education_raw",
        "major_requirement",
        "salary_currency",
        mode="before",
    )
    @classmethod
    def _normalize_optional_text(cls, value: object) -> object:
        return _empty_to_none(value)

    @field_validator("education_min_rank", mode="before")
    @classmethod
    def _normalize_education_rank_input(cls, value: object) -> object:
        return _normalize_education_min_rank(value)

    @model_validator(mode="after")
    def _normalize_comparable_fields(self) -> JobDescriptionEx:
        years_min, years_max = _normalize_experience_bounds(
            self.years_experience_min,
            self.years_experience_max,
            self.experience_raw,
        )
        self.years_experience_min = years_min
        self.years_experience_max = years_max
        self.education_min_rank = _normalize_education_min_rank(
            self.education_min_rank,
            self.education_raw,
        )
        return self


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

    @field_validator("fact_type", mode="before")
    @classmethod
    def _normalize_fact_type(cls, value: object) -> object:
        return _fallback_if_empty(value, "other")


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
]
