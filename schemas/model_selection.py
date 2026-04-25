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
        description="已配置模型供应商名称，对应 tb_model_provider.name。",
        examples=["default-openai"],
    )
    model_name: str = Field(
        description="模型名称。",
        examples=["gpt-4o-mini"],
    )
    supports_image_input: bool = Field(
        default=False,
        description="该模型是否支持图片输入。",
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
        description="新的模型供应商名称。省略时保持原值。",
        examples=["compatible-main"],
    )
    model_name: str | None = Field(
        default=None,
        description="新的模型名称。省略时保持原值。",
        examples=["custom-model"],
    )
    supports_image_input: bool | None = Field(
        default=None,
        description="是否支持图片输入。省略时保持原值。",
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
                }
            ]
        }
    )

    id: int = Field(description="模型选择记录 ID。", examples=[1])
    provider: ModelProviderResponse = Field(description="已展开的模型供应商配置摘要。")
    model_name: str = Field(description="模型名称。", examples=["gpt-4o-mini"])
    supports_image_input: bool = Field(
        description="该模型是否支持图片输入。",
        examples=[True],
    )
