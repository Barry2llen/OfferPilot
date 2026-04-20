import base64
import io
from datetime import datetime
from importlib import import_module
from pathlib import Path

import fitz
from exceptions import (
    ResumePreviewConversionError,
    ResumePreviewDependencyError,
    ResumePreviewError,
    ResumePreviewFileNotFoundError,
    UnsupportedResumePreviewFileError,
)

from pydantic import BaseModel, ConfigDict, Field

class ResumeDetail(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": 1,
                    "file_path": "data/resumes/2f8f0a8e1d4047d7a1cf9fd649c95ed3.pdf",
                    "content": "张三\n五年前端开发经验\n负责企业后台与数据可视化项目交付。",
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
    content: str = Field(
        description="从简历文件中解析得到的完整文本内容。",
        examples=["张三\n五年前端开发经验\n负责企业后台与数据可视化项目交付。"],
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

    def _require_file_path(self) -> Path:
        if not self.file_path:
            raise ResumePreviewError("Resume file path is not available.")

        path = Path(self.file_path)
        resolved = path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()
        if not resolved.is_file():
            raise ResumePreviewFileNotFoundError(f"Resume file not found: {self.file_path}")
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
                    "content_preview": "李四，三年 Java 开发经验，熟悉 Spring Boot 与微服务治理。",
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
    content_preview: str = Field(
        description="解析文本的预览内容，最长返回前 200 个字符。",
        examples=["李四，三年 Java 开发经验，熟悉 Spring Boot 与微服务治理。"],
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
