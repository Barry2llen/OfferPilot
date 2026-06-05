import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from main import create_app
from schemas.config import Config
from schemas.job_description import (
    JobDescription,
    JdFact,
    JdRequirementBlock,
)


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
            "supports_image_input": True,
        },
    )

    assert provider.status_code == 200
    assert selection.status_code == 200
    return selection.json()["id"]


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


def _fake_job_description(raw_text: str = "岗位职责：负责后端服务开发。") -> JobDescription:
    return JobDescription(
        raw_text=raw_text,
        source_url="https://example.com/jobs/123",
        company_name="示例科技",
        job_title="后端开发工程师",
        primary_location="上海",
        remote_policy_raw="不接受居家办公",
        employment_type_raw="全职",
        experience_raw="3年以上后端开发经验",
        education_raw="本科及以上",
        education_min_rank=2,
        blocks=[
            JdRequirementBlock(
                block_type="responsibility",
                title="岗位职责",
                content="负责后端服务开发。",
                facts=[
                    JdFact(
                        fact_type="responsibility",
                        importance="responsibility",
                        text="负责后端服务开发",
                        evidence="负责后端服务开发。",
                        keywords=["后端"],
                    )
                ],
            )
        ],
    )


def _install_fake_jd_workflow(monkeypatch: pytest.MonkeyPatch, captured: dict | None = None) -> None:
    class FakeJdAnalysisWorkflow:
        def __init__(self, config=None) -> None:
            self.config = config

        async def astream_events(
            self,
            selection,
            jd_text=None,
            source_url=None,
            images=None,
            handlers=None,
            event_filter=None,
            event_stream_options=None,
        ):
            if captured is not None:
                captured["selection"] = selection
                captured["jd_text"] = jd_text
                captured["source_url"] = source_url
                captured["images"] = images
                captured["event_filter"] = event_filter
                captured["event_stream_options"] = event_stream_options
            if handlers and "on_custom_event" in handlers:
                await handlers["on_custom_event"](
                    {
                        "event": "on_custom_event",
                        "name": "on_progress_update",
                        "data": {
                            "progress": 0.4,
                            "message": "Extracting JD structure.",
                            "additional_data": {"block_count": 1},
                        },
                    }
                )
            return _fake_job_description(jd_text or "岗位职责：负责后端服务开发。")

    monkeypatch.setattr(
        "services.jd_analysis_jobs.JdAnalysisWorkflow",
        FakeJdAnalysisWorkflow,
    )


def _install_failing_jd_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingJdAnalysisWorkflow:
        def __init__(self, config=None) -> None:
            self.config = config

        async def astream_events(
            self,
            selection,
            jd_text=None,
            source_url=None,
            images=None,
            handlers=None,
            event_filter=None,
            event_stream_options=None,
        ):
            raise RuntimeError("jd analysis failed")

    monkeypatch.setattr(
        "services.jd_analysis_jobs.JdAnalysisWorkflow",
        FailingJdAnalysisWorkflow,
    )


def test_analyze_job_description_with_text_persists_result(
    temporary_app_config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_jd_workflow(monkeypatch)
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)
        response = client.post(
            "/job-descriptions",
            data={
                "selection_id": str(selection_id),
                "jd_text": "岗位职责：负责后端服务开发。",
            },
        )
        final_payload = _sse_payload(response, "final")["job_description"]
        detail = client.get(f"/job-descriptions/{final_payload['id']}")
        listed = client.get("/job-descriptions")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: progress" in response.text
    assert final_payload["status"] == "parsed"
    assert final_payload["job_title"] == "后端开发工程师"
    assert final_payload["company_name"] == "示例科技"
    assert final_payload["block_count"] == 1
    assert final_payload["fact_count"] == 1
    assert detail.status_code == 200
    assert detail.json()["raw_text"] == "岗位职责：负责后端服务开发。"
    assert detail.json()["result"]["remote_policy_raw"] == "不接受居家办公"
    assert detail.json()["result"]["employment_type_raw"] == "全职"
    assert detail.json()["result"]["education_min_rank"] == 2
    assert detail.json()["result"]["blocks"][0]["facts"][0]["keywords"] == ["后端"]
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == final_payload["id"]


def test_analyze_job_description_with_url_passes_source_url(
    temporary_app_config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}
    _install_fake_jd_workflow(monkeypatch, captured)
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)
        response = client.post(
            "/job-descriptions",
            data={
                "selection_id": str(selection_id),
                "source_url": "https://example.com/jobs/123",
            },
        )

    assert response.status_code == 200
    assert captured["source_url"] == "https://example.com/jobs/123"
    assert captured["event_filter"] is not None
    assert captured["event_stream_options"] == {
        "exclude_types": ["chat_model", "llm", "parser"]
    }


def test_analyze_job_description_with_uploaded_image(
    temporary_app_config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}
    _install_fake_jd_workflow(monkeypatch, captured)
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)
        response = client.post(
            "/job-descriptions",
            data={"selection_id": str(selection_id)},
            files={"files": ("jd.png", b"fake-image", "image/png")},
        )
        payload = _sse_payload(response, "final")["job_description"]
        files = client.get("/ai/files")

    assert response.status_code == 200
    assert captured["images"][0].startswith("data:image/png;base64,")
    assert payload["source_image_file_ids"]
    assert files.status_code == 200
    assert files.json()[0]["id"] == payload["source_image_file_ids"][0]


def test_analyze_job_description_with_existing_image_file(
    temporary_app_config: Config,
    workspace_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}
    _install_fake_jd_workflow(monkeypatch, captured)
    app = create_app(temporary_app_config)
    image_path = workspace_tmp_dir / "jd.jpg"
    image_path.write_bytes(b"existing-image")

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)
        with app.state.database.session_scope() as session:
            session.execute(
                text(
                    "INSERT INTO tb_chat_file "
                    "(id, storage_path, original_filename, media_type, size_bytes) "
                    "VALUES ('JDIMG1', :path, 'jd.jpg', 'image/jpeg', 14)"
                ),
                {"path": str(image_path)},
            )

        response = client.post(
            "/job-descriptions",
            data={
                "selection_id": str(selection_id),
                "file_ids[]": "JDIMG1",
            },
        )
        payload = _sse_payload(response, "final")["job_description"]

    assert response.status_code == 200
    assert captured["images"][0].startswith("data:image/jpeg;base64,")
    assert payload["source_image_file_ids"] == ["JDIMG1"]


def test_analyze_job_description_rejects_empty_input(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)
        response = client.post(
            "/job-descriptions",
            data={"selection_id": str(selection_id)},
        )

    assert response.status_code == 422
    assert "JD text, source URL, or at least one image is required." in response.json()["detail"]


def test_analyze_job_description_returns_404_for_missing_selection(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        response = client.post(
            "/job-descriptions",
            data={
                "selection_id": "999",
                "jd_text": "岗位职责：负责后端服务开发。",
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Model selection not found: 999"


def test_analyze_job_description_returns_404_for_missing_file_id(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)
        response = client.post(
            "/job-descriptions",
            data={
                "selection_id": str(selection_id),
                "file_ids[]": "NOFILE",
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Chat file not found: NOFILE"


def test_analyze_job_description_rejects_non_image_file(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)
        response = client.post(
            "/job-descriptions",
            data={"selection_id": str(selection_id)},
            files={"files": ("jd.txt", b"plain text", "text/plain")},
        )

    assert response.status_code == 415
    assert "Unsupported JD image file type" in response.json()["detail"]


def test_analyze_job_description_persists_failed_status(
    temporary_app_config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_failing_jd_workflow(monkeypatch)
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)
        response = client.post(
            "/job-descriptions",
            data={
                "selection_id": str(selection_id),
                "jd_text": "岗位职责：负责后端服务开发。",
            },
        )
        error_payload = _sse_payload(response, "error")
        detail = client.get(f"/job-descriptions/{error_payload['analysis_id']}")

    assert response.status_code == 200
    assert error_payload["status"] == "failed"
    assert error_payload["detail"] == "jd analysis failed"
    assert detail.status_code == 200
    assert detail.json()["status"] == "failed"
    assert detail.json()["error_message"] == "jd analysis failed"


def test_delete_job_description_analysis(
    temporary_app_config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_jd_workflow(monkeypatch)
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)
        created = client.post(
            "/job-descriptions",
            data={
                "selection_id": str(selection_id),
                "jd_text": "岗位职责：负责后端服务开发。",
            },
        )
        analysis_id = _sse_payload(created, "final")["job_description"]["id"]
        delete_response = client.delete(f"/job-descriptions/{analysis_id}")
        get_response = client.get(f"/job-descriptions/{analysis_id}")

    assert delete_response.status_code == 204
    assert get_response.status_code == 404


def test_openapi_json_contains_job_description_docs(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    payload = response.json()

    tags = {tag["name"]: tag["description"] for tag in payload["tags"]}
    assert "job-descriptions" in tags
    assert "JD 分析接口" in tags["job-descriptions"]

    paths = payload["paths"]
    assert paths["/job-descriptions"]["get"]["summary"] == "列出 JD 分析历史"
    assert paths["/job-descriptions"]["post"]["summary"] == "创建并流式分析 JD"
    assert "text/event-stream" in paths["/job-descriptions"]["post"]["responses"]["200"]["content"]
    assert paths["/job-descriptions/{analysis_id}"]["get"]["summary"] == "获取 JD 分析详情"
    assert paths["/job-descriptions/{analysis_id}"]["delete"]["summary"] == "删除 JD 分析记录"

    schemas = payload["components"]["schemas"]
    assert "JobDescriptionAnalysisDetail" in schemas
    assert "JobDescriptionAnalysisListItem" in schemas
