from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from schemas.job_description import JobDescription


type JobDescriptionAnalysisStatus = Literal["processing", "parsed", "failed"]


class JobDescriptionAnalysisListItem(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": 1,
                    "status": "parsed",
                    "source_url": "https://example.com/jobs/123",
                    "source_image_file_ids": ["A1B2C3"],
                    "summary": "负责后端服务开发，熟悉 Python。",
                    "error_message": None,
                    "model_selection_id": 1,
                    "job_title": "后端开发工程师",
                    "company_name": "示例科技",
                    "primary_location": "上海",
                    "block_count": 2,
                    "fact_count": 8,
                    "created_at": "2026-05-13T18:00:00",
                    "updated_at": "2026-05-13T18:01:00",
                    "completed_at": "2026-05-13T18:01:00",
                }
            ]
        }
    )

    id: int = Field(description="JD analysis record ID.", examples=[1])
    status: JobDescriptionAnalysisStatus = Field(description="Analysis status.", examples=["parsed"])
    source_url: str | None = Field(default=None, description="Source URL of the JD.", examples=["https://example.com/jobs/123"])
    source_image_file_ids: list[str] = Field(default_factory=list, description="File-library image IDs used for analysis.", examples=[["A1B2C3"]])
    summary: str | None = Field(default=None, description="Summary of the original JD text.", examples=["Build backend services with Python."])
    error_message: str | None = Field(default=None, description="Failure reason.", examples=["Model call failed."])
    model_selection_id: int | None = Field(default=None, description="Model selection ID used for analysis.", examples=[1])
    job_title: str | None = Field(default=None, description="Job title.", examples=["Backend Engineer"])
    company_name: str | None = Field(default=None, description="Company name.", examples=["Example Technologies"])
    primary_location: str | None = Field(default=None, description="Primary work location.", examples=["Shanghai"])
    block_count: int = Field(description="Number of requirement blocks.", examples=[2])
    fact_count: int = Field(description="Number of facts.", examples=[8])
    created_at: datetime = Field(description="Record creation time.", examples=["2026-05-13T18:00:00"])
    updated_at: datetime = Field(description="Record update time.", examples=["2026-05-13T18:01:00"])
    completed_at: datetime | None = Field(default=None, description="Analysis completion time.", examples=["2026-05-13T18:01:00"])


class JobDescriptionAnalysisDetail(JobDescriptionAnalysisListItem):
    raw_text: str = Field(description="Original JD text used for analysis.", examples=["Responsibilities: Build backend services."])
    result: JobDescription | None = Field(default=None, description="Structured JD analysis result.")


__all__ = [
    "JobDescriptionAnalysisDetail",
    "JobDescriptionAnalysisListItem",
    "JobDescriptionAnalysisStatus",
]
