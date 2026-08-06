from pydantic import BaseModel, Field


class ContextCompactionSettingsResponse(BaseModel):
    model_selection_id: int | None = Field(
        default=None,
        description=(
            "Optional model selection used for auto-compaction. Null follows the current conversation model."
        ),
        examples=[None, 1],
    )


class ContextCompactionSettingsUpdate(BaseModel):
    model_selection_id: int | None = Field(
        description=(
            "Model selection ID for auto-compaction, or null to follow the current conversation model."
        ),
        examples=[None, 1],
    )


__all__ = [
    "ContextCompactionSettingsResponse",
    "ContextCompactionSettingsUpdate",
]
