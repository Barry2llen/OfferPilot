from pathlib import Path

import fitz
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk

from db.models import ModelProviderORM, ModelSelectionORM
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


class _FakeResumeAdviceGraph:
    def __init__(self, events: list[dict]) -> None:
        self._events = events

    async def astream_events(self, _: dict):
        for event in self._events:
            yield event


def _create_model_selection(
    app,
    *,
    selection_id: int = 1,
    provider_name: str = "google-main",
    supports_image_input: bool = True,
) -> int:
    with app.state.database.session_scope() as session:
        session.add(ModelProviderORM(name=provider_name, provider="google"))
        session.flush()
        selection = ModelSelectionORM(
            id=selection_id,
            provider_name=provider_name,
            model_name="gemini-2.5-pro",
            supports_image_input=supports_image_input,
        )
        session.add(selection)
        session.flush()
        return selection.id


def _build_resume_advice_events(
    *,
    tokens: list[str] | None = None,
    final_content: str = "建议补充量化成果，并压缩项目描述。",
) -> list[dict]:
    events: list[dict] = []
    for token in tokens or []:
        events.append(
            {
                "event": "on_chat_model_stream",
                "data": {"chunk": AIMessageChunk(content=token)},
            }
        )
    events.append(
        {
            "event": "on_chain_end",
            "data": {"output": {"messages": [AIMessage(content=final_content)]}},
        }
    )
    return events


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
        DocumentParserService,
        "extract_text",
        lambda self, _: next(parsed_values),
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


def test_generate_resume_advice_endpoint_returns_completed_response(
    temporary_app_config: Config,
    monkeypatch,
) -> None:
    app = create_app(temporary_app_config)
    monkeypatch.setattr(DocumentParserService, "extract_text", lambda self, _: "Jane Doe Resume")
    monkeypatch.setattr(
        "services.resume_advice_service.resume_advice",
        lambda **_: _FakeResumeAdviceGraph(_build_resume_advice_events()),
    )

    with TestClient(app) as client:
        model_selection_id = _create_model_selection(app)
        created = client.post(
            "/resumes/files",
            files={"file": ("resume.png", b"fake-image", "image/png")},
        )
        response = client.post(
            f"/resumes/{created.json()['id']}/advice",
            json={"model_selection_id": model_selection_id, "user_prompt": "帮我优化"},
        )

    assert created.status_code == 200
    assert response.status_code == 200
    assert response.json() == {
        "resume_id": created.json()["id"],
        "model_selection_id": model_selection_id,
        "content": "建议补充量化成果，并压缩项目描述。",
    }


def test_stream_resume_advice_endpoint_returns_sse_events(
    temporary_app_config: Config,
    monkeypatch,
) -> None:
    app = create_app(temporary_app_config)
    monkeypatch.setattr(DocumentParserService, "extract_text", lambda self, _: "Jane Doe Resume")
    monkeypatch.setattr(
        "services.resume_advice_service.resume_advice",
        lambda **_: _FakeResumeAdviceGraph(
            _build_resume_advice_events(
                tokens=["先补充量化成果", "，再突出岗位匹配度"],
                final_content="先补充量化成果，再突出岗位匹配度",
            )
        ),
    )

    with TestClient(app) as client:
        model_selection_id = _create_model_selection(app)
        created = client.post(
            "/resumes/files",
            files={"file": ("resume.png", b"fake-image", "image/png")},
        )
        with client.stream(
            "POST",
            f"/resumes/{created.json()['id']}/advice/stream",
            json={"model_selection_id": model_selection_id},
        ) as response:
            body = "".join(response.iter_text())
            content_type = response.headers["content-type"]

    assert created.status_code == 200
    assert response.status_code == 200
    assert content_type.startswith("text/event-stream")
    assert 'event: token' in body
    assert 'data: {"content": "先补充量化成果"}' in body
    assert 'event: done' in body
    assert '"model_selection_id": 1' in body
    assert '"content": "先补充量化成果，再突出岗位匹配度"' in body


def test_resume_advice_endpoints_return_404_for_missing_resume(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        model_selection_id = _create_model_selection(app)
        sync_response = client.post(
            "/resumes/999/advice",
            json={"model_selection_id": model_selection_id},
        )
        stream_response = client.post(
            "/resumes/999/advice/stream",
            json={"model_selection_id": model_selection_id},
        )

    assert sync_response.status_code == 404
    assert stream_response.status_code == 404


def test_resume_advice_endpoints_return_404_for_missing_model_selection(
    temporary_app_config: Config,
    monkeypatch,
) -> None:
    app = create_app(temporary_app_config)
    monkeypatch.setattr(DocumentParserService, "extract_text", lambda self, _: "Jane Doe Resume")

    with TestClient(app) as client:
        created = client.post(
            "/resumes/files",
            files={"file": ("resume.png", b"fake-image", "image/png")},
        )
        sync_response = client.post(
            f"/resumes/{created.json()['id']}/advice",
            json={"model_selection_id": 999},
        )
        stream_response = client.post(
            f"/resumes/{created.json()['id']}/advice/stream",
            json={"model_selection_id": 999},
        )

    assert created.status_code == 200
    assert sync_response.status_code == 404
    assert stream_response.status_code == 404


def test_resume_advice_endpoints_reject_models_without_image_input_support(
    temporary_app_config: Config,
    monkeypatch,
) -> None:
    app = create_app(temporary_app_config)
    monkeypatch.setattr(DocumentParserService, "extract_text", lambda self, _: "Jane Doe Resume")

    with TestClient(app) as client:
        model_selection_id = _create_model_selection(app, supports_image_input=False)
        created = client.post(
            "/resumes/files",
            files={"file": ("resume.png", b"fake-image", "image/png")},
        )
        sync_response = client.post(
            f"/resumes/{created.json()['id']}/advice",
            json={"model_selection_id": model_selection_id},
        )
        stream_response = client.post(
            f"/resumes/{created.json()['id']}/advice/stream",
            json={"model_selection_id": model_selection_id},
        )

    assert created.status_code == 200
    assert sync_response.status_code == 422
    assert stream_response.status_code == 422


def test_generate_resume_advice_endpoint_returns_404_when_resume_file_is_missing(
    temporary_app_config: Config,
    monkeypatch,
) -> None:
    app = create_app(temporary_app_config)
    monkeypatch.setattr(DocumentParserService, "extract_text", lambda self, _: "Jane Doe Resume")

    with TestClient(app) as client:
        model_selection_id = _create_model_selection(app)
        created = client.post(
            "/resumes/files",
            files={"file": ("resume.png", b"fake-image", "image/png")},
        )
        saved_path = _resolve_saved_path(created.json()["file_path"])
        saved_path.unlink()
        response = client.post(
            f"/resumes/{created.json()['id']}/advice",
            json={"model_selection_id": model_selection_id},
        )

    assert created.status_code == 200
    assert response.status_code == 404


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
    assert "简历优化建议接口" in payload["tags"][0]["description"]

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

    advice = payload["paths"]["/resumes/{resume_id}/advice"]["post"]
    assert advice["summary"] == "生成简历优化建议"
    assert "model_selection_id" in advice["description"]
    assert advice["parameters"][0]["name"] == "resume_id"
    assert "简历记录 ID" in advice["parameters"][0]["description"]
    assert "404" in advice["responses"]
    assert "422" in advice["responses"]
    assert "500" in advice["responses"]

    stream_advice = payload["paths"]["/resumes/{resume_id}/advice/stream"]["post"]
    assert stream_advice["summary"] == "流式生成简历优化建议"
    assert "event: token" in stream_advice["description"]
    assert "text/event-stream" in stream_advice["responses"]["200"]["content"]

    schemas = payload["components"]["schemas"]
    advice_request = schemas["ResumeAdviceRequest"]
    assert "模型配置 ID" in advice_request["properties"]["model_selection_id"]["description"]
    assert advice_request["properties"]["user_prompt"]["examples"][0].startswith("请重点")

    resume_detail = schemas["ResumeDetail"]
    assert "完整文本内容" in resume_detail["properties"]["content"]["description"]
    assert resume_detail["properties"]["preview_url"]["examples"][0] == "/resumes/1/file"
