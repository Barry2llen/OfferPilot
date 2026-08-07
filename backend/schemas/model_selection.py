from pydantic import BaseModel, ConfigDict, Field

from .model_provider import ModelProvider, ModelProviderResponse


class ModelSelection(BaseModel):
    id: int | None = None
    provider: ModelProvider
    model_name: str
    supports_image_input: bool = False


class ModelSelectionCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "provider_name": "default-openai",
                    "model_name": "gpt-4o-mini",
                    "supports_image_input": True,
                }
            ]
        }
    )

    provider_name: str = Field(
        description="Configured model provider name corresponding to tb_model_provider.name.",
        examples=["default-openai"],
    )
    model_name: str = Field(
        description="Model name.",
        examples=["gpt-4o-mini"],
    )
    supports_image_input: bool = Field(
        default=False,
        description="Whether this model supports image input.",
        examples=[True],
    )


class ModelSelectionUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "provider_name": "compatible-main",
                    "model_name": "custom-model",
                    "supports_image_input": False,
                }
            ]
        }
    )

    provider_name: str | None = Field(
        default=None,
        description="New model provider name. The current value is kept when omitted.",
        examples=["compatible-main"],
    )
    model_name: str | None = Field(
        default=None,
        description="New model name. The current value is kept when omitted.",
        examples=["custom-model"],
    )
    supports_image_input: bool | None = Field(
        default=None,
        description="Whether image input is supported. The current value is kept when omitted.",
        examples=[False],
    )


class ModelSelectionResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": 1,
                    "provider": {
                        "provider": "OpenAI",
                        "name": "default-openai",
                        "base_url": None,
                        "has_api_key": True,
                    },
                    "model_name": "gpt-4o-mini",
                    "supports_image_input": True,
                    "context_window_tokens": 128000,
                }
            ]
        }
    )

    id: int = Field(description="Model selection record ID.", examples=[1])
    provider: ModelProviderResponse = Field(
        description="Expanded model provider configuration summary."
    )
    model_name: str = Field(description="Model name.", examples=["gpt-4o-mini"])
    supports_image_input: bool = Field(
        description="Whether this model supports image input.",
        examples=[True],
    )
    context_window_tokens: int = Field(
        description="Resolved maximum context window for this model in tokens.",
        examples=[128000],
    )
