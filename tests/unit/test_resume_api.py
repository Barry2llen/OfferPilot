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
    assert response.json()["has_file"] is False


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
    assert payload["preview_url"] == f"/resumes/{payload['id']}/file"
    assert _resolve_saved_path(payload["file_path"]).exists()


def test_list_and_detail_resume_endpoints(temporary_app_config: Config) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        text_response = client.post("/resumes/text", json={"content": "A" * 250})
        file_response = client.post("/resumes/files", files={"file": ("resume.png", b"img", "image/png")})

        listed = client.get("/resumes")
        detail = client.get(f"/resumes/{text_response.json()['id']}")

    assert file_response.status_code == 422
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["content_preview"] == "A" * 200
    assert listed.json()[0]["preview_url"] is None
    assert detail.status_code == 200
    assert detail.json()["content"] == "A" * 250
    assert detail.json()["has_file"] is False


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


def test_update_resume_text_endpoint(temporary_app_config: Config) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        created = client.post("/resumes/text", json={"content": "Original"})
        response = client.patch(
            f"/resumes/{created.json()['id']}/text",
            json={"content": "Updated"},
        )

    assert response.status_code == 200
    assert response.json()["content"] == "Updated"


def test_replace_resume_file_endpoint(
    temporary_app_config: Config,
    monkeypatch,
) -> None:
    app = create_app(temporary_app_config)
    parsed_values = iter(["Original", "Updated OCR"])
    monkeypatch.setattr(
        DocumentParserService,
        "extract_text",
        lambda self, _: next(parsed_values),
    )

    with TestClient(app) as client:
        created = client.post(
            "/resumes/files",
            files={"file": ("resume.png", b"image-1", "image/png")},
        )
        response = client.put(
            f"/resumes/{created.json()['id']}/file",
            files={"file": ("resume.jpg", b"image-2", "image/jpeg")},
        )

    assert response.status_code == 200
    assert response.json()["content"] == "Updated OCR"
    assert response.json()["original_filename"] == "resume.jpg"
    assert response.json()["media_type"] == "image/jpeg"


def test_preview_resume_file_endpoint(
    temporary_app_config: Config,
    workspace_tmp_dir: Path,
) -> None:
    app = create_app(temporary_app_config)
    pdf_path = workspace_tmp_dir / "resume.pdf"
    _create_pdf(pdf_path, "Jane Doe Resume")

    with TestClient(app) as client:
        with pdf_path.open("rb") as file:
            created = client.post(
                "/resumes/files",
                files={"file": ("resume.pdf", file, "application/pdf")},
            )
        response = client.get(f"/resumes/{created.json()['id']}/file")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "inline" in response.headers["content-disposition"]
    assert response.content


def test_preview_text_resume_returns_404(temporary_app_config: Config) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        created = client.post("/resumes/text", json={"content": "Plain"})
        response = client.get(f"/resumes/{created.json()['id']}/file")

    assert response.status_code == 404


def test_delete_resume_endpoint(
    temporary_app_config: Config,
    monkeypatch,
) -> None:
    app = create_app(temporary_app_config)
    monkeypatch.setattr(DocumentParserService, "extract_text", lambda self, _: "Stored")

    with TestClient(app) as client:
        created = client.post(
            "/resumes/files",
            files={"file": ("resume.png", b"fake-image", "image/png")},
        )
        saved_path = _resolve_saved_path(created.json()["file_path"])
        delete_response = client.delete(f"/resumes/{created.json()['id']}")
        get_response = client.get(f"/resumes/{created.json()['id']}")

    assert delete_response.status_code == 204
    assert get_response.status_code == 404
    assert not saved_path.exists()


def test_resume_endpoints_return_404_for_missing_id(temporary_app_config: Config) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        detail = client.get("/resumes/999")
        update = client.patch("/resumes/999/text", json={"content": "Updated"})
        delete = client.delete("/resumes/999")
        preview = client.get("/resumes/999/file")

    assert detail.status_code == 404
    assert update.status_code == 404
    assert delete.status_code == 404
    assert preview.status_code == 404


def test_upload_resume_file_endpoint_rejects_doc(temporary_app_config: Config) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        response = client.post(
            "/resumes/files",
            files={"file": ("resume.doc", b"legacy-doc", "application/msword")},
        )

    assert response.status_code == 415
    assert "Legacy .doc files are not supported." in response.json()["detail"]
