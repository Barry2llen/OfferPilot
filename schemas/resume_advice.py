from pydantic import BaseModel, ConfigDict, Field


class ResumeAdviceRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "model_selection_id": 1,
                    "user_prompt": "请重点从项目表述、量化成果和岗位匹配度三个方面给建议。",
                }
            ]
        }
    )

    model_selection_id: int = Field(
        description="用于生成建议的模型配置 ID，必须引用已存在且支持图片输入的模型。",
        examples=[1],
    )
    user_prompt: str | None = Field(
        default=None,
        description="附加优化要求，会与简历内容一并发送给模型。",
        examples=["请重点从项目表述、量化成果和岗位匹配度三个方面给建议。"],
    )


class ResumeAdviceResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "resume_id": 1,
                    "model_selection_id": 1,
                    "content": "建议补充项目结果的量化指标，并将技能栈前置到更显眼的位置。",
                }
            ]
        }
    )

    resume_id: int = Field(description="被分析的简历记录 ID。", examples=[1])
    model_selection_id: int = Field(
        description="本次生成所使用的模型配置 ID。",
        examples=[1],
    )
    content: str = Field(
        description="模型最终整合后的完整简历优化建议文本。",
        examples=["建议补充项目结果的量化指标，并将技能栈前置到更显眼的位置。"],
    )


__all__ = ["ResumeAdviceRequest", "ResumeAdviceResponse"]
