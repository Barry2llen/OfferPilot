import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.models.chat import DeepSeekThinkingChatModel, load_chat_model
from exceptions import ChatModelLoadError
from schemas.model_provider import ModelProvider
from schemas.model_selection import ModelSelection


def test_load_chat_model_rejects_unsupported_provider() -> None:
    selection = ModelSelection.model_construct(
        provider=ModelProvider.model_construct(
            provider="Unsupported Provider",
            name="demo-provider",
        ),
        model_name="demo-model",
    )

    with pytest.raises(ChatModelLoadError):
        load_chat_model(selection)


def test_load_chat_model_wraps_init_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    selection = ModelSelection(
        provider=ModelProvider(provider="OpenAI", name="demo-provider"),
        model_name="gpt-4o-mini",
    )
    monkeypatch.setattr(
        "agent.models.chat.init_chat_model",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("init failed")),
    )
    load_chat_model.cache_clear()

    with pytest.raises(ChatModelLoadError, match="init failed"):
        load_chat_model(selection)

    load_chat_model.cache_clear()


def test_load_chat_model_uses_deepseek_provider_model() -> None:
    selection = ModelSelection(
        provider=ModelProvider(
            provider="DeepSeek",
            name="default-deepseek",
            api_key="sk-test",
        ),
        model_name="deepseek-reasoner",
    )
    load_chat_model.cache_clear()

    model = load_chat_model(selection)

    assert isinstance(model, DeepSeekThinkingChatModel)
    load_chat_model.cache_clear()


def test_openai_compatible_deepseek_url_does_not_use_deepseek_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[dict] = []
    compatible_model = object()
    selection = ModelSelection(
        provider=ModelProvider(
            provider="OpenAI Compatible",
            name="compatible-deepseek",
            base_url="https://api.deepseek.com/v1",
            api_key="sk-test",
        ),
        model_name="deepseek-reasoner",
    )

    def fake_init_chat_model(**kwargs: object) -> object:
        events.append(kwargs)
        return compatible_model

    monkeypatch.setattr("agent.models.chat.init_chat_model", fake_init_chat_model)
    load_chat_model.cache_clear()

    model = load_chat_model(selection)

    assert model is compatible_model
    assert events == [
        {
            "model_provider": "openai",
            "model": "deepseek-reasoner",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": "sk-test",
        }
    ]
    load_chat_model.cache_clear()


def test_deepseek_payload_passes_back_reasoning_content() -> None:
    model = DeepSeekThinkingChatModel(
        model="deepseek-reasoner",
        api_key="sk-test",
    )
    messages = [
        HumanMessage(content="查一下天气"),
        AIMessage(
            content="",
            additional_kwargs={"reasoning_content": "需要调用天气工具。"},
            tool_calls=[
                {
                    "name": "get_weather",
                    "args": {"city": "北京"},
                    "id": "call-1",
                }
            ],
        ),
        ToolMessage(content="晴，20 摄氏度", tool_call_id="call-1"),
    ]

    payload = model._get_request_payload(messages)

    assert payload["messages"][1]["role"] == "assistant"
    assert payload["messages"][1]["reasoning_content"] == "需要调用天气工具。"
    assert payload["messages"][1]["tool_calls"][0]["id"] == "call-1"
