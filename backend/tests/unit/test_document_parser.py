import sys
from pathlib import Path
from types import ModuleType
from zipfile import ZipFile

import fitz
import pytest

from exceptions import ResumeParsingError, UnsupportedResumeFileError
from utils import document_parser


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
    file_path = workspace_tmp_dir / "resume.pdf"
    _create_pdf(file_path, "Jane Doe Resume")

    extracted = document_parser.extract_text(file_path)

    assert "Jane Doe Resume" in extracted


def test_extract_text_from_docx(workspace_tmp_dir: Path) -> None:
    file_path = workspace_tmp_dir / "resume.docx"
    _create_docx(file_path, ["Jane Doe", "Python Engineer"])

    extracted = document_parser.extract_text(file_path)

    assert extracted == "Jane Doe\nPython Engineer"


def test_extract_text_from_image_uses_ocr_module(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_path = workspace_tmp_dir / "resume.png"
    file_path.write_bytes(b"fake-image")

    class FakeRapidOCR:
        def __call__(self, _: str | Path | bytes):
            return [([0, 0, 1, 1], "Jane Doe", 0.99)], None

    fake_module = ModuleType("rapidocr_onnxruntime")
    fake_module.RapidOCR = FakeRapidOCR
    monkeypatch.setitem(
        sys.modules,
        "rapidocr_onnxruntime",
        fake_module,
    )
    monkeypatch.setattr(document_parser, "_ocr_engine", None)

    extracted = document_parser.extract_text(file_path)

    assert extracted == "Jane Doe"


def test_extract_text_ocr_from_pdf_renders_pages_before_ocr(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_path = workspace_tmp_dir / "resume.pdf"
    _create_pdf(file_path, "Jane Doe Resume")
    seen_payloads: list[bytes] = []

    class FakeRapidOCR:
        def __call__(self, payload: str | Path | bytes):
            assert isinstance(payload, bytes)
            seen_payloads.append(payload)
            return [([0, 0, 1, 1], f"page-{len(seen_payloads)}", 0.99)], None

    fake_module = ModuleType("rapidocr_onnxruntime")
    fake_module.RapidOCR = FakeRapidOCR
    monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", fake_module)
    monkeypatch.setattr(document_parser, "_ocr_engine", None)

    extracted = document_parser.extract_text_ocr(file_path)

    assert extracted == "page-1"
    assert seen_payloads


def test_extract_text_ocr_for_docx_logs_warning_and_falls_back(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_path = workspace_tmp_dir / "resume.docx"
    _create_docx(file_path, ["Jane Doe"])
    warnings: list[str] = []
    monkeypatch.setattr(document_parser.logger, "warning", lambda message: warnings.append(message))

    extracted = document_parser.extract_text_ocr(file_path)

    assert extracted == "Jane Doe"
    assert warnings == ["DOCX OCR is not supported directly; falling back to direct text extraction."]


def test_extract_text_ocr_raises_when_ocr_dependency_missing(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_path = workspace_tmp_dir / "resume.png"
    file_path.write_bytes(b"fake-image")
    monkeypatch.delitem(sys.modules, "rapidocr_onnxruntime", raising=False)
    monkeypatch.setattr(document_parser, "_ocr_engine", None)

    original_import = __import__

    def _raise_import_error(name: str, *args, **kwargs):
        if name == "rapidocr_onnxruntime":
            raise ImportError("missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _raise_import_error)

    with pytest.raises(UnsupportedResumeFileError, match="Image OCR dependency is not installed"):
        document_parser.extract_text_ocr(file_path)


def test_extract_text_ocr_wraps_runtime_errors(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_path = workspace_tmp_dir / "resume.png"
    file_path.write_bytes(b"fake-image")

    class FakeRapidOCR:
        def __call__(self, _: str | Path | bytes):
            raise RuntimeError("boom")

    fake_module = ModuleType("rapidocr_onnxruntime")
    fake_module.RapidOCR = FakeRapidOCR
    monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", fake_module)
    monkeypatch.setattr(document_parser, "_ocr_engine", None)

    with pytest.raises(ResumeParsingError, match="Failed to OCR image resume"):
        document_parser.extract_text_ocr(file_path)


def test_extract_text_rejects_doc(workspace_tmp_dir: Path) -> None:
    file_path = workspace_tmp_dir / "resume.doc"
    file_path.write_bytes(b"legacy-doc")

    with pytest.raises(UnsupportedResumeFileError, match="Legacy \\.doc files"):
        document_parser.extract_text(file_path)
