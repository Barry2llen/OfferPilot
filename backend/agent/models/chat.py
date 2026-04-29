
from functools import lru_cache
from typing import Any

from langchain.chat_models import BaseChatModel, init_chat_model
from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_deepseek import ChatDeepSeek

from exceptions import ChatModelLoadError
from schemas.model_selection import ModelSelection
from utils.logger import logger


class DeepSeekThinkingChatModel(ChatDeepSeek):
    """DeepSeek chat model that preserves thinking-mode reasoning history."""

    def _get_request_payload(
        self,
        input_: LanguageModelInput,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        messages = self._convert_input(input_).to_messages()
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        payload_messages = payload.get("messages")
        if not isinstance(payload_messages, list):
            return payload

        for source_message, payload_message in zip(messages, payload_messages):
            if not isinstance(source_message, AIMessage):
                continue
            if not isinstance(payload_message, dict):
                continue
            if payload_message.get("role") != "assistant":
                continue

            reasoning_content = source_message.additional_kwargs.get(
                "reasoning_content"
            )
            if isinstance(reasoning_content, str):
                payload_message["reasoning_content"] = reasoning_content

        return payload

def load_chat_model(model_selection: ModelSelection | None) -> BaseChatModel:
    if model_selection is None:
        raise ChatModelLoadError("Model selection is required to load a chat model.")
    return _load_chat_model_cached(
        provider_name=model_selection.provider.provider,
        model_name=model_selection.model_name,
        base_url=model_selection.provider.base_url,
        api_key=model_selection.provider.api_key,
    )


@lru_cache(maxsize=10, typed=True)
def _load_chat_model_cached(
    *,
    provider_name: str,
    model_name: str,
    base_url: str | None,
    api_key: str | None,
) -> BaseChatModel:
    
    from dotenv import load_dotenv
    load_dotenv(override=True)

    required_base_and_key = False

    model_provider = provider_name.lower()
    match model_provider:
        case "openai-compatible" | "openai compatible":
            model_provider = "openai"
            required_base_and_key = True
        case "google":
            model_provider = "google_genai"
        case _:
            pass

    try:
        if model_provider == "deepseek":
            deepseek_kwargs: dict[str, Any] = {"model": model_name}
            if base_url is not None:
                deepseek_kwargs["api_base"] = base_url
            if api_key is not None:
                deepseek_kwargs["api_key"] = api_key
            return DeepSeekThinkingChatModel(**deepseek_kwargs)

        return init_chat_model(
            model_provider=model_provider,
            model=model_name,
            base_url=base_url,
            api_key=api_key,
        ) if required_base_and_key else init_chat_model(
            model_provider=model_provider,
            model=model_name,
        )
    except Exception as e:
        logger.error(f"Error loading chat model for provider {provider_name}: {e}")
        raise ChatModelLoadError(
            f"Error loading chat model for provider {provider_name}: {e}"
        ) from e


load_chat_model.cache_clear = _load_chat_model_cached.cache_clear
