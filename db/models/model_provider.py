
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
    model: str
    name: str
    base_url: str = None
    api_key: str = None
