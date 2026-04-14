
from functools import lru_cache

from langchain.chat_models import (
    init_chat_model,
    BaseChatModel
)

from schemas.model_selection import ModelSelection
from utils.logger import logger

@lru_cache(maxsize=10, typed=True)
def load_chat_model(model_selection: ModelSelection) -> BaseChatModel:

    match provider_name := model_selection.provider.name:
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
            raise ValueError(f"Unsupported model provider: {provider_name}")

    try:
        return init_chat_model(
            model_provider=model_provider,
            model=model_selection.model_name,
            base_url=model_selection.provider.base_url,
            api_key=model_selection.provider.api_key
        )
    except Exception as e:
        logger.error(f"Error loading chat model for provider {provider_name}: {e}")
        raise e