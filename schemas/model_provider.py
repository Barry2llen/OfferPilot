from pydantic import BaseModel
from typing import Literal

type Provider = Literal[
    "OpenAI",
    "Google",
    "Anthropic",
    "Deepseek"
    "OpenAI Compatible"
]

class ModelProvider(BaseModel):
    provider: Provider | str
    name: str
    base_url: str | None = None
    api_key: str | None = None
