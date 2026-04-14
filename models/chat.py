
from functools import lru_cache

from langchain.chat_models import (
    init_chat_model,
    BaseChatModel
)

from db.models import ModelProvider
from utils.logger import logger

@lru_cache(maxsize=1)
def load_chat_models(providers: list[ModelProvider]) -> dict[str, BaseChatModel]:

    model_providers = {
        "OpenAI": "openai",
        "Google": "google_genai",
        "Anthropic": "anthropic",
    }

    @lru_cache(maxsize=None, typed=True)
    def load_chat_model(provider: ModelProvider) -> BaseChatModel:
        try:
            return init_chat_model(
                model_provider=model_providers.get(provider.provider, "openai"),
                model=provider.model,
                base_url=provider.base_url,
                api_key=provider.api_key
            )
        except Exception as e:
            logger.error(f"Error loading chat model for provider {provider.provider}: {e}")
            return None

    return {provider.name: load_chat_model(provider) for provider in providers if load_chat_model(provider) is not None}