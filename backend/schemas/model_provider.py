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
        description="模型供应商类型。",
        examples=["OpenAI"],
    )
    name: str = Field(
        description="模型供应商配置名称，作为后续模型选择的引用键。",
        examples=["default-openai"],
    )
    base_url: str | None = Field(
        default=None,
        description="供应商 API 地址。OpenAI Compatible 通常需要配置；DeepSeek 省略时使用官方默认地址。",
        examples=["https://api.example.com/v1"],
    )
    api_key: str | None = Field(
        default=None,
        description="供应商 API Key。响应不会回显明文。",
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
        description="新的供应商类型。省略时保持原值。",
        examples=["DeepSeek"],
    )
    base_url: str | None = Field(
        default=None,
        description="新的供应商兼容 API 地址。省略时保持原值，传 null 时清空。",
        examples=["https://compatible.example.com/v1"],
    )
    api_key: str | None = Field(
        default=None,
        description="新的 API Key。省略时保留原值，传 null 时清空。",
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
        description="模型供应商类型。",
        examples=["OpenAI"],
    )
    name: str = Field(
        description="模型供应商配置名称。",
        examples=["default-openai"],
    )
    base_url: str | None = Field(
        default=None,
        description="供应商兼容 API 地址。",
        examples=["https://api.example.com/v1"],
    )
    has_api_key: bool = Field(
        description="是否已配置 API Key。不会回显明文密钥。",
        examples=[True],
    )
