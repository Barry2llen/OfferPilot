from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatAttachmentRef(BaseModel):
    file_id: str = Field(
        description="聊天文件短 ID。",
        examples=["A1B2C3"],
    )
    original_filename: str = Field(
        description="用户上传时的原始文件名。",
        examples=["portfolio.pdf"],
    )
    media_type: str | None = Field(
        default=None,
        description="文件媒体类型。",
        examples=["application/pdf"],
    )
    injection_mode: str = Field(
        description="该文件在当前线程中的注入模式：text、ocr_text 或 image。",
        examples=["image"],
    )


class ChatFileListItem(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "A1B2C3",
                    "original_filename": "notes.md",
                    "media_type": "text/markdown",
                    "size_bytes": 1280,
                    "created_at": "2026-05-13T18:00:00",
                    "reference_count": 2,
                    "raw_url": "/ai/files/A1B2C3/raw",
                }
            ]
        }
    )

    id: str = Field(description="聊天文件短 ID。", examples=["A1B2C3"])
    original_filename: str = Field(description="原始文件名。", examples=["notes.md"])
    media_type: str | None = Field(
        default=None,
        description="媒体类型。",
        examples=["text/markdown"],
    )
    size_bytes: int = Field(description="文件字节大小。", examples=[1280])
    created_at: datetime = Field(
        description="文件入库时间。",
        examples=["2026-05-13T18:00:00"],
    )
    reference_count: int = Field(
        description="当前被多少个线程引用。",
        examples=[2],
    )
    raw_url: str = Field(
        description="查看原始文件内容的接口路径。",
        examples=["/ai/files/A1B2C3/raw"],
    )


class ChatFileDetail(ChatFileListItem):
    pass


@dataclass(slots=True)
class StoredChatFile:
    path: str
    media_type: str | None
    filename: str
