from fastapi.testclient import TestClient

from main import create_app
from schemas.config import Config


def test_cors_preflight_is_enabled_for_all_routes() -> None:
    app = create_app(Config())
    client = TestClient(app)

    response = client.options(
        "/ai/chat",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert "POST" in response.headers["access-control-allow-methods"]
    assert response.headers["access-control-allow-headers"] == "content-type,authorization"
