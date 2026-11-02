from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .model_provider import ModelProvider, ModelProviderResponse


class ThinkingSettings(BaseModel):
    type: Literal["effort", "level", "budget", "deepseek", "adaptive"] = Field(
        description="Provider-specific thinking control.", examples=["effort"]
    )
    value: str | int | None = Field(
        default=None,
        description="Thinking value, or null for the provider default.",
        examples=["high"],
    )
    max_tokens: int | None = Field(
        default=None,
        description="Output token limit required by Anthropic budget mode.",
        examples=[8192],
    )


def validate_model_options(
    provider: str,
    api_mode: str,
    thinking: ThinkingSettings | None,
    extra: dict[str, Any],
) -> None:
    provider = provider.lower()
    if (
        provider not in {"openai", "openai compatible", "openai-compatible"}
        and api_mode != "auto"
    ):
        raise ValueError(
            "API mode is only supported by OpenAI and OpenAI Compatible providers"
        )
    allowed = {
        "openai": {"effort"},
        "openai compatible": {"effort"},
        "openai-compatible": {"effort"},
        "google": {"level", "budget"},
        "deepseek": {"deepseek"},
        "anthropic": {"adaptive", "budget"},
    }
    if thinking:
        if thinking.type not in allowed.get(provider, set()):
            raise ValueError("Thinking control is not supported by this provider")
        value = thinking.value
        values = {
            "effort": {"none", "minimal", "low", "medium", "high", "xhigh", "max"},
            "level": {"minimal", "low", "medium", "high"},
            "deepseek": {"disabled", "low", "high", "max"},
            "adaptive": {"low", "medium", "high", "xhigh", "max"},
        }
        if thinking.type == "budget":
            if value is not None and (
                type(value) is not int
                or value < (1024 if provider == "anthropic" else -1)
            ):
                raise ValueError("Invalid thinking token budget")
            if provider == "anthropic" and (
                thinking.max_tokens is None
                or thinking.max_tokens <= 1024
                or (value is not None and value >= thinking.max_tokens)
            ):
                raise ValueError(
                    "Anthropic budget requires max_tokens greater than the budget"
                )
        elif value is not None and value not in values[thinking.type]:
            raise ValueError("Invalid thinking value")
    forbidden = {
        "model",
        "api_key",
        "base_url",
        "messages",
        "input",
        "instructions",
        "tools",
        "tool_choice",
        "stream",
        "streaming",
        "disable_streaming",
        "stream_usage",
        "stream_options",
        "response_format",
        "thinking",
        "thinking_config",
        "thinking_level",
        "thinking_budget",
        "reasoning_effort",
        "extra_body",
        "use_responses_api",
        "use_previous_response_id",
        "model_kwargs",
        "output_version",
        "headers",
        "default_headers",
        "http_client",
        "http_async_client",
        "client",
        "async_client",
        "callbacks",
        "max_retries",
        "timeout",
        "google_api_key",
        "openai_api_key",
    }
    conflicts = forbidden.intersection(extra)
    if conflicts:
        raise ValueError(
            f"Advanced parameters conflict with managed fields: {', '.join(sorted(conflicts))}"
        )
    for key, managed in (
        ("reasoning", {"effort"}),
        ("output_config", {"effort", "format"}),
        ("text", {"format"}),
    ):
        if key in extra:
            if not isinstance(extra[key], dict) or managed.intersection(extra[key]):
                raise ValueError(f"{key} contains managed request fields")
    if (
        provider == "anthropic"
        and thinking
        and thinking.type == "budget"
        and "max_tokens" in extra
    ):
        raise ValueError("max_tokens is managed by the Anthropic budget setting")

    credential_fields = {
        "api_key",
        "apikey",
        "authorization",
        "access_token",
        "auth_token",
        "secret_key",
        "credentials",
    }
    credential_suffixes = tuple(f"_{field}" for field in credential_fields)

    def check_credentials(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized_key = key.lower().replace("-", "_")
                if normalized_key in credential_fields or normalized_key.endswith(
                    credential_suffixes
                ):
                    raise ValueError(
                        "Credentials cannot be stored in advanced parameters"
                    )
                check_credentials(item)
        elif isinstance(value, list):
            for item in value:
                check_credentials(item)

    check_credentials(extra)
    if provider == "google" and extra:
        google_extra_params(extra)


def google_extra_params(extra: dict[str, Any]) -> dict[str, Any]:
    from google.genai.types import GenerateContentConfig

    flattened = dict(extra)
    if "generationConfig" in flattened and "generation_config" in flattened:
        raise ValueError("Specify generationConfig only once")
    nested = flattened.pop("generationConfig", None)
    if nested is None:
        nested = flattened.pop("generation_config", {})
    if not isinstance(nested, dict):
        raise ValueError("generationConfig must be an object")
    validated = GenerateContentConfig.model_validate({**flattened, **nested})
    managed = {
        "system_instruction",
        "tools",
        "tool_config",
        "thinking_config",
        "http_options",
        "response_schema",
        "response_json_schema",
        "response_mime_type",
        "automatic_function_calling",
    }
    if managed.intersection(validated.model_fields_set):
        raise ValueError("Google advanced parameters contain managed fields")
    return {name: getattr(validated, name) for name in validated.model_fields_set}


class ModelSelection(BaseModel):
    id: int | None = None
    provider: ModelProvider
    model_name: str
    supports_image_input: bool = False
    api_mode: Literal["auto", "responses", "chat_completions"] = "auto"
    thinking: ThinkingSettings | None = None
    extra_params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_options(self) -> "ModelSelection":
        validate_model_options(
            self.provider.provider, self.api_mode, self.thinking, self.extra_params
        )
        return self


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
    api_mode: Literal["auto", "responses", "chat_completions"] = Field(
        default="auto", description="OpenAI API protocol.", examples=["responses"]
    )
    thinking: ThinkingSettings | None = Field(
        default=None, description="Provider-specific default thinking settings."
    )
    extra_params: dict[str, Any] = Field(
        default_factory=dict, description="Additional provider request body parameters."
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
    api_mode: Literal["auto", "responses", "chat_completions"] | None = Field(
        default=None, description="OpenAI API protocol."
    )
    thinking: ThinkingSettings | None = Field(
        default=None,
        description="Provider-specific default thinking settings; null clears them.",
    )
    extra_params: dict[str, Any] | None = Field(
        default=None, description="Additional provider request body parameters."
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
    api_mode: Literal["auto", "responses", "chat_completions"] = Field(
        default="auto", description="OpenAI API protocol."
    )
    thinking: ThinkingSettings | None = Field(
        default=None, description="Provider-specific default thinking settings."
    )
    extra_params: dict[str, Any] = Field(
        default_factory=dict, description="Additional provider request body parameters."
    )
