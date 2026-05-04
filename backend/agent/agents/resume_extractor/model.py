from pydantic import BaseModel, Field

class TextValidation(BaseModel):
    """
    Validation schema for the extracted resume raw text.
    """
    is_valid: bool = Field(description="Whether the extracted resume raw text is valid or not.")
    reason: str | None = Field(default=None, description="The reason for the validation result.")

__all__ = ["TextValidation"]