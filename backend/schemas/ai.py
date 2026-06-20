from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from schemas.chat_file import ChatAttachmentRef


class AIChatCommand(BaseModel):
    type: Literal["prompt", "continue", "retry", "query"] = Field(
        description=(
            "流式会话命令类型。prompt 表示新输入，retry 表示恢复上一次失败中断并重试，"
            "query 表示回传 query 工具中断的用户选择。"
        ),
        examples=["query"],
    )
    prompt: str | None = Field(
        default=None,
        description="命令附带的文本。prompt 命令未提供时使用请求体顶层 prompt；retry/query 可省略。",
        examples=["请继续处理。"],
    )
    choice: Literal["firstChoice", "secondChoice", "thirdChoice", "other"] | None = Field(
        default=None,
        description="query 命令回传的用户选择。仅 command.type=query 时必填。",
        examples=["firstChoice"],
    )
    note: str | None = Field(
        default=None,
        description="query 命令回传的补充说明；可附加到任意用户选择。",
        examples=["我更想先看成本最低的方案。"],
    )


class AIChatRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "selection_id": 1,
                    "prompt": "请帮我总结这份简历的优势。",
                    "thread_id": "conversation-001",
                    "file_ids": ["A1B2C3"],
                }
            ]
        }
    )

    selection_id: int = Field(
        description="模型选择记录 ID，对应 tb_model_selection.id。",
        examples=[1],
    )
    prompt: str | None = Field(
        default=None,
        description="用户输入的文本消息。带附件请求可省略，纯文本请求必填。",
        examples=["请帮我总结这份简历的优势。"],
    )
    thread_id: str | None = Field(
        default=None,
        description="会话线程 ID。传入时续聊；省略时由服务端生成。",
        examples=["conversation-001"],
    )
    file_ids: list[str] = Field(
        default_factory=list,
        description="需要在当前请求中复用的历史文件 ID 列表。",
        examples=[["A1B2C3"]],
    )


class AIChatResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "thread_id": "conversation-001",
                    "content": "这份简历的主要优势是项目经历完整、技术栈清晰。",
                },
                {
                    "thread_id": "conversation-002",
                    "content": [
                        {
                            "type": "text",
                            "text": "你好！有什么我可以帮您的吗？",
                            "index": 0,
                            "extras": {},
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/png;base64,iVBORw0KGgo="
                            },
                            "index": 1,
                            "extras": {},
                        },
                    ],
                }
            ]
        }
    )

    thread_id: str = Field(
        description="本次请求使用的会话线程 ID。",
        examples=["conversation-001"],
    )
    content: Any = Field(
        description="AI 最终回复内容。字符串会原样返回，文字、图片等结构化内容块会保持 JSON 结构。",
        examples=[
            "这份简历的主要优势是项目经历完整、技术栈清晰。",
            [
                {
                    "type": "text",
                    "text": "你好！有什么我可以帮您的吗？",
                    "index": 0,
                    "extras": {},
                }
            ],
        ],
    )


class AIChatHistoryMessage(BaseModel):
    role: str = Field(
        description="消息角色。human 映射为 user，ai 映射为 assistant，tool 保持为 tool。",
        examples=["assistant"],
    )
    type: str = Field(
        description="LangChain 消息类型。",
        examples=["ai"],
    )
    content: Any = Field(
        description="消息内容。用户消息会返回对用户可见的 display_content，隐藏附件正文不会暴露给前端。",
        examples=["这份简历的主要优势是项目经历完整、技术栈清晰。"],
    )
    attachments: list[ChatAttachmentRef] | None = Field(
        default=None,
        description="用户消息关联的附件列表。仅用户消息存在附件时返回。",
    )
    reasoning: str | None = Field(
        default=None,
        description="模型推理或工具调用前的中间思考内容，前端应折叠展示。",
        examples=["我需要先检索最新资料。"],
    )
    reasoning_duration_ms: int | None = Field(
        default=None,
        description="模型产生推理内容的调用耗时，单位毫秒。仅存在 reasoning 时返回。",
        examples=[12000],
    )
    name: str | None = Field(
        default=None,
        description="消息名称，通常用于工具消息或带名称的模型消息。",
        examples=["web_search_exa"],
    )
    tool_call_id: str | None = Field(
        default=None,
        description="工具调用 ID，仅工具消息存在时返回。",
        examples=["call-001"],
    )
    status: str | None = Field(
        default=None,
        description="工具消息状态，例如 success 或 error。",
        examples=["success"],
    )


class AIChatHistorySummary(BaseModel):
    thread_id: str = Field(
        description="会话线程 ID。",
        examples=["conversation-001"],
    )
    title: str = Field(
        description="会话标题，默认取首条用户消息并截断。",
        examples=["请帮我总结这份简历的优势。"],
    )
    last_message_preview: str = Field(
        description="最后一条消息内容预览。",
        examples=["这份简历的主要优势是项目经历完整、技术栈清晰。"],
    )
    message_count: int = Field(
        description="当前最新 checkpoint 中的消息数量。",
        examples=[2],
    )
    attachment_count: int = Field(
        default=0,
        description="当前线程已关联的唯一附件数量。",
        examples=[1],
    )
    requires_image_input: bool = Field(
        default=False,
        description="当前线程是否已包含 image 模式附件，用于前端提示仅文本模型可能无法继续利用原始图片内容。",
        examples=[True],
    )
    updated_at: datetime = Field(
        description="会话最新 checkpoint 创建时间。",
        examples=["2026-04-25T20:00:00"],
    )


class AIChatHistoryListResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "thread_id": "conversation-001",
                            "title": "请帮我总结这份简历的优势。",
                            "last_message_preview": "这份简历的主要优势是项目经历完整、技术栈清晰。",
                            "message_count": 2,
                            "attachment_count": 1,
                            "requires_image_input": True,
                            "updated_at": "2026-04-25T20:00:00",
                        }
                    ],
                    "limit": 20,
                    "offset": 0,
                }
            ]
        }
    )

    items: list[AIChatHistorySummary] = Field(
        description="会话历史摘要列表，按最近更新时间倒序排列。",
    )
    limit: int = Field(
        description="本次查询的分页大小。",
        examples=[20],
    )
    offset: int = Field(
        description="本次查询的分页偏移量。",
        examples=[0],
    )


class AIChatHistoryDetailResponse(AIChatHistorySummary):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "thread_id": "conversation-001",
                    "title": "请帮我总结这份简历的优势。",
                    "last_message_preview": "这份简历的主要优势是项目经历完整、技术栈清晰。",
                    "message_count": 2,
                    "attachment_count": 1,
                    "requires_image_input": False,
                    "updated_at": "2026-04-25T20:00:00",
                    "messages": [
                        {
                            "role": "user",
                            "type": "human",
                            "content": "请帮我总结这份简历的优势。",
                            "attachments": [
                                {
                                    "file_id": "A1B2C3",
                                    "original_filename": "resume.pdf",
                                    "media_type": "application/pdf",
                                    "injection_mode": "image",
                                }
                            ],
                        },
                        {
                            "role": "assistant",
                            "type": "ai",
                            "content": "这份简历的主要优势是项目经历完整、技术栈清晰。",
                        },
                    ],
                }
            ]
        }
    )

    messages: list[AIChatHistoryMessage] = Field(
        description="当前会话最新 checkpoint 中保存的完整消息列表。",
    )


class AIChatStreamRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "selection_id": 1,
                    "prompt": "请帮我总结这份简历的优势。",
                    "thread_id": "conversation-001",
                    "file_ids": ["A1B2C3"],
                },
                {
                    "selection_id": 1,
                    "thread_id": "conversation-001",
                    "command": {"type": "retry"},
                },
                {
                    "selection_id": 1,
                    "thread_id": "conversation-001",
                    "command": {
                        "type": "query",
                        "choice": "firstChoice",
                        "note": "按推荐方案继续。",
                    },
                },
            ]
        }
    )

    selection_id: int = Field(
        description="模型选择记录 ID，对应 tb_model_selection.id。",
        examples=[1],
    )
    prompt: str | None = Field(
        default=None,
        description="用户输入的文本消息。带附件请求可省略；retry 命令可省略。",
        examples=["请帮我总结这份简历的优势。"],
    )
    thread_id: str | None = Field(
        default=None,
        description="会话线程 ID。retry/query 命令必须传入上一次中断返回的线程 ID。",
        examples=["conversation-001"],
    )
    file_ids: list[str] = Field(
        default_factory=list,
        description="需要在当前请求中复用的历史文件 ID 列表。",
        examples=[["A1B2C3"]],
    )
    command: AIChatCommand | None = Field(
        default=None,
        description="流式会话命令。省略时按 prompt 命令处理；retry 用于恢复失败中断；query 用于恢复用户选择中断。",
        examples=[{"type": "query", "choice": "firstChoice", "note": "按推荐方案继续。"}],
    )

    @model_validator(mode="after")
    def validate_stream_command(self) -> "AIChatStreamRequest":
        command_type = self.command.type if self.command else "prompt"

        if command_type in {"retry", "query"}:
            if not self.thread_id:
                raise ValueError(f"thread_id is required when command.type is {command_type}")
            if command_type == "query" and self.command and self.command.choice is None:
                raise ValueError("choice is required when command.type is query")
            return self

        return self
