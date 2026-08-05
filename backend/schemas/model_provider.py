from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

type Provider = Literal[
    "OpenAI",
    "Google",
    "Anthropic",
    "DeepSeek",
    "OpenAI Compatible",
]


class ModelProvider(BaseModel):
    provider: Provider | str
    name: str
    base_url: str | None = None
    api_key: str | None = None


class ModelProviderCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "provider": "DeepSeek",
                    "name": "default-deepseek",
                    "base_url": None,
                    "api_key": "sk-deepseek-secret",
                }
            ]
        }
    )

    provider: Provider = Field(
        description="Model provider type.",
        examples=["OpenAI"],
    )
    name: str = Field(
        description="Model provider configuration name used as a reference key for model selections.",
        examples=["default-openai"],
    )
    base_url: str | None = Field(
        default=None,
        description="Provider API URL. Usually required for OpenAI Compatible providers; DeepSeek uses its official default when omitted.",
        examples=["https://api.example.com/v1"],
    )
    api_key: str | None = Field(
        default=None,
        description="Provider API key. Responses never expose the key in plaintext.",
        examples=["sk-local-secret"],
    )


class ModelProviderUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "provider": "DeepSeek",
                    "base_url": None,
                    "api_key": None,
                }
            ]
        }
    )

    provider: Provider | None = Field(
        default=None,
        description="New provider type. The current value is kept when omitted.",
        examples=["DeepSeek"],
    )
    base_url: str | None = Field(
        default=None,
        description="New provider-compatible API URL. The current value is kept when omitted and cleared when null is sent.",
        examples=["https://compatible.example.com/v1"],
    )
    api_key: str | None = Field(
        default=None,
        description="New API key. The current value is kept when omitted and cleared when null is sent.",
        examples=["sk-updated-secret"],
    )


class ModelProviderResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "provider": "DeepSeek",
                    "name": "default-deepseek",
                    "base_url": None,
                    "has_api_key": True,
                }
            ]
        }
    )

    provider: Provider | str = Field(
        description="Model provider type.",
        examples=["OpenAI"],
    )
    name: str = Field(
        description="Model provider configuration name.",
        examples=["default-openai"],
    )
    base_url: str | None = Field(
        default=None,
        description="Provider-compatible API URL.",
        examples=["https://api.example.com/v1"],
    )
    has_api_key: bool = Field(
        description="Whether an API key is configured. The key is never returned in plaintext.",
        examples=[True],
    )
