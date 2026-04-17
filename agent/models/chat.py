
from functools import lru_cache

from langchain.chat_models import BaseChatModel, init_chat_model

from exceptions import ChatModelLoadError, UnsupportedModelProviderError
from schemas.model_selection import ModelSelection
from utils.logger import logger

def load_chat_model(model_selection: ModelSelection) -> BaseChatModel:
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
    match provider_name:
        case "OpenAI":
            model_provider = "openai"
        case "Anthropic":
            model_provider = "anthropic"
        case "Google":
            model_provider = "google_genai"
        case "OpenAI Compatible":
            model_provider = "openai"
        case _:
            logger.error(f"Unsupported model provider: {provider_name}")
            raise UnsupportedModelProviderError(
                f"Unsupported model provider: {provider_name}"
            )

    try:
        return init_chat_model(
            model_provider=model_provider,
            model=model_name,
            base_url=base_url,
            api_key=api_key,
        )
    except Exception as e:
        logger.error(f"Error loading chat model for provider {provider_name}: {e}")
        raise ChatModelLoadError(
            f"Error loading chat model for provider {provider_name}: {e}"
        ) from e


load_chat_model.cache_clear = _load_chat_model_cached.cache_clear
