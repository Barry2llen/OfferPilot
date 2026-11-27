from __future__ import annotations

from schemas.config.base import ContextCompactionConfig
from schemas.model_selection import ModelSelection
from utils.logger import logger

from ..models.output_limits import configured_output_limit
from .models import ContextBudget
from .protocols import ContextBudgetPolicy


class DefaultContextBudgetPolicy(ContextBudgetPolicy):
    """Resolve model-specific windows into a safe input budget."""

    def __init__(self, config: ContextCompactionConfig) -> None:
        self.config = config

    def resolve(self, model_selection: ModelSelection) -> ContextBudget:
        output_limit = configured_output_limit(model_selection)
        budget = ContextBudget(
            max_context_tokens=self.resolve_max_context_tokens(model_selection),
            reserved_output_tokens=max(
                self.config.reserved_output_tokens, output_limit or 0
            ),
            safety_margin_tokens=self.config.safety_margin_tokens,
            trigger_input_ratio=self.config.trigger_input_ratio,
            target_input_ratio=self.config.target_input_ratio,
        )
        provider = getattr(model_selection, "provider", None)
        logger.debug(
            lambda: (
                "Compaction budget resolved: "
                f"provider={getattr(provider, 'provider', 'unknown')}, "
                f"model={getattr(model_selection, 'model_name', 'unknown')}, "
                f"max_context={budget.max_context_tokens}, "
                f"output_limit={output_limit}, output_reserve={budget.reserved_output_tokens}, "
                f"safety_margin={budget.safety_margin_tokens}, "
                f"hard={budget.available_input_tokens}, trigger={budget.trigger_input_tokens}, "
                f"target={budget.target_input_tokens}."
            )
        )
        return budget

    def resolve_summary_input_limit(
        self, model_selection: ModelSelection, output_limit: int
    ) -> int:
        return (
            self.resolve_max_context_tokens(model_selection)
            - output_limit
            - self.config.safety_margin_tokens
        )

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
