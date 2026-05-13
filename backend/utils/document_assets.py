import base64
import io
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from types import ModuleType

import fitz

from exceptions import (
    ResumeParsingError,
    ResumePreviewConversionError,
    ResumePreviewDependencyError,
    UnsupportedResumeFileError,
    UnsupportedResumePreviewFileError,
)
from utils import document_parser
from utils.garble_text import detect_garbled_text

_DIRECT_IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
_TEXT_FILE_SUFFIXES = {
    ".txt",
    ".md",
    ".json",
    ".csv",
    ".yaml",
    ".yml",
    ".xml",
    ".html",
    ".htm",
    ".log",
    ".ini",
    ".conf",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".go",
    ".rs",
    ".sh",
    ".sql",
}
_CHAT_SUPPORTED_SUFFIXES = {
    ".pdf",
    ".docx",
    *set(_DIRECT_IMAGE_MIME_TYPES),
    *_TEXT_FILE_SUFFIXES,
}


@dataclass(frozen=True, slots=True)
class RenderedDocumentImage:
    mime_type: str
    base64_data: str

    def to_data_url(self) -> str:
        return f"data:{self.mime_type};base64,{self.base64_data}"

    def to_content_block(self) -> dict[str, str]:
        return {
            "type": "image",
            "base64": self.base64_data,
            "mime_type": self.mime_type,
        }


def is_supported_chat_file_suffix(suffix: str) -> bool:
    return suffix.lower() in _CHAT_SUPPORTED_SUFFIXES


def is_textual_chat_file(file_path: Path) -> bool:
    return file_path.suffix.lower() in _TEXT_FILE_SUFFIXES


def is_chat_image_document(file_path: Path) -> bool:
    return file_path.suffix.lower() in {".pdf", ".docx", *set(_DIRECT_IMAGE_MIME_TYPES)}


def render_file_to_images(file_path: Path) -> list[RenderedDocumentImage]:
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        return _convert_pdf_to_images(file_path)
    if suffix == ".docx":
        return _convert_docx_to_images(file_path)
    if suffix in _DIRECT_IMAGE_MIME_TYPES:
        return [_encode_image(file_path.read_bytes(), _DIRECT_IMAGE_MIME_TYPES[suffix])]

    raise UnsupportedResumePreviewFileError(
        f"Unsupported resume preview file type: {suffix or '<missing>'}"
    )


def extract_ocr_text(file_path: Path) -> str:
    return document_parser.extract_text_ocr(file_path)


def decode_text_file(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix not in _TEXT_FILE_SUFFIXES:
        raise UnsupportedResumeFileError(
            f"Unsupported resume file type: {suffix or '<missing>'}"
        )

    payload = file_path.read_bytes()
    if not payload:
        return ""

    text = _decode_bytes(payload)
    if detect_garbled_text(text).is_garbled:
        raise ResumeParsingError("Failed to decode text file content.")
    return text


def _convert_pdf_to_images(file_path: Path) -> list[RenderedDocumentImage]:
    try:
        with fitz.open(file_path) as document:
            return [
                _encode_image(page.get_pixmap().tobytes(output="png"), "image/png")
                for page in document
            ]
    except Exception as error:
        raise ResumePreviewConversionError(
            "Failed to convert PDF resume to preview images."
        ) from error


def _convert_docx_to_images(file_path: Path) -> list[RenderedDocumentImage]:
    try:
        aw = import_module("aspose.words")
    except ImportError as error:
        raise ResumePreviewDependencyError(
            "Aspose.Words dependency is not installed."
        ) from error

    try:
        document = aw.Document(str(file_path))
        previews: list[RenderedDocumentImage] = []
        for page_index in range(document.page_count):
            options = aw.saving.ImageSaveOptions(aw.SaveFormat.PNG)
            options.page_index = page_index
            options.page_count = 1
            buffer = io.BytesIO()
            document.save(buffer, options)
            previews.append(_encode_image(buffer.getvalue(), "image/png"))
        return previews
    except Exception as error:
        raise ResumePreviewConversionError(
            "Failed to convert DOCX resume to preview images."
        ) from error


def _encode_image(payload: bytes, mime_type: str) -> RenderedDocumentImage:
    return RenderedDocumentImage(
        mime_type=mime_type,
        base64_data=base64.b64encode(payload).decode("ascii"),
    )


def _decode_bytes(payload: bytes) -> str:
    if b"\x00" in payload:
        raise ResumeParsingError("Text file appears to be binary.")

    try:
        charset_module = __import__("charset_normalizer")
    except ImportError:
        charset_module = None

    if isinstance(charset_module, ModuleType):
        from_bytes = getattr(charset_module, "from_bytes", None)
        if callable(from_bytes):
            matches = from_bytes(payload)
            best = matches.best() if matches is not None else None
            if best is not None:
                output = str(best)
                if output:
                    return output

    for encoding in ("utf-8", "utf-8-sig", "utf-16", "gb18030", "latin-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise ResumeParsingError("Failed to decode text file content.")
