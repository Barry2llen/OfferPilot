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

    id: int = Field(description="JD 分析记录 ID。", examples=[1])
    status: JobDescriptionAnalysisStatus = Field(description="分析状态。", examples=["parsed"])
    source_url: str | None = Field(default=None, description="JD 来源 URL。", examples=["https://example.com/jobs/123"])
    source_image_file_ids: list[str] = Field(default_factory=list, description="用于分析的文件库图片 ID。", examples=[["A1B2C3"]])
    summary: str | None = Field(default=None, description="JD 原文摘要。", examples=["负责后端服务开发，熟悉 Python。"])
    error_message: str | None = Field(default=None, description="失败原因。", examples=["Model call failed."])
    model_selection_id: int | None = Field(default=None, description="用于分析的模型选择 ID。", examples=[1])
    job_title: str | None = Field(default=None, description="职位名称。", examples=["后端开发工程师"])
    company_name: str | None = Field(default=None, description="公司名称。", examples=["示例科技"])
    primary_location: str | None = Field(default=None, description="主要工作地点。", examples=["上海"])
    block_count: int = Field(description="需求块数量。", examples=[2])
    fact_count: int = Field(description="事实数量。", examples=[8])
    created_at: datetime = Field(description="记录创建时间。", examples=["2026-05-13T18:00:00"])
    updated_at: datetime = Field(description="记录更新时间。", examples=["2026-05-13T18:01:00"])
    completed_at: datetime | None = Field(default=None, description="分析完成时间。", examples=["2026-05-13T18:01:00"])


class JobDescriptionAnalysisDetail(JobDescriptionAnalysisListItem):
    raw_text: str = Field(description="用于分析的 JD 原文。", examples=["岗位职责：负责后端服务开发。"])
    result: JobDescription | None = Field(default=None, description="结构化 JD 分析结果。")


__all__ = [
    "JobDescriptionAnalysisDetail",
    "JobDescriptionAnalysisListItem",
    "JobDescriptionAnalysisStatus",
]
