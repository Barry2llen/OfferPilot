import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from sqlalchemy import inspect, text

from agent.models.chat import load_chat_model
from api.routes.ai import ParsedAIChatPayload, _chat_fingerprint
from db.engine import DatabaseManager
from exceptions.agent import ModelRequestConfigurationError
from main import create_app
from schemas.ai import ThinkingOverride
from schemas.config import Config, SQLiteDatabaseConfig
from schemas.model_provider import ModelProvider
from schemas.model_selection import ModelSelection
from services.chat_events import _extract_chunk_reasoning, _extract_chunk_text
from services.chat_runs import apply_thinking_override
from utils.i18n import public_run_error


def selection(provider: str, **kwargs) -> ModelSelection:
    return ModelSelection(
        provider=ModelProvider(provider=provider, name="test", api_key="test"),
        model_name="example",
        **kwargs,
    )


@pytest.mark.parametrize(
    ("provider", "thinking", "expected"),
    [
        ("OpenAI", {"type": "effort", "value": "high"}, {"reasoning_effort": "high"}),
        ("Google", {"type": "level", "value": "low"}, {"thinking_level": "low"}),
        ("Google", {"type": "budget", "value": 1024}, {"thinking_budget": 1024}),
        (
            "Anthropic",
            {"type": "adaptive", "value": "medium"},
            {"thinking": {"type": "adaptive"}, "output_config": {"effort": "medium"}},
        ),
        (
            "Anthropic",
            {"type": "budget", "value": 1024, "max_tokens": 4096},
            {
                "thinking": {"type": "enabled", "budget_tokens": 1024},
                "max_tokens": 4096,
            },
        ),
    ],
)
def test_provider_options_are_passed_to_model(
    monkeypatch, provider, thinking, expected
):
    calls = []
    monkeypatch.setattr(
        "agent.models.chat.init_chat_model",
        lambda **kwargs: calls.append(kwargs) or object(),
    )
    load_chat_model.cache_clear()
    load_chat_model(selection(provider, thinking=thinking))
    for key, value in expected.items():
        assert calls[0][key] == value
    load_chat_model.cache_clear()


def test_protocol_and_cache_include_options(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "agent.models.chat.init_chat_model",
        lambda **kwargs: calls.append(kwargs) or object(),
    )
    load_chat_model.cache_clear()
    load_chat_model(
        selection(
            "OpenAI", api_mode="responses", thinking={"type": "effort", "value": "high"}
        )
    )
    load_chat_model(
        selection(
            "OpenAI",
            api_mode="chat_completions",
            thinking={"type": "effort", "value": "none"},
        )
    )
    assert [item["use_responses_api"] for item in calls] == [True, False]
    assert [item["reasoning_effort"] for item in calls] == ["high", "none"]
    load_chat_model.cache_clear()


def test_responses_payload_preserves_tool_history():
    model = load_chat_model(
        selection(
            "OpenAI", api_mode="responses", thinking={"type": "effort", "value": "high"}
        )
    )
    messages = [
        HumanMessage(content="weather"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "weather",
                    "args": {"city": "Paris"},
                    "id": "call_1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(content="sunny", tool_call_id="call_1"),
    ]
    payload = model._get_request_payload(
        messages,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "weather",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
    )
    assert model._use_responses_api(payload)
    assert payload["reasoning"]["effort"] == "high"
    assert any(item["type"] == "function_call" for item in payload["input"])
    assert any(item["type"] == "function_call_output" for item in payload["input"])
    load_chat_model.cache_clear()


def test_thinking_override_does_not_modify_configuration():
    original = selection("OpenAI", thinking={"type": "effort", "value": "high"})
    assert apply_thinking_override(original, {"value": None}).thinking.value is None
    assert original.thinking.value == "high"
    with pytest.raises(ValueError):
        apply_thinking_override(original, {"value": "invalid"})


def test_thinking_override_changes_submission_fingerprint():
    def payload(value):
        return ParsedAIChatPayload(1, "hello", "thread", None, [], [], thinking_override=value)

    default = _chat_fingerprint(payload(None), True, "zh-CN")
    high = _chat_fingerprint(payload(ThinkingOverride(value="high")), True, "zh-CN")
    provider_default = _chat_fingerprint(payload(ThinkingOverride(value=None)), True, "zh-CN")
    assert len({default, high, provider_default}) == 3


def test_validate_conflicts_and_budget():
    with pytest.raises(ValueError):
        selection("OpenAI", extra_params={"tools": []})
    with pytest.raises(ValueError):
        selection(
            "Anthropic", thinking={"type": "budget", "value": 2048, "max_tokens": 2048}
        )
    selection("OpenAI", extra_params={"reasoning": {"mode": "pro"}})
    with pytest.raises(ValueError):
        selection(
            "Google",
            extra_params={
                "generationConfig": {"thinkingConfig": {"thinkingBudget": 20}}
            },
        )


def test_google_advanced_fields_are_sent_and_structured_temperature_wins():
    selected = selection(
        "Google",
        thinking={"type": "level", "value": "low"},
        extra_params={"generationConfig": {"presencePenalty": 0.4, "temperature": 0.8}},
    )
    model = load_chat_model(selected)
    config = model._prepare_request([HumanMessage(content="hello")])["config"]
    assert config.presence_penalty == 0.4
    assert config.temperature == 0.8
    assert config.thinking_config.thinking_level.value.lower() == "low"
    structured = load_chat_model(selected, temperature=0)
    assert (
        structured._prepare_request([HumanMessage(content="hello")])[
            "config"
        ].temperature
        == 0
    )
    load_chat_model.cache_clear()


def test_old_database_upgrades_twice_without_losing_data(tmp_path):
    manager = DatabaseManager(SQLiteDatabaseConfig(path=str(tmp_path / "old.db")))
    with manager.get_engine().begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE tb_model_provider (name VARCHAR(255) PRIMARY KEY, provider VARCHAR(32) NOT NULL, base_url VARCHAR(255), api_key VARCHAR(255))"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE tb_model_selection (id INTEGER PRIMARY KEY, provider_name VARCHAR(255) NOT NULL, model_name VARCHAR(255) NOT NULL, supports_image_input BOOLEAN NOT NULL DEFAULT FALSE)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO tb_model_selection (id, provider_name, model_name) VALUES (1, 'legacy', 'model')"
            )
        )
    manager.initialize_tables()
    manager.initialize_tables()
    with manager.get_engine().connect() as connection:
        assert {"api_mode", "thinking", "extra_params"} <= {
            c["name"] for c in inspect(connection).get_columns("tb_model_selection")
        }
        assert (
            connection.execute(
                text("SELECT model_name FROM tb_model_selection WHERE id=1")
            ).scalar_one()
            == "model"
        )
    manager.dispose()


def test_model_options_round_trip(temporary_app_config: Config):
    with TestClient(create_app(temporary_app_config)) as client:
        client.post("/model-providers", json={"name": "test", "provider": "OpenAI"})
        created = client.post(
            "/model-selections",
            json={
                "provider_name": "test",
                "model_name": "model",
                "api_mode": "responses",
                "thinking": {"type": "effort", "value": "high"},
                "extra_params": {"top_p": 0.7},
            },
        )
        assert created.status_code == 200
        row = client.get(f"/model-selections/{created.json()['id']}").json()
        assert row["api_mode"] == "responses"
        assert row["thinking"]["value"] == "high"
        assert row["extra_params"] == {"top_p": 0.7}
        updated = client.put(f"/model-selections/{row['id']}", json={"thinking": None})
        assert updated.json()["thinking"] is None
        assert (
            client.put(
                f"/model-selections/{row['id']}", json={"extra_params": {"tools": []}}
            ).status_code
            == 422
        )
        rejected = client.put(
            f"/model-selections/{row['id']}",
            json={"extra_params": {"api_key": "sensitive-value"}},
        )
        assert rejected.status_code == 422
        assert "sensitive-value" not in rejected.text
        assert "高级参数" in rejected.json()["detail"]


def test_bad_request_message_is_localized_and_preserves_provider_detail():
    error = ModelRequestConfigurationError("unsupported reasoning")
    assert "请检查模型设置" in public_run_error(error, "zh-CN")
    assert "unsupported reasoning" in public_run_error(error, "en-US")


@pytest.mark.parametrize(
    "extra_params",
    [
        {"anthropic_api_key": "sensitive-alias-value"},
        {"deepseek_api_key": "sensitive-alias-value"},
        {"custom": {"OpenAI-API-Key": "sensitive-alias-value"}},
        {"custom": [{"google_api_key": "sensitive-alias-value"}]},
    ],
)
def test_advanced_parameters_reject_credential_aliases(extra_params):
    with pytest.raises(ValueError, match="Credentials cannot be stored"):
        selection("Anthropic", extra_params=extra_params)


def test_model_options_api_rejects_credential_alias_without_echoing_or_saving(
    temporary_app_config: Config,
):
    with TestClient(create_app(temporary_app_config)) as client:
        client.post(
            "/model-providers", json={"name": "test", "provider": "Anthropic"}
        )
        payload = {"provider_name": "test", "model_name": "model"}
        created = client.post("/model-selections", json=payload)
        selection_id = created.json()["id"]
        extra = {"anthropic_api_key": "sensitive-alias-value"}
        rejected_create = client.post(
            "/model-selections",
            json={**payload, "model_name": "other", "extra_params": extra},
        )
        rejected_update = client.put(
            f"/model-selections/{selection_id}", json={"extra_params": extra}
        )
        for rejected in (rejected_create, rejected_update):
            assert rejected.status_code == 422
            assert "sensitive-alias-value" not in rejected.text
            assert "高级参数中不能保存凭据" in rejected.json()["detail"]
        listed = client.get("/model-selections")
        assert listed.status_code == 200
        assert len(listed.json()) == 1
        assert listed.json()[0]["extra_params"] == {}


def test_reasoning_blocks_are_not_emitted_as_answer_text():
    reasoning = AIMessageChunk(
        content=[
            {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "thought"}],
            }
        ]
    )
    assert _extract_chunk_text(reasoning) == ""
    assert _extract_chunk_reasoning(reasoning) == "thought"
