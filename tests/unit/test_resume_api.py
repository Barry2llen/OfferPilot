from pathlib import Path

import fitz
from fastapi.testclient import TestClient

from main import create_app
from schemas.config import Config
from services.document_parser_service import DocumentParserService


def _create_pdf(path: Path, text: str) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def _resolve_saved_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else Path.cwd() / path


def test_upload_resume_text_endpoint(temporary_app_config: Config) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        response = client.post("/resumes/text", json={"content": "Jane Doe Resume"})

    assert response.status_code == 200
    assert response.json()["content"] == "Jane Doe Resume"
    assert response.json()["file_path"] is None


def test_upload_resume_file_endpoint_with_pdf(
    temporary_app_config: Config,
    workspace_tmp_dir: Path,
) -> None:
    app = create_app(temporary_app_config)
    pdf_path = workspace_tmp_dir / "resume.pdf"
    _create_pdf(pdf_path, "Jane Doe Resume")

    with TestClient(app) as client:
        with pdf_path.open("rb") as file:
            response = client.post(
                "/resumes/files",
                files={"file": ("resume.pdf", file, "application/pdf")},
            )

    assert response.status_code == 200
    payload = response.json()
    assert "Jane Doe Resume" in payload["content"]
    assert payload["original_filename"] == "resume.pdf"
    assert payload["file_path"] is not None
    assert _resolve_saved_path(payload["file_path"]).exists()


def test_upload_resume_file_endpoint_with_image(
    temporary_app_config: Config,
    monkeypatch,
) -> None:
    app = create_app(temporary_app_config)
    monkeypatch.setattr(
        DocumentParserService,
        "extract_text",
        lambda self, _: "Jane Doe OCR Resume",
    )

    with TestClient(app) as client:
        response = client.post(
            "/resumes/files",
            files={"file": ("resume.png", b"fake-image", "image/png")},
        )

    assert response.status_code == 200
    assert response.json()["content"] == "Jane Doe OCR Resume"
    assert response.json()["media_type"] == "image/png"


def test_upload_resume_file_endpoint_rejects_doc(temporary_app_config: Config) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        response = client.post(
            "/resumes/files",
            files={"file": ("resume.doc", b"legacy-doc", "application/msword")},
        )

    assert response.status_code == 415
    assert "Legacy .doc files are not supported." in response.json()["detail"]
