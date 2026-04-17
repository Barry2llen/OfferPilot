from pydantic import BaseModel

from .model_provider import ModelProvider


class ModelSelection(BaseModel):
    id: int | None = None
    provider: ModelProvider
    model_name: str
    supports_image_input: bool = False
