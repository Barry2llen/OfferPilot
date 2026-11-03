import json
from functools import lru_cache
from inspect import signature
from typing import Any, Literal

from langchain.chat_models import BaseChatModel, init_chat_model
from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_deepseek import ChatDeepSeek
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field, SecretStr

from exceptions import ChatModelLoadError
from schemas.model_selection import ModelSelection, google_extra_params
from utils.logger import logger


class GoogleConfiguredChatModel(ChatGoogleGenerativeAI):
    """Apply native generation fields that the LangChain constructor does not forward."""

    request_options: dict[str, Any] = Field(default_factory=dict, exclude=True)
    forced_temperature: float | None = Field(default=None, exclude=True)
    omit_default_temperature: bool = Field(default=False, exclude=True)

    def _prepare_request(self, messages: Any, **kwargs: Any) -> dict[str, Any]:
        request = super()._prepare_request(messages, **kwargs)
        config = request["config"]
        for key, value in self.request_options.items():
            setattr(config, key, value)
        if self.forced_temperature is not None:
            config.temperature = self.forced_temperature
        elif self.omit_default_temperature and "temperature" not in self.request_options:
            config.temperature = None
        return request


class DeepSeekThinkingChatModel(ChatDeepSeek):
    """DeepSeek chat model that preserves thinking-mode reasoning history."""

    def with_structured_output(
        self,
        schema: Any | None = None,
        *,
        method: Literal[
            "function_calling",
            "json_mode",
            "json_schema",
        ] = "function_calling",
        include_raw: bool = False,
        strict: bool | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, Any]:
        if method != "function_calling":
            return super().with_structured_output(
                schema,
                method=method,
                include_raw=include_raw,
                strict=strict,
                **kwargs,
            )

        structured_model = super().with_structured_output(
            schema,
            method="json_mode",
            include_raw=include_raw,
            strict=strict,
            **kwargs,
        )
        return (
            RunnableLambda(
                lambda input_: self._prepend_json_output_instruction(input_, schema)  # type: ignore
            )
            | structured_model
        )

    def _get_request_payload(
        self,
        input_: LanguageModelInput,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        messages = self._convert_input(input_).to_messages()
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        payload_messages = payload.get("messages")
        if not isinstance(payload_messages, list):
            return payload

        for source_message, payload_message in zip(messages, payload_messages):
            if not isinstance(source_message, AIMessage):
                continue
            if not isinstance(payload_message, dict):
                continue
            if payload_message.get("role") != "assistant":
                continue

            reasoning_content = source_message.additional_kwargs.get(
                "reasoning_content"
            )
            if isinstance(reasoning_content, str):
                payload_message["reasoning_content"] = reasoning_content

        return payload

    def _prepend_json_output_instruction(
        self,
        input_: LanguageModelInput,
        schema: Any | None,
    ) -> list[Any]:
        messages = self._convert_input(input_).to_messages()
        return [
            SystemMessage(content=_build_json_output_instruction(schema)),
            *messages,
        ]


def _build_json_output_instruction(schema: Any | None) -> str:
    schema_name = getattr(schema, "__name__", "JSON object")
    example = _json_example_for_schema(schema)
    example_json = json.dumps(example, ensure_ascii=False, indent=2)
    return (
        "Return only one valid json object. Do not include Markdown code fences, "
        "comments, or explanatory text.\n"
        f"The json object must match the {schema_name} structure expected by the "
        "application.\n"
        "EXAMPLE JSON OUTPUT:\n"
        f"{example_json}"
    )


def _json_example_for_schema(schema: Any | None) -> Any:
    if schema is None:
        return {}

    if isinstance(schema, type) and issubclass(schema, BaseModel):
        configured_example = _configured_pydantic_example(schema)
        if configured_example is not None:
            return configured_example
        json_schema = schema.model_json_schema()
        return _example_from_json_schema(json_schema, json_schema)

    if isinstance(schema, dict):
        configured_examples = schema.get("examples")
        if isinstance(configured_examples, list) and configured_examples:
            return configured_examples[0]
        return _example_from_json_schema(schema, schema)

    return {}


def _configured_pydantic_example(schema: type[BaseModel]) -> Any | None:
    json_schema_extra = schema.model_config.get("json_schema_extra")
    if not isinstance(json_schema_extra, dict):
        return None

    examples = json_schema_extra.get("examples")
    if not isinstance(examples, list) or not examples:
        return None

    return examples[0]


def _example_from_json_schema(schema: dict[str, Any], root: dict[str, Any]) -> Any:
    if "$ref" in schema:
        resolved_schema = _resolve_json_schema_ref(schema["$ref"], root)
        if resolved_schema is not None:
            return _example_from_json_schema(resolved_schema, root)

    examples = schema.get("examples")
    if isinstance(examples, list) and examples:
        return examples[0]

    if "default" in schema:
        return schema["default"]

    if "const" in schema:
        return schema["const"]

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return enum_values[0]

    any_of = schema.get("anyOf")
    if isinstance(any_of, list):
        for item in any_of:
            if isinstance(item, dict) and item.get("type") != "null":
                return _example_from_json_schema(item, root)

    schema_type = schema.get("type")
    if schema_type == "object" or "properties" in schema:
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return {}
        return {
            name: _example_from_json_schema(property_schema, root)
            for name, property_schema in properties.items()
            if isinstance(property_schema, dict)
        }
    if schema_type == "array":
        return []
    if schema_type == "boolean":
        return True
    if schema_type == "integer":
        return 0
    if schema_type == "number":
        return 0.0
    if schema_type == "string":
        return "string"
    if schema_type == "null":
        return None

    return {}


def _resolve_json_schema_ref(ref: str, root: dict[str, Any]) -> dict[str, Any] | None:
    prefix = "#/$defs/"
    if not ref.startswith(prefix):
        return None

    definitions = root.get("$defs")
    if not isinstance(definitions, dict):
        return None

    resolved = definitions.get(ref.removeprefix(prefix))
    return resolved if isinstance(resolved, dict) else None


def _openai_model_options(
    extra_params: dict[str, Any], model_class: type[BaseChatModel]
) -> dict[str, Any]:
    from openai.resources.chat.completions import Completions
    from openai.resources.responses import Responses

    native_fields = set(model_class.model_fields)
    native_fields.update(
        field.alias for field in model_class.model_fields.values() if field.alias
    )
    native_fields.update(signature(Completions.create).parameters)
    native_fields.update(signature(Responses.create).parameters)
    options = {key: value for key, value in extra_params.items() if key in native_fields}
    extensions = {
        key: value for key, value in extra_params.items() if key not in native_fields
    }
    if extensions:
        options["extra_body"] = extensions
    return options


def load_chat_model(model_selection: ModelSelection | None, **kwargs) -> BaseChatModel:
    if model_selection is None:
        raise ChatModelLoadError("Model selection is required to load a chat model.")
    return _load_chat_model_cached(
        provider_name=model_selection.provider.provider,
        model_name=model_selection.model_name,
        base_url=model_selection.provider.base_url,
        api_key=model_selection.provider.api_key,
        options_json=json.dumps({"api_mode": model_selection.api_mode, "thinking": model_selection.thinking.model_dump() if model_selection.thinking else None, "extra_params": model_selection.extra_params}, sort_keys=True),
        **kwargs,
    )


@lru_cache(maxsize=10, typed=True)
def _load_chat_model_cached(
    *,
    provider_name: str,
    model_name: str,
    base_url: str | None,
    api_key: str | None,
    options_json: str = "{}",
    _omit_default_temperature: bool = False,
    **kwargs: Any,
) -> BaseChatModel:

    from dotenv import load_dotenv

    load_dotenv(override=True)

    required_base_and_key = False

    model_provider = provider_name.lower()
    match model_provider:
        case "openai-compatible" | "openai compatible":
            model_provider = "openai"
            required_base_and_key = True
        case "google":
            model_provider = "google_genai"
        case _:
            pass

    options = json.loads(options_json)
    extra_params = options.get("extra_params") or {}
    options_kwargs = {} if model_provider == "google_genai" and extra_params else dict(extra_params)
    if extra_params and model_provider in {"openai", "deepseek"}:
        from langchain_openai import ChatOpenAI

        model_class = (
            DeepSeekThinkingChatModel if model_provider == "deepseek" else ChatOpenAI
        )
        options_kwargs = _openai_model_options(extra_params, model_class)
    thinking = options.get("thinking")
    mode = options.get("api_mode", "auto")
    if model_provider == "openai" and mode != "auto":
        options_kwargs["use_responses_api"] = mode == "responses"
    if thinking:
        value, kind = thinking.get("value"), thinking["type"]
        if model_provider == "openai" and value is not None:
            if isinstance(options_kwargs.get("reasoning"), dict):
                options_kwargs["reasoning"] = {**options_kwargs["reasoning"], "effort": value}
            else:
                options_kwargs["reasoning_effort"] = value
        elif model_provider == "google_genai" and value is not None:
            options_kwargs["thinking_level" if kind == "level" else "thinking_budget"] = value
        elif model_provider == "deepseek" and value is not None:
            options_kwargs["extra_body"] = {
                **options_kwargs.get("extra_body", {}),
                "thinking": {"type": "disabled" if value == "disabled" else "enabled"},
            }
            if value != "disabled":
                options_kwargs["reasoning_effort"] = value
        elif model_provider == "anthropic":
            if kind == "adaptive" and value is not None:
                options_kwargs["thinking"] = {"type": "adaptive"}
                options_kwargs["output_config"] = {**options_kwargs.get("output_config", {}), "effort": value}
            elif kind == "budget" and value is not None:
                options_kwargs["thinking"] = {"type": "enabled", "budget_tokens": value}
                options_kwargs["max_tokens"] = thinking["max_tokens"]
    options_kwargs.update(kwargs)

    try:
        if model_provider == "google_genai" and (
            extra_params or _omit_default_temperature
        ):
            return GoogleConfiguredChatModel(
                model=model_name,
                api_key=SecretStr(api_key) if api_key is not None else None,
                request_options=google_extra_params(extra_params),
                forced_temperature=kwargs.get("temperature"),
                omit_default_temperature=_omit_default_temperature,
                **options_kwargs,
            )
        if model_provider == "deepseek":
            deepseek_kwargs: dict[str, Any] = {"model": model_name}
            if base_url is not None:
                deepseek_kwargs["api_base"] = base_url
            if api_key is not None:
                deepseek_kwargs["api_key"] = api_key
            return DeepSeekThinkingChatModel(**deepseek_kwargs, **options_kwargs)

        return (
            init_chat_model(
                model_provider=model_provider,
                model=model_name,
                base_url=base_url,
                api_key=api_key,
                **options_kwargs,
            )
            if required_base_and_key
            else init_chat_model(
                model_provider=model_provider, model=model_name, api_key=api_key, **options_kwargs
            )
        )
    except Exception as e:
        logger.error(f"Error loading chat model for provider {provider_name}: {e}")
        raise ChatModelLoadError(
            f"Error loading chat model for provider {provider_name}: {e}"
        ) from e


load_chat_model.cache_clear = _load_chat_model_cached.cache_clear
