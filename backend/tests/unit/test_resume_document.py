import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from zipfile import ZipFile

import fitz
import pytest

from exceptions import (
    ResumeFileNotFoundError,
    ResumePreviewConversionError,
    ResumePreviewDependencyError,
    ResumePreviewError,
    ResumePreviewFileNotFoundError,
    UnsupportedResumeFileError,
    UnsupportedResumePreviewFileError,
)
from schemas.resume_document import (
    ResumeDocument,
)
from utils import document_parser


def _create_pdf(path: Path, pages: list[str]) -> None:
    document = fitz.open()
    for text in pages:
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


def _build_resume(file_path: Path | None) -> ResumeDocument:
    return ResumeDocument(
        id=1,
        file_path=str(file_path) if file_path is not None else None,
        upload_time=datetime.now(),
        original_filename=file_path.name if file_path is not None else None,
        media_type=None,
        has_file=file_path is not None,
        preview_url=None,
    )


def test_convert_pdf_to_preview_images(workspace_tmp_dir: Path) -> None:
    file_path = workspace_tmp_dir / "resume.pdf"
    _create_pdf(file_path, ["page-1", "page-2"])

    previews = _build_resume(file_path).convert_resume_to_image_base64()

    assert len(previews) == 2
    assert all(item.startswith("data:image/png;base64,") for item in previews)


def test_convert_png_to_preview_image(workspace_tmp_dir: Path) -> None:
    file_path = workspace_tmp_dir / "resume.png"
    file_path.write_bytes(b"fake-png")

    previews = _build_resume(file_path).convert_resume_to_image_base64()

    assert previews == ["data:image/png;base64,ZmFrZS1wbmc="]


def test_convert_jpeg_to_preview_image(workspace_tmp_dir: Path) -> None:
    file_path = workspace_tmp_dir / "resume.jpg"
    file_path.write_bytes(b"fake-jpg")

    previews = _build_resume(file_path).convert_resume_to_image_base64()

    assert previews == ["data:image/jpeg;base64,ZmFrZS1qcGc="]


def test_convert_docx_to_preview_images_with_aspose_module(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_path = workspace_tmp_dir / "resume.docx"
    _create_docx(file_path, ["Jane Doe", "Python Engineer"])

    class FakeImageSaveOptions:
        def __init__(self, _: str) -> None:
            self.page_index = 0
            self.page_count = 0

    class FakeDocument:
        def __init__(self, _: str) -> None:
            self.page_count = 2

        def save(self, buffer, options: FakeImageSaveOptions) -> None:
            buffer.write(f"page-{options.page_index}".encode("ascii"))

    fake_words = ModuleType("aspose.words")
    fake_words.Document = FakeDocument
    fake_words.SaveFormat = SimpleNamespace(PNG="png")
    fake_words.saving = SimpleNamespace(ImageSaveOptions=FakeImageSaveOptions)

    fake_aspose = ModuleType("aspose")
    fake_aspose.words = fake_words
    monkeypatch.setitem(sys.modules, "aspose", fake_aspose)
    monkeypatch.setitem(sys.modules, "aspose.words", fake_words)

    previews = _build_resume(file_path).convert_resume_to_image_base64()

    assert previews == [
        "data:image/png;base64,cGFnZS0w",
        "data:image/png;base64,cGFnZS0x",
    ]


def test_convert_docx_raises_dependency_error_when_aspose_missing(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_path = workspace_tmp_dir / "resume.docx"
    _create_docx(file_path, ["Jane Doe"])
    monkeypatch.setattr(
        "schemas.resume_document.import_module",
        lambda _: (_ for _ in ()).throw(ImportError("missing aspose.words")),
    )

    with pytest.raises(ResumePreviewDependencyError, match="Aspose\\.Words"):
        _build_resume(file_path).convert_resume_to_image_base64()


def test_convert_raises_when_file_path_missing() -> None:
    with pytest.raises(ResumePreviewError, match="file path is not available"):
        _build_resume(None).convert_resume_to_image_base64()


def test_convert_raises_when_file_missing() -> None:
    file_path = Path("dev/test-tmp/missing-resume.pdf")

    with pytest.raises(ResumePreviewFileNotFoundError, match="Resume file not found"):
        _build_resume(file_path).convert_resume_to_image_base64()


def test_convert_raises_for_unsupported_file_type(workspace_tmp_dir: Path) -> None:
    file_path = workspace_tmp_dir / "resume.txt"
    file_path.write_text("resume", encoding="utf-8")

    with pytest.raises(UnsupportedResumePreviewFileError, match="Unsupported resume preview"):
        _build_resume(file_path).convert_resume_to_image_base64()


def test_convert_docx_raises_conversion_error_when_renderer_fails(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_path = workspace_tmp_dir / "resume.docx"
    _create_docx(file_path, ["Jane Doe"])

    class FakeImageSaveOptions:
        def __init__(self, _: str) -> None:
            self.page_index = 0
            self.page_count = 0

    class FakeDocument:
        def __init__(self, _: str) -> None:
            self.page_count = 1

        def save(self, buffer, options: FakeImageSaveOptions) -> None:
            raise RuntimeError("render failed")

    fake_words = ModuleType("aspose.words")
    fake_words.Document = FakeDocument
    fake_words.SaveFormat = SimpleNamespace(PNG="png")
    fake_words.saving = SimpleNamespace(ImageSaveOptions=FakeImageSaveOptions)

    fake_aspose = ModuleType("aspose")
    fake_aspose.words = fake_words
    monkeypatch.setitem(sys.modules, "aspose", fake_aspose)
    monkeypatch.setitem(sys.modules, "aspose.words", fake_words)

    with pytest.raises(ResumePreviewConversionError, match="Failed to convert DOCX"):
        _build_resume(file_path).convert_resume_to_image_base64()


def test_extract_text_delegates_pdf_to_helper(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_path = workspace_tmp_dir / "resume.pdf"
    _create_pdf(file_path, ["Jane Doe"])
    monkeypatch.setattr(document_parser, "extract_text", lambda _: "Jane Doe")

    extracted = _build_resume(file_path).extract_text()

    assert extracted == "Jane Doe"


def test_extract_text_delegates_image_to_ocr(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_path = workspace_tmp_dir / "resume.png"
    file_path.write_bytes(b"fake-png")
    monkeypatch.setattr(ResumeDocument, "extract_text_ocr", lambda self: "OCR Resume")

    extracted = _build_resume(file_path).extract_text()

    assert extracted == "OCR Resume"


def test_extract_text_ocr_delegates_to_helper(
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_path = workspace_tmp_dir / "resume.docx"
    _create_docx(file_path, ["Jane Doe"])
    monkeypatch.setattr(document_parser, "extract_text_ocr", lambda _: "Jane Doe")

    extracted = _build_resume(file_path).extract_text_ocr()

    assert extracted == "Jane Doe"


def test_extract_text_raises_when_file_path_missing() -> None:
    with pytest.raises(ResumeFileNotFoundError, match="file path is not available"):
        _build_resume(None).extract_text()


def test_extract_text_ocr_raises_for_unsupported_file_type(
    workspace_tmp_dir: Path,
) -> None:
    file_path = workspace_tmp_dir / "resume.txt"
    file_path.write_text("resume", encoding="utf-8")

    with pytest.raises(UnsupportedResumeFileError, match="Unsupported resume file type"):
        _build_resume(file_path).extract_text_ocr()
