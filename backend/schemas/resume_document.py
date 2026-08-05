from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from exceptions import (
    ResumeFileNotFoundError,
    ResumePreviewError,
    ResumePreviewFileNotFoundError,
)
from pydantic import BaseModel, ConfigDict, Field
from utils.document_assets import render_file_to_images
from utils import document_parser


type ResumeParseStatus = Literal["unparsed", "processing", "parsed", "failed"]

class ResumeDetail(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": 1,
                    "file_path": "data/resumes/2f8f0a8e1d4047d7a1cf9fd649c95ed3.pdf",
                    "upload_time": "2026-04-18T17:00:00",
                    "original_filename": "zhangsan_resume.pdf",
                    "media_type": "application/pdf",
                    "has_file": True,
                    "preview_url": "/resumes/1/file",
                }
            ]
        }
    )

    id: int = Field(description="Resume record ID used to retrieve details and preview the original file.", examples=[1])
    file_path: str | None = Field(
        default=None,
        description="Server-side resume file path, usually relative to the project root.",
        examples=["data/resumes/2f8f0a8e1d4047d7a1cf9fd649c95ed3.pdf"],
    )
    upload_time: datetime = Field(
        description="Resume upload time in ISO 8601 format.",
        examples=["2026-04-18T17:00:00"],
    )
    original_filename: str | None = Field(
        default=None,
        description="Original filename supplied by the user.",
        examples=["zhangsan_resume.pdf"],
    )
    media_type: str | None = Field(
        default=None,
        description="Uploaded file media type.",
        examples=["application/pdf"],
    )
    has_file: bool = Field(
        description="Whether the original resume file is still available for preview.",
        examples=[True],
    )
    preview_url: str | None = Field(
        default=None,
        description="API path for previewing the original resume file online.",
        examples=["/resumes/1/file"],
    )
    parse_status: ResumeParseStatus = Field(
        default="unparsed",
        description="Resume parsing status: unparsed, processing, parsed, or failed.",
        examples=["parsed"],
    )
    parse_error: str | None = Field(
        default=None,
        description="Error details when parsing fails; empty after success or before parsing.",
        examples=["Model call failed after 3 retries."],
    )
    parsed_at: datetime | None = Field(
        default=None,
        description="Time parsing completed; returned after parsing succeeds or fails.",
        examples=["2026-04-18T17:02:00"],
    )
    summary: str | None = Field(
        default=None,
        description="Parsing summary, usually a short excerpt from the beginning of the resume.",
        examples=["张三 高级后端开发工程师 Python, FastAPI"],
    )
    section_count: int = Field(
        default=0,
        description="Number of parsed resume sections.",
        examples=[4],
    )
    fact_count: int = Field(
        default=0,
        description="Number of parsed facts.",
        examples=[18],
    )
    raw_text: str = Field(
        default="",
        description="Complete parsed source text. Omitted from list responses and returned by detail and parsing final events.",
        examples=["张三\n高级后端开发工程师\nPython, FastAPI"],
    )
    sections: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Structured resume sections and facts. Omitted from list responses and returned by detail and parsing final events.",
        examples=[
            [
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
            ]
        ],
    )


class ResumeDocument(ResumeDetail):
    def convert_resume_to_image_base64(self) -> list[str]:
        """
        Convert the stored resume file to preview images as Data URLs.
        """
        file_path = self._require_file_path()
        return [image.to_data_url() for image in render_file_to_images(file_path)]

    def extract_text(self) -> str:
        file_path = self._require_text_file_path()
        if file_path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            return self.extract_text_ocr()
        return document_parser.extract_text(file_path)

    def extract_text_ocr(self) -> str:
        file_path = self._require_text_file_path()
        return document_parser.extract_text_ocr(file_path)

    def _require_file_path(self) -> Path:
        if not self.file_path:
            raise ResumePreviewError("Resume file path is not available.")

        path = Path(self.file_path)
        resolved = path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()
        if not resolved.is_file():
            raise ResumePreviewFileNotFoundError(f"Resume file not found: {self.file_path}")
        return resolved

    def _require_text_file_path(self) -> Path:
        if not self.file_path:
            raise ResumeFileNotFoundError("Resume file path is not available.")

        path = Path(self.file_path)
        resolved = path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()
        if not resolved.is_file():
            raise ResumeFileNotFoundError(f"Resume file not found: {self.file_path}")
        return resolved



class ResumeListItem(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": 2,
                    "file_path": "data/resumes/6b4f0e8199c54c4ab8d7e7b5c53fb242.png",
                    "upload_time": "2026-04-18T17:05:00",
                    "original_filename": "lisi_resume.png",
                    "media_type": "image/png",
                    "has_file": True,
                    "preview_url": "/resumes/2/file",
                }
            ]
        }
    )

    id: int = Field(description="Resume record ID.", examples=[2])
    file_path: str | None = Field(
        default=None,
        description="Server-side resume file path.",
        examples=["data/resumes/6b4f0e8199c54c4ab8d7e7b5c53fb242.png"],
    )
    upload_time: datetime = Field(
        description="Resume upload time in ISO 8601 format.",
        examples=["2026-04-18T17:05:00"],
    )
    original_filename: str | None = Field(
        default=None,
        description="Original filename supplied by the user.",
        examples=["lisi_resume.png"],
    )
    media_type: str | None = Field(
        default=None,
        description="Uploaded file media type.",
        examples=["image/png"],
    )
    has_file: bool = Field(
        description="Whether the original resume file is still available.",
        examples=[True],
    )
    preview_url: str | None = Field(
        default=None,
        description="API path for previewing the original resume file online.",
        examples=["/resumes/2/file"],
    )
    parse_status: ResumeParseStatus = Field(
        default="unparsed",
        description="Resume parsing status.",
        examples=["parsed"],
    )
    parse_error: str | None = Field(
        default=None,
        description="Error details when parsing fails.",
        examples=["Failed to extract text from resume."],
    )
    parsed_at: datetime | None = Field(
        default=None,
        description="Time parsing completed.",
        examples=["2026-04-18T17:06:00"],
    )
    summary: str | None = Field(
        default=None,
        description="Parsing summary.",
        examples=["李四 前端工程师 React, Next.js"],
    )
    section_count: int = Field(
        default=0,
        description="Number of parsed resume sections.",
        examples=[3],
    )
    fact_count: int = Field(
        default=0,
        description="Number of parsed facts.",
        examples=[12],
    )
