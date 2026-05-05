import base64
import io
from datetime import datetime
from importlib import import_module
from pathlib import Path
from typing import Any, Literal

import fitz
from exceptions import (
    ResumeFileNotFoundError,
    ResumePreviewConversionError,
    ResumePreviewDependencyError,
    ResumePreviewError,
    ResumePreviewFileNotFoundError,
    UnsupportedResumePreviewFileError,
)
from pydantic import BaseModel, ConfigDict, Field
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

    id: int = Field(description="简历记录 ID。用于查询详情和预览原文件。", examples=[1])
    file_path: str | None = Field(
        default=None,
        description="服务端保存的简历文件路径。通常为相对项目根目录的存储路径。",
        examples=["data/resumes/2f8f0a8e1d4047d7a1cf9fd649c95ed3.pdf"],
    )
    upload_time: datetime = Field(
        description="简历上传时间，采用 ISO 8601 格式。",
        examples=["2026-04-18T17:00:00"],
    )
    original_filename: str | None = Field(
        default=None,
        description="用户上传时的原始文件名。",
        examples=["zhangsan_resume.pdf"],
    )
    media_type: str | None = Field(
        default=None,
        description="上传文件的媒体类型。",
        examples=["application/pdf"],
    )
    has_file: bool = Field(
        description="是否仍然保留原始简历文件，可用于预览。",
        examples=[True],
    )
    preview_url: str | None = Field(
        default=None,
        description="用于在线预览原始简历文件的接口路径。",
        examples=["/resumes/1/file"],
    )
    parse_status: ResumeParseStatus = Field(
        default="unparsed",
        description="简历解析状态。unparsed 表示尚未解析，processing 表示解析中，parsed 表示解析成功，failed 表示解析失败。",
        examples=["parsed"],
    )
    parse_error: str | None = Field(
        default=None,
        description="解析失败时的错误详情。解析成功或尚未解析时为空。",
        examples=["Model call failed after 3 retries."],
    )
    parsed_at: datetime | None = Field(
        default=None,
        description="解析完成时间。仅解析成功或失败后返回。",
        examples=["2026-04-18T17:02:00"],
    )
    summary: str | None = Field(
        default=None,
        description="解析结果摘要，通常取简历原文开头的简短文本。",
        examples=["张三 高级后端开发工程师 Python, FastAPI"],
    )
    section_count: int = Field(
        default=0,
        description="已解析出的简历章节数量。",
        examples=[4],
    )
    fact_count: int = Field(
        default=0,
        description="已解析出的事实数量。",
        examples=[18],
    )
    raw_text: str = Field(
        default="",
        description="完整解析原文。列表接口不返回该字段，详情和解析 final 事件会返回。",
        examples=["张三\n高级后端开发工程师\nPython, FastAPI"],
    )
    sections: list[dict[str, Any]] = Field(
        default_factory=list,
        description="结构化简历章节及 facts。列表接口不返回该字段，详情和解析 final 事件会返回。",
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
    _DIRECT_IMAGE_MIME_TYPES = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }

    def convert_resume_to_image_base64(self) -> list[str]:
        """
        Convert the stored resume file to preview images as Data URLs.
        """
        file_path = self._require_file_path()
        suffix = file_path.suffix.lower()

        if suffix == ".pdf":
            return self._convert_pdf_to_images(file_path)
        if suffix == ".docx":
            return self._convert_docx_to_images(file_path)
        if suffix in self._DIRECT_IMAGE_MIME_TYPES:
            return [self._build_data_url(file_path.read_bytes(), self._DIRECT_IMAGE_MIME_TYPES[suffix])]

        raise UnsupportedResumePreviewFileError(
            f"Unsupported resume preview file type: {suffix or '<missing>'}"
        )

    def extract_text(self) -> str:
        file_path = self._require_text_file_path()
        if file_path.suffix.lower() in self._DIRECT_IMAGE_MIME_TYPES:
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

    def _convert_pdf_to_images(self, file_path: Path) -> list[str]:
        try:
            with fitz.open(file_path) as document:
                return [
                    self._build_data_url(
                        page.get_pixmap().tobytes(output="png"),
                        "image/png",
                    )
                    for page in document
                ]
        except ResumePreviewError:
            raise
        except Exception as error:
            raise ResumePreviewConversionError(
                "Failed to convert PDF resume to preview images."
            ) from error

    def _convert_docx_to_images(self, file_path: Path) -> list[str]:
        try:
            aw = import_module("aspose.words")
        except ImportError as error:
            raise ResumePreviewDependencyError(
                "Aspose.Words dependency is not installed."
            ) from error

        try:
            document = aw.Document(str(file_path))
            previews: list[str] = []
            for page_index in range(document.page_count):
                options = aw.saving.ImageSaveOptions(aw.SaveFormat.PNG)
                options.page_index = page_index
                options.page_count = 1
                buffer = io.BytesIO()
                document.save(buffer, options)
                previews.append(self._build_data_url(buffer.getvalue(), "image/png"))
            return previews
        except ResumePreviewError:
            raise
        except Exception as error:
            raise ResumePreviewConversionError(
                "Failed to convert DOCX resume to preview images."
            ) from error

    def _build_data_url(self, payload: bytes, mime_type: str) -> str:
        encoded = base64.b64encode(payload).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"



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

    id: int = Field(description="简历记录 ID。", examples=[2])
    file_path: str | None = Field(
        default=None,
        description="服务端保存的简历文件路径。",
        examples=["data/resumes/6b4f0e8199c54c4ab8d7e7b5c53fb242.png"],
    )
    upload_time: datetime = Field(
        description="简历上传时间，采用 ISO 8601 格式。",
        examples=["2026-04-18T17:05:00"],
    )
    original_filename: str | None = Field(
        default=None,
        description="用户上传时的原始文件名。",
        examples=["lisi_resume.png"],
    )
    media_type: str | None = Field(
        default=None,
        description="上传文件的媒体类型。",
        examples=["image/png"],
    )
    has_file: bool = Field(
        description="是否仍然保留原始简历文件。",
        examples=[True],
    )
    preview_url: str | None = Field(
        default=None,
        description="用于在线预览原始简历文件的接口路径。",
        examples=["/resumes/2/file"],
    )
    parse_status: ResumeParseStatus = Field(
        default="unparsed",
        description="简历解析状态。",
        examples=["parsed"],
    )
    parse_error: str | None = Field(
        default=None,
        description="解析失败时的错误详情。",
        examples=["Failed to extract text from resume."],
    )
    parsed_at: datetime | None = Field(
        default=None,
        description="解析完成时间。",
        examples=["2026-04-18T17:06:00"],
    )
    summary: str | None = Field(
        default=None,
        description="解析结果摘要。",
        examples=["李四 前端工程师 React, Next.js"],
    )
    section_count: int = Field(
        default=0,
        description="已解析出的简历章节数量。",
        examples=[3],
    )
    fact_count: int = Field(
        default=0,
        description="已解析出的事实数量。",
        examples=[12],
    )
