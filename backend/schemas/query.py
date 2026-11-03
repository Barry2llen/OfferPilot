"""Shared contracts for dynamic user decisions and their validated answers."""

from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

type QuerySelectionMode = Literal["single", "multiple"]
type QueryText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class QueryOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: QueryText = Field(
        description="Unique option identifier within this question.",
        examples=["revise"],
    )
    label: QueryText = Field(
        description="User-facing option label.", examples=["Revise my resume"]
    )
    description: QueryText = Field(
        description="Short explanation of when this option is appropriate.",
        examples=["Improve the resume before applying."],
    )


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["query"] = Field(
        default="query", description="User decision request.", examples=["query"]
    )
    question: QueryText = Field(
        description="Specific question the user must answer.",
        examples=["What should we do next?"],
    )
    selection_mode: QuerySelectionMode = Field(
        description="Whether the user may choose one option or multiple options.",
        examples=["single", "multiple"],
    )
    options: list[QueryOption] = Field(
        min_length=2,
        description="Two or more options with unique IDs; the first is recommended.",
        examples=[
            [
                {"id": "revise", "label": "Revise", "description": "Improve first."},
                {"id": "apply", "label": "Apply", "description": "Apply now."},
            ]
        ],
    )

    @model_validator(mode="after")
    def unique_option_ids(self) -> Self:
        if len({option.id for option in self.options}) != len(self.options):
            raise ValueError("Invalid query request.")
        return self


class QueryAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_option_ids: list[QueryText] = Field(
        default_factory=list,
        description="Selected IDs from the pending question; may be empty for free text.",
        examples=[["revise"], []],
    )
    free_text: str | None = Field(
        default=None,
        description="Alternative answer; may accompany selections only in multiple mode.",
        examples=["Prepare for an interview instead."],
    )
    note: str | None = Field(
        default=None,
        description="Optional supplementary explanation; cannot be the only answer.",
        examples=["Focus on my recent experience."],
    )

    @field_validator("free_text", "note")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None

    @model_validator(mode="after")
    def valid_answer(self) -> Self:
        if (not self.selected_option_ids and not self.free_text) or len(
            set(self.selected_option_ids)
        ) != len(self.selected_option_ids):
            raise ValueError("Invalid query answer.")
        return self

    def for_request(self, request: QueryRequest) -> Self:
        """Validate ownership/cardinality and canonicalize selection order for retries."""
        selected = set(self.selected_option_ids)
        available = {option.id for option in request.options}
        if not selected <= available or (
            request.selection_mode == "single"
            and (len(selected) > 1 or bool(selected and self.free_text))
        ):
            raise ValueError("Invalid query answer.")
        return self.model_copy(
            update={
                "selected_option_ids": [
                    option.id for option in request.options if option.id in selected
                ]
            }
        )
