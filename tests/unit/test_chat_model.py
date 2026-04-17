import pytest

from agent.models.chat import load_chat_model
from exceptions import ChatModelLoadError, UnsupportedModelProviderError
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

    with pytest.raises(UnsupportedModelProviderError, match="Unsupported model provider"):
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
