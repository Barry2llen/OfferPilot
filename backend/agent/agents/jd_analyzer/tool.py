from langchain.tools import tool
from pydantic import Field


@tool("mark_jd_extraction_success", return_direct=True)
async def mark_jd_extraction_success(
    jd_text: str = Field(
        ...,
        description=(
            "The complete original job description text extracted from the provided "
            "text, URL, image input, or OCR text. Do not summarize or rewrite it."
        ),
    ),
) -> str:
    """
    Use this tool when the complete original JD text has been successfully obtained.
    """

    return jd_text


@tool("mark_jd_extraction_failure", return_direct=True)
async def mark_jd_extraction_failure(
    reason: str = Field(
        ...,
        description=(
            "Brief reason why a complete, reliable JD could not be obtained from "
            "the provided sources."
        ),
    ),
) -> str:
    """
    Use this tool when the provided sources are insufficient or unreliable for JD extraction.
    """

    return reason


__all__ = [
    "mark_jd_extraction_success",
    "mark_jd_extraction_failure",
]
