from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from schemas.query import QueryAnswer, QueryRequest


class PendingInputIdentity(BaseModel):
    request_id: str = Field(description="Input request ID.", examples=["request-001"])
    run_id: str = Field(description="Owning run ID.", examples=["run-001"])
    thread_id: str = Field(description="Conversation ID.", examples=["thread-001"])
    tool_call_id: str | None = Field(
        description="Owning tool call, if any.", examples=["call-001", None]
    )
    source: str = Field(description="Requesting agent.", examples=["supervisor"])


class PendingQueryInput(QueryRequest, PendingInputIdentity):
    pass


class PendingErrorInput(PendingInputIdentity):
    type: Literal["error"] = Field(
        default="error", description="Retry request after an error.", examples=["error"]
    )
    message: str | None = Field(
        default=None,
        description="Localized error for the user.",
        examples=["The model call failed. Please retry."],
    )


type PendingInput = Annotated[
    PendingQueryInput | PendingErrorInput, Field(discriminator="type")
]


class RetryAnswer(BaseModel):
    model_config = {"extra": "forbid"}
    type: Literal["retry"] = Field(
        description="Retry the failed operation in the existing run.",
        examples=["retry"],
    )


class InputAnswer(BaseModel):
    answer: QueryAnswer | RetryAnswer = Field(
        description="Dynamic query selections/free text/note or an error retry command.",
        examples=[
            {"selected_option_ids": ["revise"], "free_text": None, "note": None},
            {"type": "retry"},
        ],
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
    pending_inputs: list[PendingInput] = Field(
        default_factory=list,
        description="Outstanding dynamic query or retry requests, identified by request_id and tool_call_id. Query requests preserve selection mode and every option on reconnect.",
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
