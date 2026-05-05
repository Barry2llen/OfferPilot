import asyncio
import json
import time
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

from main import create_app
from schemas.config import Config
from schemas.resume import Resume, ResumeFact, ResumeSection


def _create_pdf(path: Path, text: str) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def _resolve_saved_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else Path.cwd() / path


def _create_model_selection(client: TestClient) -> int:
    provider = client.post(
        "/model-providers",
        json={
            "provider": "OpenAI",
            "name": "default-openai",
        },
    )
    selection = client.post(
        "/model-selections",
        json={
            "provider_name": "default-openai",
            "model_name": "gpt-4o-mini",
        },
    )

    assert provider.status_code == 200
    assert selection.status_code == 200
    return selection.json()["id"]


def _install_fake_resume_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResumeExtractWorkflow:
        def __init__(self, config=None) -> None:
            self.config = config

        async def astream_events(self, selection, resume_document, handlers=None):
            if handlers and "on_custom_event" in handlers:
                await handlers["on_custom_event"](
                    {
                        "event": "on_custom_event",
                        "name": "on_progress_update",
                        "data": {
                            "progress": 0.5,
                            "message": "Extracting resume sections.",
                            "additional_data": {"section_count": 1},
                        },
                    }
                )
            return Resume(
                raw_text="Jane Doe\nPython Engineer",
                document=resume_document,
                sections=[
                    ResumeSection(
                        title="技能",
                        content="Python, FastAPI",
                        facts=[
                            ResumeFact(
                                fact_type="skill",
                                text="Python",
                                evidence="Python, FastAPI",
                                keywords=["Python"],
                            )
                        ],
                    )
                ],
            )

    monkeypatch.setattr(
        "services.resume_extraction_jobs.ResumeExtractWorkflow",
        FakeResumeExtractWorkflow,
    )


def _install_failing_resume_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingResumeExtractWorkflow:
        def __init__(self, config=None) -> None:
            self.config = config

        async def astream_events(self, selection, resume_document, handlers=None):
            raise RuntimeError("extract failed")

    monkeypatch.setattr(
        "services.resume_extraction_jobs.ResumeExtractWorkflow",
        FailingResumeExtractWorkflow,
    )


def _sse_payload(response, event_name: str) -> dict:
    for block in response.text.strip().split("\n\n"):
        event = None
        data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line.removeprefix("event:").strip()
            if line.startswith("data:"):
                data = json.loads(line.removeprefix("data:").strip())
        if event == event_name and data is not None:
            return data
    raise AssertionError(f"SSE event not found: {event_name}\n{response.text}")


def _wait_for_parse_status(
    client: TestClient,
    resume_id: int,
    status: str,
    *,
    timeout: float = 1.5,
) -> dict:
    deadline = time.monotonic() + timeout
    last_payload: dict | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/resumes/{resume_id}")
        assert response.status_code == 200
        last_payload = response.json()
        if last_payload["parse_status"] == status:
            return last_payload
        time.sleep(0.02)
    raise AssertionError(f"Resume {resume_id} did not reach {status}: {last_payload}")


def test_upload_resume_file_endpoint_with_pdf(
    temporary_app_config: Config,
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_resume_workflow(monkeypatch)
    app = create_app(temporary_app_config)
    pdf_path = workspace_tmp_dir / "resume.pdf"
    _create_pdf(pdf_path, "Jane Doe Resume")

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)
        with pdf_path.open("rb") as file:
            response = client.post(
                "/resumes/files",
                data={"selection_id": str(selection_id)},
                files={"file": ("resume.pdf", file, "application/pdf")},
            )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: progress" in response.text
    payload = _sse_payload(response, "final")["resume"]
    assert "content" not in payload
    assert payload["original_filename"] == "resume.pdf"
    assert payload["file_path"] is not None
    assert payload["preview_url"] == f"/resumes/{payload['id']}/file"
    assert payload["parse_status"] == "parsed"
    assert payload["raw_text"] == "Jane Doe\nPython Engineer"
    assert payload["section_count"] == 1
    assert payload["fact_count"] == 1
    assert _resolve_saved_path(payload["file_path"]).exists()


def test_list_and_detail_resume_endpoints(temporary_app_config: Config) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)
        first = client.post(
            "/resumes/files",
            data={"selection_id": str(selection_id)},
            files={"file": ("resume.txt", b"text", "text/plain")},
        )
        second = client.post(
            "/resumes/files",
            data={"selection_id": str(selection_id)},
            files={"file": ("resume.doc", b"doc", "application/msword")},
        )

        listed = client.get("/resumes")
        detail = client.get("/resumes/1")

    assert first.status_code == 415
    assert second.status_code == 415
    assert listed.status_code == 200
    assert listed.json() == []
    assert detail.status_code == 404


def test_list_and_detail_resume_endpoints_with_uploaded_files(
    temporary_app_config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_resume_workflow(monkeypatch)
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)
        first = client.post(
            "/resumes/files",
            data={"selection_id": str(selection_id)},
            files={"file": ("resume.png", b"image-1", "image/png")},
        )
        second = client.post(
            "/resumes/files",
            data={"selection_id": str(selection_id)},
            files={"file": ("resume.jpg", b"image-2", "image/jpeg")},
        )
        first_payload = _sse_payload(first, "final")["resume"]
        second_payload = _sse_payload(second, "final")["resume"]
        listed = client.get("/resumes")
        detail = client.get(f"/resumes/{first_payload['id']}")

    assert first.status_code == 200
    assert second.status_code == 200
    assert listed.status_code == 200
    assert len(listed.json()) == 2
    assert "content_preview" not in listed.json()[0]
    assert listed.json()[0]["preview_url"] == f"/resumes/{second_payload['id']}/file"
    assert listed.json()[0]["parse_status"] == "parsed"
    assert listed.json()[0]["summary"] == "Jane Doe Python Engineer"
    assert "content_preview" not in listed.json()[1]
    assert listed.json()[1]["preview_url"] == f"/resumes/{first_payload['id']}/file"
    assert detail.status_code == 200
    assert "content" not in detail.json()
    assert detail.json()["has_file"] is True
    assert detail.json()["raw_text"] == "Jane Doe\nPython Engineer"
    assert detail.json()["sections"][0]["facts"][0]["keywords"] == ["Python"]


def test_upload_resume_file_endpoint_with_image(
    temporary_app_config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_resume_workflow(monkeypatch)
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)
        response = client.post(
            "/resumes/files",
            data={"selection_id": str(selection_id)},
            files={"file": ("resume.png", b"fake-image", "image/png")},
        )

    assert response.status_code == 200
    payload = _sse_payload(response, "final")["resume"]
    assert "content" not in payload
    assert payload["media_type"] == "image/png"


def test_upload_resume_file_endpoint_returns_404_for_missing_selection(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        response = client.post(
            "/resumes/files",
            data={"selection_id": "999"},
            files={"file": ("resume.png", b"fake-image", "image/png")},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Model selection not found: 999"


def test_upload_resume_file_endpoint_persists_failed_parse_status(
    temporary_app_config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_failing_resume_workflow(monkeypatch)
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)
        response = client.post(
            "/resumes/files",
            data={"selection_id": str(selection_id)},
            files={"file": ("resume.png", b"fake-image", "image/png")},
        )
        error_payload = _sse_payload(response, "error")
        detail = client.get(f"/resumes/{error_payload['resume_id']}")

    assert response.status_code == 200
    assert error_payload["parse_status"] == "failed"
    assert error_payload["detail"] == "extract failed"
    assert detail.status_code == 200
    assert detail.json()["parse_status"] == "failed"
    assert detail.json()["parse_error"] == "extract failed"


def test_upload_resume_file_keeps_parsing_after_stream_disconnect(
    temporary_app_config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SlowResumeExtractWorkflow:
        def __init__(self, config=None) -> None:
            self.config = config

        async def astream_events(self, selection, resume_document, handlers=None):
            if handlers and "on_custom_event" in handlers:
                await handlers["on_custom_event"](
                    {
                        "event": "on_custom_event",
                        "name": "on_progress_update",
                        "data": {"progress": 0.2, "message": "Started."},
                    }
                )
            await asyncio.sleep(0.05)
            return Resume(
                raw_text="parsed after disconnect",
                document=resume_document,
                sections=[],
            )

    monkeypatch.setattr(
        "services.resume_extraction_jobs.ResumeExtractWorkflow",
        SlowResumeExtractWorkflow,
    )
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)
        with client.stream(
            "POST",
            "/resumes/files",
            data={"selection_id": str(selection_id)},
            files={"file": ("resume.png", b"fake-image", "image/png")},
        ) as response:
            assert response.status_code == 200

        listed = client.get("/resumes").json()
        detail = _wait_for_parse_status(client, listed[0]["id"], "parsed")

    assert detail["raw_text"] == "parsed after disconnect"


def test_upload_resume_file_persists_failed_status_after_stream_disconnect(
    temporary_app_config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SlowFailingResumeExtractWorkflow:
        def __init__(self, config=None) -> None:
            self.config = config

        async def astream_events(self, selection, resume_document, handlers=None):
            await asyncio.sleep(0.05)
            raise RuntimeError("failed after disconnect")

    monkeypatch.setattr(
        "services.resume_extraction_jobs.ResumeExtractWorkflow",
        SlowFailingResumeExtractWorkflow,
    )
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)
        with client.stream(
            "POST",
            "/resumes/files",
            data={"selection_id": str(selection_id)},
            files={"file": ("resume.png", b"fake-image", "image/png")},
        ) as response:
            assert response.status_code == 200

        listed = client.get("/resumes").json()
        detail = _wait_for_parse_status(client, listed[0]["id"], "failed")

    assert detail["parse_error"] == "failed after disconnect"


def test_replace_resume_file_does_not_allow_old_job_to_overwrite_new_parse(
    temporary_app_config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FilenameResumeExtractWorkflow:
        def __init__(self, config=None) -> None:
            self.config = config

        async def astream_events(self, selection, resume_document, handlers=None):
            filename = resume_document.original_filename or ""
            if filename == "old.png":
                await asyncio.sleep(0.2)
                raw_text = "old parse result"
            else:
                await asyncio.sleep(0.01)
                raw_text = "new parse result"
            return Resume(raw_text=raw_text, document=resume_document, sections=[])

    monkeypatch.setattr(
        "services.resume_extraction_jobs.ResumeExtractWorkflow",
        FilenameResumeExtractWorkflow,
    )
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)
        with client.stream(
            "POST",
            "/resumes/files",
            data={"selection_id": str(selection_id)},
            files={"file": ("old.png", b"old-image", "image/png")},
        ) as response:
            assert response.status_code == 200

        created_id = client.get("/resumes").json()[0]["id"]

        replaced = client.put(
            f"/resumes/{created_id}/file",
            data={"selection_id": str(selection_id)},
            files={"file": ("new.png", b"new-image", "image/png")},
        )
        replaced_payload = _sse_payload(replaced, "final")["resume"]
        time.sleep(0.25)
        detail = client.get(f"/resumes/{created_id}").json()

    assert replaced_payload["raw_text"] == "new parse result"
    assert detail["raw_text"] == "new parse result"


def test_replace_resume_file_endpoint(
    temporary_app_config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_resume_workflow(monkeypatch)
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)
        created = client.post(
            "/resumes/files",
            data={"selection_id": str(selection_id)},
            files={"file": ("resume.png", b"image-1", "image/png")},
        )
        created_payload = _sse_payload(created, "final")["resume"]
        response = client.put(
            f"/resumes/{created_payload['id']}/file",
            data={"selection_id": str(selection_id)},
            files={"file": ("resume.jpg", b"image-2", "image/jpeg")},
        )

    assert response.status_code == 200
    payload = _sse_payload(response, "final")["resume"]
    assert "content" not in payload
    assert payload["original_filename"] == "resume.jpg"
    assert payload["media_type"] == "image/jpeg"
    assert payload["parse_status"] == "parsed"


def test_preview_resume_file_endpoint(
    temporary_app_config: Config,
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_resume_workflow(monkeypatch)
    app = create_app(temporary_app_config)
    pdf_path = workspace_tmp_dir / "resume.pdf"
    _create_pdf(pdf_path, "Jane Doe Resume")

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)
        with pdf_path.open("rb") as file:
            created = client.post(
                "/resumes/files",
                data={"selection_id": str(selection_id)},
                files={"file": ("resume.pdf", file, "application/pdf")},
            )
        created_payload = _sse_payload(created, "final")["resume"]
        response = client.get(f"/resumes/{created_payload['id']}/file")

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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_resume_workflow(monkeypatch)
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)
        created = client.post(
            "/resumes/files",
            data={"selection_id": str(selection_id)},
            files={"file": ("resume.png", b"fake-image", "image/png")},
        )
        created_payload = _sse_payload(created, "final")["resume"]
        saved_path = _resolve_saved_path(created_payload["file_path"])
        delete_response = client.delete(f"/resumes/{created_payload['id']}")
        get_response = client.get(f"/resumes/{created_payload['id']}")

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
        selection_id = _create_model_selection(client)
        response = client.post(
            "/resumes/files",
            data={"selection_id": str(selection_id)},
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
    assert "文件信息" in list_resumes["description"]

    upload_resume = payload["paths"]["/resumes/files"]["post"]
    assert upload_resume["summary"] == "上传简历文件"
    assert "PDF、DOCX、PNG、JPG 或 JPEG" in upload_resume["description"]
    assert upload_resume["requestBody"]["content"]["multipart/form-data"]["schema"]["$ref"]
    assert "text/event-stream" in upload_resume["responses"]["200"]["content"]
    assert "415" in upload_resume["responses"]
    assert "422" in upload_resume["responses"]

    schemas = payload["components"]["schemas"]
    resume_detail = schemas["ResumeDetail"]
    assert "content" not in resume_detail["properties"]
    assert "content_preview" not in schemas["ResumeListItem"]["properties"]
    assert "parse_status" in resume_detail["properties"]
    assert "raw_text" in resume_detail["properties"]
    assert "sections" in resume_detail["properties"]
    assert resume_detail["properties"]["preview_url"]["examples"][0] == "/resumes/1/file"
    assert "ResumeAdviceRequest" not in schemas
    assert "ResumeAdviceResponse" not in schemas
    assert "/resumes/{resume_id}/advice" not in payload["paths"]
    assert "/resumes/{resume_id}/advice/stream" not in payload["paths"]
