import json

from fastapi.testclient import TestClient

from main import create_app
from schemas.config import Config, ContextCompactionConfig


def test_model_provider_api_crud_and_api_key_masking(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        created = client.post(
            "/model-providers",
            json={
                "provider": "OpenAI",
                "name": "default-openai",
                "api_key": "secret-key",
            },
        )
        duplicate = client.post(
            "/model-providers",
            json={
                "provider": "OpenAI",
                "name": "default-openai",
            },
        )
        listed = client.get("/model-providers")
        detail = client.get("/model-providers/default-openai")
        updated = client.put(
            "/model-providers/default-openai",
            json={
                "provider": "OpenAI Compatible",
                "base_url": "https://compatible.example.com/v1",
            },
        )
        cleared_key = client.put(
            "/model-providers/default-openai",
            json={"api_key": None},
        )
        deleted = client.delete("/model-providers/default-openai")
        missing = client.get("/model-providers/default-openai")

    assert created.status_code == 200
    assert created.json() == {
        "provider": "OpenAI",
        "name": "default-openai",
        "base_url": None,
        "has_api_key": True,
    }
    assert "api_key" not in created.json()
    assert duplicate.status_code == 409
    assert listed.status_code == 200
    assert [item["name"] for item in listed.json()] == ["default-openai"]
    assert detail.status_code == 200
    assert updated.status_code == 200
    assert updated.json()["provider"] == "OpenAI Compatible"
    assert updated.json()["base_url"] == "https://compatible.example.com/v1"
    assert updated.json()["has_api_key"] is True
    assert cleared_key.status_code == 200
    assert cleared_key.json()["has_api_key"] is False
    assert deleted.status_code == 204
    assert missing.status_code == 404


def test_model_selection_api_crud_and_provider_reference_conflict(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        provider = client.post(
            "/model-providers",
            json={
                "provider": "OpenAI",
                "name": "default-openai",
            },
        )
        created = client.post(
            "/model-selections",
            json={
                "provider_name": "default-openai",
                "model_name": "gpt-4o-mini",
                "supports_image_input": True,
            },
        )
        duplicate = client.post(
            "/model-selections",
            json={
                "provider_name": "default-openai",
                "model_name": "gpt-4o-mini",
            },
        )
        referenced_delete = client.delete("/model-providers/default-openai")
        listed = client.get("/model-selections")
        detail = client.get(f"/model-selections/{created.json()['id']}")
        updated = client.put(
            f"/model-selections/{created.json()['id']}",
            json={
                "model_name": "gpt-4.1",
                "supports_image_input": False,
            },
        )
        deleted = client.delete(f"/model-selections/{created.json()['id']}")
        provider_deleted = client.delete("/model-providers/default-openai")
        missing_provider = client.post(
            "/model-selections",
            json={
                "provider_name": "missing-provider",
                "model_name": "gpt-4o-mini",
            },
        )

    assert provider.status_code == 200
    assert created.status_code == 200
    assert created.json()["provider"]["name"] == "default-openai"
    assert created.json()["supports_image_input"] is True
    assert duplicate.status_code == 409
    assert referenced_delete.status_code == 409
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert detail.status_code == 200
    assert updated.status_code == 200
    assert updated.json()["model_name"] == "gpt-4.1"
    assert updated.json()["supports_image_input"] is False
    assert deleted.status_code == 204
    assert provider_deleted.status_code == 204
    assert missing_provider.status_code == 404


def test_model_selection_api_returns_resolved_context_window(
    temporary_app_config: Config,
) -> None:
    config = temporary_app_config.model_copy(
        update={
            "context_compaction": ContextCompactionConfig(
                model_context_windows={"OpenAI:gpt-4o-mini": 64_000},
            )
        }
    )
    app = create_app(config)

    with TestClient(app) as client:
        client.post(
            "/model-providers",
            json={"provider": "OpenAI", "name": "default-openai"},
        )
        selection = client.post(
            "/model-selections",
            json={
                "provider_name": "default-openai",
                "model_name": "gpt-4o-mini",
            },
        )
        listed = client.get("/model-selections")

    assert selection.status_code == 200
    assert selection.json()["context_window_tokens"] == 64_000
    assert listed.status_code == 200
    assert listed.json()[0]["context_window_tokens"] == 64_000


def test_context_compaction_settings_follow_current_or_use_selected_model(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        client.post(
            "/model-providers",
            json={"provider": "OpenAI", "name": "default-openai"},
        )
        selection = client.post(
            "/model-selections",
            json={
                "provider_name": "default-openai",
                "model_name": "gpt-4o-mini",
            },
        )
        initial = client.get("/context-compaction-settings")
        updated = client.patch(
            "/context-compaction-settings",
            json={"model_selection_id": selection.json()["id"]},
        )
        cleared = client.patch(
            "/context-compaction-settings",
            json={"model_selection_id": None},
        )
        invalid = client.patch(
            "/context-compaction-settings",
            json={"model_selection_id": 999},
        )

    assert initial.status_code == 200
    assert initial.json() == {"model_selection_id": None}
    assert updated.status_code == 200
    assert updated.json()["model_selection_id"] == selection.json()["id"]
    assert cleared.status_code == 200
    assert cleared.json() == {"model_selection_id": None}
    assert invalid.status_code == 404


def test_model_provider_api_accepts_deepseek(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        created = client.post(
            "/model-providers",
            json={
                "provider": "DeepSeek",
                "name": "default-deepseek",
                "api_key": "sk-deepseek",
            },
        )

    assert created.status_code == 200
    assert created.json() == {
        "provider": "DeepSeek",
        "name": "default-deepseek",
        "base_url": None,
        "has_api_key": True,
    }


def test_model_config_openapi_metadata(temporary_app_config: Config) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    payload = response.json()
    assert "/model-providers" in payload["paths"]
    assert "/model-selections" in payload["paths"]
    assert "/context-compaction-settings" in payload["paths"]
    assert (
        payload["paths"]["/model-providers"]["post"]["summary"]
        == "Create a model provider"
    )
    assert (
        payload["paths"]["/model-selections"]["post"]["summary"]
        == "Create a model selection"
    )
    assert (
        payload["components"]["schemas"]["ModelSelectionResponse"]["properties"][
            "context_window_tokens"
        ]["description"]
        == "Resolved maximum context window for this model in tokens."
    )
    assert "ModelProviderResponse" in payload["components"]["schemas"]
    assert "DeepSeek" in json.dumps(
        payload["components"]["schemas"]["ModelProviderCreate"],
        ensure_ascii=False,
    )
    assert (
        "Whether an API key is configured"
        in payload["components"]["schemas"]["ModelProviderResponse"]["properties"][
            "has_api_key"
        ]["description"]
    )
