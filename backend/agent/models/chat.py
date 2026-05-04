
import json
from functools import lru_cache
from typing import Any, Literal

from langchain.chat_models import BaseChatModel, init_chat_model
from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_deepseek import ChatDeepSeek
from pydantic import BaseModel

from exceptions import ChatModelLoadError
from schemas.model_selection import ModelSelection
from utils.logger import logger


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
        return RunnableLambda(
            lambda input_: self._prepend_json_output_instruction(input_, schema)
        ) | structured_model

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
        return [SystemMessage(content=_build_json_output_instruction(schema)), *messages]


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


def load_chat_model(model_selection: ModelSelection | None) -> BaseChatModel:
    if model_selection is None:
        raise ChatModelLoadError("Model selection is required to load a chat model.")
    return _load_chat_model_cached(
        provider_name=model_selection.provider.provider,
        model_name=model_selection.model_name,
        base_url=model_selection.provider.base_url,
        api_key=model_selection.provider.api_key,
    )


@lru_cache(maxsize=10, typed=True)
def _load_chat_model_cached(
    *,
    provider_name: str,
    model_name: str,
    base_url: str | None,
    api_key: str | None,
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

    try:
        if model_provider == "deepseek":
            deepseek_kwargs: dict[str, Any] = {"model": model_name}
            if base_url is not None:
                deepseek_kwargs["api_base"] = base_url
            if api_key is not None:
                deepseek_kwargs["api_key"] = api_key
            return DeepSeekThinkingChatModel(**deepseek_kwargs)

        return init_chat_model(
            model_provider=model_provider,
            model=model_name,
            base_url=base_url,
            api_key=api_key,
        ) if required_base_and_key else init_chat_model(
            model_provider=model_provider,
            model=model_name,
        )
    except Exception as e:
        logger.error(f"Error loading chat model for provider {provider_name}: {e}")
        raise ChatModelLoadError(
            f"Error loading chat model for provider {provider_name}: {e}"
        ) from e


load_chat_model.cache_clear = _load_chat_model_cached.cache_clear
