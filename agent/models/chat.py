
from functools import lru_cache

from langchain.chat_models import BaseChatModel, init_chat_model

from exceptions import ChatModelLoadError
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
    
    from dotenv import load_dotenv
    load_dotenv(override=True)

    required_base_and_key = False

    model_provider = provider_name.lower()
    match model_provider:
        case "openai-compatible":
            model_provider = "openai"
            required_base_and_key = True
        case "google":
            model_provider = "google_genai"
        case _:
            pass

    try:
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
