from pathlib import Path
from types import ModuleType
from xml.etree import ElementTree
from zipfile import ZipFile

import fitz
from exceptions import ResumeParsingError, UnsupportedResumeFileError


class DocumentParserService:
    """Extract text from supported resume documents."""

    _IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}

    def __init__(self) -> None:
        self._ocr_engine: object | None = None

    def extract_text(self, file_path: Path) -> str:
        suffix = file_path.suffix.lower()

        if suffix == ".pdf":
            return self._extract_pdf_text(file_path)
        if suffix == ".docx":
            return self._extract_docx_text(file_path)
        if suffix in self._IMAGE_SUFFIXES:
            return self._extract_image_text(file_path)
        if suffix == ".doc":
            raise UnsupportedResumeFileError("Legacy .doc files are not supported.")

        raise UnsupportedResumeFileError(f"Unsupported resume file type: {suffix}")

    def _extract_pdf_text(self, file_path: Path) -> str:
        try:
            with fitz.open(file_path) as document:
                return "\n".join(page.get_text("text") for page in document)
        except Exception as error:
            raise ResumeParsingError("Failed to extract text from PDF resume.") from error

    def _extract_docx_text(self, file_path: Path) -> str:
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

    def _extract_image_text(self, file_path: Path) -> str:
        try:
            ocr_engine = self._get_ocr_engine()
            result, _ = ocr_engine(str(file_path))
        except UnsupportedResumeFileError:
            raise
        except Exception as error:
            raise ResumeParsingError("Failed to OCR image resume.") from error

        if not result:
            return ""

        lines: list[str] = []
        for item in result:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                text = item[1]
                if isinstance(text, str) and text:
                    lines.append(text)

        return "\n".join(lines)

    def _get_ocr_engine(self) -> object:
        if self._ocr_engine is not None:
            return self._ocr_engine

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

        self._ocr_engine = rapid_ocr()
        return self._ocr_engine
