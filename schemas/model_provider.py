from pydantic import BaseModel
from typing import Literal

type Provider = Literal[
    "OpenAI",
    "Google",
    "Anthropic",
    "OpenAI Compatible"
]

class ModelProvider(BaseModel):
    provider: Provider
    name: str
    base_url: str | None = None
    api_key: str | None = None
