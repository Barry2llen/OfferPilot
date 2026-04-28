from pathlib import Path

import fitz
from fastapi.testclient import TestClient

from main import create_app
from schemas.config import Config
from utils import document_parser


def _create_pdf(path: Path, text: str) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def _resolve_saved_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else Path.cwd() / path


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
        first = client.post("/resumes/files", files={"file": ("resume.png", b"img", "image/png")})
        second = client.post("/resumes/files", files={"file": ("resume.jpg", b"img", "image/jpeg")})

        listed = client.get("/resumes")
        detail = client.get("/resumes/1")

    assert first.status_code == 422
    assert second.status_code == 422
    assert listed.status_code == 200
    assert listed.json() == []
    assert detail.status_code == 404


def test_list_and_detail_resume_endpoints_with_uploaded_files(
    temporary_app_config: Config,
    monkeypatch,
) -> None:
    app = create_app(temporary_app_config)
    parsed_values = iter(["A" * 250, "Second Resume"])
    monkeypatch.setattr(
        document_parser,
        "extract_text",
        lambda _: next(parsed_values),
    )

    with TestClient(app) as client:
        first = client.post(
            "/resumes/files",
            files={"file": ("resume.png", b"image-1", "image/png")},
        )
        second = client.post(
            "/resumes/files",
            files={"file": ("resume.jpg", b"image-2", "image/jpeg")},
        )
        listed = client.get("/resumes")
        detail = client.get(f"/resumes/{first.json()['id']}")

    assert first.status_code == 200
    assert second.status_code == 200
    assert listed.status_code == 200
    assert len(listed.json()) == 2
    assert listed.json()[0]["content_preview"] == "Second Resume"
    assert listed.json()[0]["preview_url"] == f"/resumes/{second.json()['id']}/file"
    assert listed.json()[1]["content_preview"] == "A" * 200
    assert listed.json()[1]["preview_url"] == f"/resumes/{first.json()['id']}/file"
    assert detail.status_code == 200
    assert detail.json()["content"] == "A" * 250
    assert detail.json()["has_file"] is True


def test_upload_resume_file_endpoint_with_image(
    temporary_app_config: Config,
    monkeypatch,
) -> None:
    app = create_app(temporary_app_config)
    monkeypatch.setattr(
        document_parser,
        "extract_text",
        lambda _: "Jane Doe OCR Resume",
    )

    with TestClient(app) as client:
        response = client.post(
            "/resumes/files",
            files={"file": ("resume.png", b"fake-image", "image/png")},
        )

    assert response.status_code == 200
    assert response.json()["content"] == "Jane Doe OCR Resume"
    assert response.json()["media_type"] == "image/png"


def test_replace_resume_file_endpoint(
    temporary_app_config: Config,
    monkeypatch,
) -> None:
    app = create_app(temporary_app_config)
    parsed_values = iter(["Original", "Updated OCR"])
    monkeypatch.setattr(
        document_parser,
        "extract_text",
        lambda _: next(parsed_values),
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


def test_resume_text_endpoints_are_removed(temporary_app_config: Config) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        create_response = client.post("/resumes/text", json={"content": "Plain"})
        update_response = client.patch("/resumes/1/text", json={"content": "Updated"})

    assert create_response.status_code == 405
    assert update_response.status_code == 404


def test_delete_resume_endpoint(
    temporary_app_config: Config,
    monkeypatch,
) -> None:
    app = create_app(temporary_app_config)
    monkeypatch.setattr(document_parser, "extract_text", lambda _: "Stored")

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
        delete = client.delete("/resumes/999")
        preview = client.get("/resumes/999/file")

    assert detail.status_code == 404
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


def test_openapi_json_contains_complete_resume_docs(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    payload = response.json()

    assert payload["info"]["title"] == "OfferPilot API"
    assert "简历文件管理" in payload["info"]["description"]
    assert payload["tags"][0]["name"] == "resumes"
    assert "简历文件管理接口" in payload["tags"][0]["description"]

    root_get = payload["paths"]["/"]["get"]
    assert root_get["summary"] == "服务探活"
    assert "服务已成功启动" in root_get["description"]

    list_resumes = payload["paths"]["/resumes"]["get"]
    assert list_resumes["summary"] == "列出已上传简历"
    assert "摘要信息" in list_resumes["description"]

    upload_resume = payload["paths"]["/resumes/files"]["post"]
    assert upload_resume["summary"] == "上传简历文件"
    assert "PDF、DOCX、PNG、JPG 或 JPEG" in upload_resume["description"]
    assert upload_resume["requestBody"]["content"]["multipart/form-data"]["schema"]["$ref"]
    assert "415" in upload_resume["responses"]
    assert "422" in upload_resume["responses"]

    schemas = payload["components"]["schemas"]
    resume_detail = schemas["ResumeDetail"]
    assert "完整文本内容" in resume_detail["properties"]["content"]["description"]
    assert resume_detail["properties"]["preview_url"]["examples"][0] == "/resumes/1/file"
    assert "ResumeAdviceRequest" not in schemas
    assert "ResumeAdviceResponse" not in schemas
    assert "/resumes/{resume_id}/advice" not in payload["paths"]
    assert "/resumes/{resume_id}/advice/stream" not in payload["paths"]
