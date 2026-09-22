from typing import Any, Literal

from pydantic import BaseModel, Field


class QueryAnswer(BaseModel):
    model_config = {"extra": "forbid"}
    choice: Literal["firstChoice", "secondChoice", "thirdChoice", "other"] = Field(
        description="Selected option or a free-form response.", examples=["firstChoice"]
    )
    note: str | None = Field(
        default=None,
        description="Optional additional user text.",
        examples=["Use the shorter version."],
    )


class RetryAnswer(BaseModel):
    model_config = {"extra": "forbid"}
    type: Literal["retry"] = Field(
        description="Retry the failed operation in the existing run.",
        examples=["retry"],
    )


class InputAnswer(BaseModel):
    answer: QueryAnswer | RetryAnswer = Field(
        description="Query choice/note or an error retry command.",
        examples=[{"choice": "firstChoice", "note": None}, {"type": "retry"}],
    )


class ChatRunResponse(BaseModel):
    run_id: str = Field(
        description="Application run ID, distinct from callback run IDs.",
        examples=["abc123"],
    )
    thread_id: str = Field(
        description="Conversation ID.", examples=["conversation-001"]
    )
    status: Literal[
        "queued",
        "running",
        "waiting_input",
        "completed",
        "failed",
        "cancelled",
        "interrupted",
    ] = Field(description="Execution status.", examples=["waiting_input"])
    sequence: int = Field(description="Submission order.", examples=[1])
    prompt: str = Field(
        description="Submitted user text.", examples=["Review my resume."]
    )
    message_id: str = Field(
        description="Submitted human message ID for snapshot/history reconciliation.",
        examples=["message-001"],
    )
    selection_id: int = Field(description="Submitted model selection ID.", examples=[1])
    detail: str | None = Field(
        default=None,
        description="Terminal error or cancellation reason.",
        examples=[None],
    )
    pending_inputs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Outstanding requests identified by request_id and tool_call_id.",
        examples=[[]],
    )
    last_event_id: int = Field(
        description="Latest event sequence for this run.", examples=[10]
    )
    resolved_attachments: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Attachments accepted for this submission.",
        examples=[[]],
    )
    requires_image_input: bool = Field(
        default=False,
        description="Whether this conversation requires image support.",
        examples=[False],
    )
    attachment_count: int = Field(
        default=0, description="Number of attached files.", examples=[0]
    )
