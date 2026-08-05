from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatAttachmentRef(BaseModel):
    file_id: str = Field(
        description="Short ID of the chat file.",
        examples=["A1B2C3"],
    )
    original_filename: str = Field(
        description="Original filename supplied by the user.",
        examples=["portfolio.pdf"],
    )
    media_type: str | None = Field(
        default=None,
        description="File media type.",
        examples=["application/pdf"],
    )
    injection_mode: str = Field(
        description="Injection mode for this file in the current thread: text, ocr_text, or image.",
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

    id: str = Field(description="Short ID of the chat file.", examples=["A1B2C3"])
    original_filename: str = Field(description="Original filename.", examples=["notes.md"])
    media_type: str | None = Field(
        default=None,
        description="Media type.",
        examples=["text/markdown"],
    )
    size_bytes: int = Field(description="File size in bytes.", examples=[1280])
    created_at: datetime = Field(
        description="Time when the file was stored.",
        examples=["2026-05-13T18:00:00"],
    )
    reference_count: int = Field(
        description="Number of threads currently referencing the file.",
        examples=[2],
    )
    raw_url: str = Field(
        description="API path for viewing the original file content.",
        examples=["/ai/files/A1B2C3/raw"],
    )


class ChatFileDetail(ChatFileListItem):
    pass


@dataclass(slots=True)
class StoredChatFile:
    path: str
    media_type: str | None
    filename: str
