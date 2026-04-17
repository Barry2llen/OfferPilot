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

from pydantic import BaseModel

class ResumeDetail(BaseModel):
    id: int
    file_path: str | None = None
    content: str
    upload_time: datetime
    original_filename: str | None = None
    media_type: str | None = None
    has_file: bool
    preview_url: str | None = None


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
    id: int
    file_path: str | None = None
    upload_time: datetime
    original_filename: str | None = None
    media_type: str | None = None
    content_preview: str
    has_file: bool
    preview_url: str | None = None
