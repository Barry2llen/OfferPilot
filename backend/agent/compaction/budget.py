from __future__ import annotations

from schemas.config.base import ContextCompactionConfig
from schemas.model_selection import ModelSelection
from utils.logger import logger

from .models import ContextBudget
from .protocols import ContextBudgetPolicy


class DefaultContextBudgetPolicy(ContextBudgetPolicy):
    """Resolve model-specific windows into a safe input budget."""

    def __init__(self, config: ContextCompactionConfig) -> None:
        self.config = config

    def resolve(self, model_selection: ModelSelection) -> ContextBudget:
        max_context_tokens = self.resolve_max_context_tokens(model_selection)
        available_input_tokens = (
            max_context_tokens
            - self.config.reserved_output_tokens
            - self.config.safety_margin_tokens
        )
        if available_input_tokens <= 1:
            # The Pydantic config validation protects the default. A custom model
            # window may still be tiny, so fail with a useful invariant here.
            raise ValueError("Model context window leaves no room for input tokens.")

        budget = ContextBudget(
            max_context_tokens=max_context_tokens,
            reserved_output_tokens=self.config.reserved_output_tokens,
            safety_margin_tokens=self.config.safety_margin_tokens,
        )
        provider = getattr(model_selection, "provider", None)
        logger.debug(
            lambda: (
                "Compaction budget resolved: "
                f"provider={getattr(provider, 'provider', 'unknown')}, "
                f"model={getattr(model_selection, 'model_name', 'unknown')}, "
                f"max_context={budget.max_context_tokens}, "
                f"available_input={budget.available_input_tokens}."
            )
        )
        return budget

    def resolve_max_context_tokens(self, model_selection: ModelSelection) -> int:
        model_name = str(getattr(model_selection, "model_name", "") or "")
        provider = getattr(model_selection, "provider", None)
        provider_name = str(getattr(provider, "provider", "") or "")
        provider_config_name = str(getattr(provider, "name", "") or "")
        windows = self.config.model_context_windows

        for key in (
            f"{provider_name}:{model_name}",
            f"{provider_name.lower()}:{model_name}",
            f"{provider_config_name}:{model_name}",
            model_name,
        ):
            if key and key in windows:
                logger.debug(
                    lambda: (
                        "Compaction context window matched configured key: "
                        f"key={key}, window={windows[key]}."
                    )
                )
                return windows[key]
        logger.debug(
            lambda: (
                "Compaction context window fell back to default: "
                f"window={self.config.default_max_context_tokens}."
            )
        )
        return self.config.default_max_context_tokens


__all__ = ["DefaultContextBudgetPolicy"]
