"""Resolve provider generation limits without changing the saved model selection."""

from copy import deepcopy
from typing import Any

from schemas.model_selection import ModelSelection, google_extra_params

_OPENAI_PROVIDERS = {"openai", "openai compatible", "openai-compatible"}
_OPENAI_LIMITS = ("max_tokens", "max_completion_tokens", "max_output_tokens")
_ANTHROPIC_LIMITS = ("max_tokens", "max_tokens_to_sample")


class OutputLimitError(ValueError):
    """A generation ceiling cannot be applied by the selected adapter."""


def _native_limit_keys(provider: str) -> tuple[str, ...]:
    if provider in _OPENAI_PROVIDERS or provider == "deepseek":
        return _OPENAI_LIMITS
    if provider == "anthropic":
        return _ANTHROPIC_LIMITS
    return ()


def _positive_limit(key: str, value: Any) -> int:
    if type(value) is not int or value <= 0:
        raise OutputLimitError(f"{key} must be a positive integer when configured.")
    return value


def configured_output_limit(selection: ModelSelection) -> int | None:
    provider = selection.provider.provider.lower()
    raw = selection.extra_params
    if provider == "google":
        params = google_extra_params(raw)
        value = params.get("max_output_tokens")
        return None if value is None else _positive_limit("max_output_tokens", value)
    limits = [
        _positive_limit(key, raw[key])
        for key in _native_limit_keys(provider)
        if raw.get(key) is not None
    ]
    thinking_budget = _anthropic_thinking_budget(selection)
    if thinking_budget is not None:
        assert selection.thinking is not None
        limits.append(
            _positive_limit("thinking.max_tokens", selection.thinking.max_tokens)
        )
        if min(limits) <= thinking_budget:
            raise OutputLimitError(
                "max_tokens must exceed the Anthropic thinking budget."
            )
    # LangChain maps one constructor limit to the selected OpenAI wire protocol.
    # Normalize aliases together so the lowest configured ceiling is honored.
    return min(limits, default=None)


def provider_extra_params(selection: ModelSelection) -> dict[str, Any]:
    provider = selection.provider.provider.lower()
    limit = configured_output_limit(selection)
    keys = _native_limit_keys(provider)
    if not keys:
        return selection.extra_params
    params = {
        key: value for key, value in selection.extra_params.items() if key not in keys
    }
    if limit is not None:
        params["max_tokens"] = limit
    return params


def summary_output_selection(selection: ModelSelection, limit: int) -> ModelSelection:
    """Apply the summary ceiling to the same native fields used in chat requests."""
    limit = _positive_limit("Summary generation limit", limit)
    provider = selection.provider.provider.lower()
    params = deepcopy(selection.extra_params)
    thinking = selection.thinking
    if provider == "google":
        for key in (
            "max_output_tokens",
            "maxOutputTokens",
            "candidate_count",
            "candidateCount",
        ):
            params.pop(key, None)
            for container in ("generationConfig", "generation_config"):
                nested = params.get(container)
                if isinstance(nested, dict):
                    nested.pop(key, None)
        params["max_output_tokens"] = limit
    elif keys := _native_limit_keys(provider):
        params.pop("n", None)
        for key in keys:
            params.pop(key, None)
        thinking_budget = _anthropic_thinking_budget(selection)
        if thinking_budget is not None:
            if limit <= thinking_budget:
                raise OutputLimitError(
                    "Summary generation limit must exceed the Anthropic thinking budget."
                )
            assert thinking is not None
            thinking = thinking.model_copy(update={"max_tokens": limit})
        else:
            params["max_tokens"] = limit
    else:
        raise OutputLimitError(
            "The summary provider does not have a supported generation-limit adapter."
        )
    return selection.model_copy(update={"extra_params": params, "thinking": thinking})


def summary_thinking_reserve(selection: ModelSelection) -> int:
    return _anthropic_thinking_budget(selection) or 0


def _anthropic_thinking_budget(selection: ModelSelection) -> int | None:
    thinking = selection.thinking
    if (
        selection.provider.provider.lower() == "anthropic"
        and thinking is not None
        and thinking.type == "budget"
        and isinstance(thinking.value, int)
    ):
        return thinking.value
    return None
