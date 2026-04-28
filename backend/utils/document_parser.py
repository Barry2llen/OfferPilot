from pathlib import Path
from types import ModuleType
from xml.etree import ElementTree
from zipfile import ZipFile

import fitz

from exceptions import ResumeParsingError, UnsupportedResumeFileError
from utils.logger import logger

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
_ocr_engine: object | None = None


def extract_text(file_path: Path) -> str:
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        return _extract_pdf_text(file_path)
    if suffix == ".docx":
        return _extract_docx_text(file_path)
    if suffix in _IMAGE_SUFFIXES:
        return extract_text_ocr(file_path)
    if suffix == ".doc":
        raise UnsupportedResumeFileError("Legacy .doc files are not supported.")

    raise UnsupportedResumeFileError(f"Unsupported resume file type: {suffix}")


def extract_text_ocr(file_path: Path) -> str:
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        return _extract_pdf_text_ocr(file_path)
    if suffix in _IMAGE_SUFFIXES:
        return _extract_image_text(file_path)
    if suffix == ".docx":
        logger.warning("DOCX OCR is not supported directly; falling back to direct text extraction.")
        return extract_text(file_path)
    if suffix == ".doc":
        raise UnsupportedResumeFileError("Legacy .doc files are not supported.")

    raise UnsupportedResumeFileError(f"Unsupported resume file type: {suffix}")


def _extract_pdf_text(file_path: Path) -> str:
    try:
        with fitz.open(file_path) as document:
            return "\n".join(page.get_text("text") for page in document)
    except Exception as error:
        raise ResumeParsingError("Failed to extract text from PDF resume.") from error


def _extract_docx_text(file_path: Path) -> str:
    try:
        with ZipFile(file_path) as archive:
            xml_bytes = archive.read("word/document.xml")
    except Exception as error:
        raise ResumeParsingError("Failed to read DOCX resume.") from error

    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as error:
        raise ResumeParsingError("Failed to parse DOCX resume.") from error

    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        fragments = [
            node.text
            for node in paragraph.findall(".//w:t", namespace)
            if node.text
        ]
        if fragments:
            paragraphs.append("".join(fragments))

    return "\n".join(paragraphs)


def _extract_image_text(file_path: Path) -> str:
    return _extract_ocr_text(file_path, "Failed to OCR image resume.")


def _extract_pdf_text_ocr(file_path: Path) -> str:
    try:
        with fitz.open(file_path) as document:
            pages = [
                _extract_ocr_text(page.get_pixmap().tobytes(output="png"), "Failed to OCR PDF resume.")
                for page in document
            ]
    except UnsupportedResumeFileError:
        raise
    except ResumeParsingError:
        raise
    except Exception as error:
        raise ResumeParsingError("Failed to OCR PDF resume.") from error

    return "\n".join(page for page in pages if page)


def _extract_ocr_text(image_content: str | Path | bytes, error_message: str) -> str:
    try:
        ocr_engine = _get_ocr_engine()
        result, _ = ocr_engine(image_content)
    except UnsupportedResumeFileError:
        raise
    except Exception as error:
        raise ResumeParsingError(error_message) from error

    if not result:
        return ""

    lines: list[str] = []
    for item in result:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            text = item[1]
            if isinstance(text, str) and text:
                lines.append(text)

    return "\n".join(lines)


def _get_ocr_engine() -> object:
    global _ocr_engine

    if _ocr_engine is not None:
        return _ocr_engine

    try:
        rapidocr_module = __import__("rapidocr_onnxruntime")
    except ImportError as error:
        raise UnsupportedResumeFileError(
            "Image OCR dependency is not installed."
        ) from error

    module = rapidocr_module if isinstance(rapidocr_module, ModuleType) else None
    rapid_ocr = getattr(module, "RapidOCR", None)
    if rapid_ocr is None:
        raise UnsupportedResumeFileError("Image OCR dependency is not available.")

    _ocr_engine = rapid_ocr()
    return _ocr_engine
