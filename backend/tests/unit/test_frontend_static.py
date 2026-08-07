from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import create_app
from schemas.config import Config


def _create_frontend_dist(path: Path) -> Path:
    assets_dir = path / "assets"
    assets_dir.mkdir(parents=True)
    (path / "index.html").write_text(
        '<!doctype html><html><body><div id="root">OfferPilot SPA</div></body></html>',
        encoding="utf-8",
    )
    (assets_dir / "app.js").write_text("console.log('OfferPilot');", encoding="utf-8")
    return path


def test_frontend_static_files_and_spa_navigation_are_served(
    workspace_tmp_dir: Path,
) -> None:
    frontend_dist = _create_frontend_dist(workspace_tmp_dir / "frontend-dist")
    client = TestClient(create_app(Config(), frontend_dist=frontend_dist))

    root_response = client.get("/")
    asset_response = client.get("/assets/app.js")
    deep_route_response = client.get("/resumes/123", headers={"accept": "text/html"})
    unknown_route_response = client.get(
        "/unknown-route", headers={"accept": "text/html"}
    )
    missing_asset_response = client.get("/assets/missing.js")
    missing_api_response = client.patch("/resumes/123/text", json={})

    assert root_response.status_code == 200
    assert "OfferPilot SPA" in root_response.text
    assert root_response.headers["cache-control"] == "no-store"
    assert "Sec-Fetch-Dest" in root_response.headers["vary"]
    assert asset_response.status_code == 200
    assert asset_response.text == "console.log('OfferPilot');"
    assert deep_route_response.status_code == 200
    assert "OfferPilot SPA" in deep_route_response.text
    assert unknown_route_response.status_code == 200
    assert "OfferPilot SPA" in unknown_route_response.text
    assert missing_asset_response.status_code == 404
    assert missing_api_response.status_code == 404
    assert missing_api_response.json() == {"detail": "Not Found"}


def test_frontend_mount_keeps_fastapi_routes_available(
    workspace_tmp_dir: Path,
) -> None:
    frontend_dist = _create_frontend_dist(workspace_tmp_dir / "frontend-dist")
    client = TestClient(create_app(Config(), frontend_dist=frontend_dist))

    health_response = client.get("/health")
    docs_response = client.get("/docs")
    openapi_response = client.get("/openapi.json")

    assert health_response.status_code == 200
    assert health_response.json() == {"message": "Hello World!"}
    assert docs_response.status_code == 200
    assert openapi_response.status_code == 200
    assert "paths" in openapi_response.json()


def test_spa_navigation_does_not_mask_json_api_requests(
    workspace_tmp_dir: Path,
    temporary_app_config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def empty_supervisor_tools(config: Config | None = None) -> list:
        return []

    monkeypatch.setattr("main.get_supervisor_tools", empty_supervisor_tools)
    frontend_dist = _create_frontend_dist(workspace_tmp_dir / "frontend-dist")
    app = create_app(temporary_app_config, frontend_dist=frontend_dist)

    with TestClient(app) as client:
        html_response = client.get(
            "/resumes",
            headers={
                "accept": "text/html",
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
            },
        )
        list_response = client.get(
            "/resumes",
            headers={
                "accept": "text/html",
                "content-type": "application/json",
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
            },
        )
        detail_response = client.get(
            "/resumes/123",
            headers={
                "accept": "text/html",
                "content-type": "application/json",
                "accept-language": "en-US",
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
            },
        )

    assert html_response.status_code == 200
    assert "OfferPilot SPA" in html_response.text
    assert list_response.status_code == 200
    assert list_response.json() == []
    assert detail_response.status_code == 404
    assert detail_response.json() == {"detail": "Resume not found: 123"}


def test_frontend_dist_can_be_selected_from_environment(
    monkeypatch,
    workspace_tmp_dir: Path,
) -> None:
    frontend_dist = _create_frontend_dist(workspace_tmp_dir / "frontend-dist")
    monkeypatch.setenv("OFFER_PILOT_FRONTEND_DIST", str(frontend_dist))
    app = create_app(Config())

    client = TestClient(app)

    assert app.state.frontend_dist == frontend_dist.resolve()
    assert client.get("/").status_code == 200


def test_missing_frontend_dist_does_not_prevent_api_app_creation(
    workspace_tmp_dir: Path,
) -> None:
    app = create_app(Config(), frontend_dist=workspace_tmp_dir / "missing-dist")
    client = TestClient(app)

    response = client.get("/health")

    assert app.state.frontend_dist is None
    assert response.status_code == 200
