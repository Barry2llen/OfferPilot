import sys
from pathlib import Path
from types import ModuleType
from zipfile import ZipFile

import fitz
import pytest

from exceptions import UnsupportedResumeFileError
from services.document_parser_service import DocumentParserService


def _create_pdf(path: Path, text: str) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def _create_docx(path: Path, paragraphs: list[str]) -> None:
    xml_body = "".join(
        "<w:p><w:r><w:t>{text}</w:t></w:r></w:p>".format(text=paragraph)
        for paragraph in paragraphs
    )
    document_xml = (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
        f"<w:body>{xml_body}</w:body>"
        "</w:document>"
    )
    with ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document_xml)


def test_extract_text_from_pdf(workspace_tmp_dir: Path) -> None:
    parser = DocumentParserService()
    file_path = workspace_tmp_dir / "resume.pdf"
    _create_pdf(file_path, "Jane Doe Resume")

    extracted = parser.extract_text(file_path)

    assert "Jane Doe Resume" in extracted


def test_extract_text_from_docx(workspace_tmp_dir: Path) -> None:
    parser = DocumentParserService()
    file_path = workspace_tmp_dir / "resume.docx"
    _create_docx(file_path, ["Jane Doe", "Python Engineer"])

    extracted = parser.extract_text(file_path)

    assert extracted == "Jane Doe\nPython Engineer"


def test_extract_text_from_image_uses_ocr_module(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DocumentParserService()
    file_path = workspace_tmp_dir / "resume.png"
    file_path.write_bytes(b"fake-image")

    class FakeRapidOCR:
        def __call__(self, _: str):
            return [([0, 0, 1, 1], "Jane Doe", 0.99)], None

    fake_module = ModuleType("rapidocr_onnxruntime")
    fake_module.RapidOCR = FakeRapidOCR
    monkeypatch.setitem(
        sys.modules,
        "rapidocr_onnxruntime",
        fake_module,
    )

    extracted = parser.extract_text(file_path)

    assert extracted == "Jane Doe"


def test_extract_text_rejects_doc(workspace_tmp_dir: Path) -> None:
    parser = DocumentParserService()
    file_path = workspace_tmp_dir / "resume.doc"
    file_path.write_bytes(b"legacy-doc")

    with pytest.raises(UnsupportedResumeFileError, match="Legacy \\.doc files"):
        parser.extract_text(file_path)
