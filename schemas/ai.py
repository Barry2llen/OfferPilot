from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AIChatCommand(BaseModel):
    type: Literal["prompt", "continue", "retry"] = Field(
        description="流式会话命令类型。prompt 表示新输入，retry 表示恢复上一次失败中断并重试。",
        examples=["retry"],
    )
    prompt: str | None = Field(
        default=None,
        description="命令附带的文本。prompt 命令未提供时使用请求体顶层 prompt；retry 可省略。",
        examples=["请继续处理。"],
    )


class AIChatRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "selection_id": 1,
                    "prompt": "请帮我总结这份简历的优势。",
                    "thread_id": "conversation-001",
                }
            ]
        }
    )

    selection_id: int = Field(
        description="模型选择记录 ID，对应 tb_model_selection.id。",
        examples=[1],
    )
    prompt: str = Field(
        min_length=1,
        description="用户输入的文本消息。",
        examples=["请帮我总结这份简历的优势。"],
    )
    thread_id: str | None = Field(
        default=None,
        description="会话线程 ID。传入时续聊；省略时由服务端生成。",
        examples=["conversation-001"],
    )


class AIChatResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "thread_id": "conversation-001",
                    "content": "这份简历的主要优势是项目经历完整、技术栈清晰。",
                }
            ]
        }
    )

    thread_id: str = Field(
        description="本次请求使用的会话线程 ID。",
        examples=["conversation-001"],
    )
    content: str = Field(
        description="AI 最终回复文本。",
        examples=["这份简历的主要优势是项目经历完整、技术栈清晰。"],
    )


class AIChatStreamRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "selection_id": 1,
                    "prompt": "请帮我总结这份简历的优势。",
                    "thread_id": "conversation-001",
                },
                {
                    "selection_id": 1,
                    "thread_id": "conversation-001",
                    "command": {"type": "retry"},
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
        min_length=1,
        description="用户输入的文本消息。首次流式调用必填；retry 命令可省略。",
        examples=["请帮我总结这份简历的优势。"],
    )
    thread_id: str | None = Field(
        default=None,
        description="会话线程 ID。retry 命令必须传入上一次中断返回的线程 ID。",
        examples=["conversation-001"],
    )
    command: AIChatCommand | None = Field(
        default=None,
        description="流式会话命令。省略时按 prompt 命令处理；retry 用于恢复失败中断。",
        examples=[{"type": "retry"}],
    )

    @model_validator(mode="after")
    def validate_stream_command(self) -> "AIChatStreamRequest":
        command_type = self.command.type if self.command else "prompt"
        command_prompt = self.command.prompt if self.command else None

        if command_type == "retry":
            if not self.thread_id:
                raise ValueError("thread_id is required when command.type is retry")
            return self

        if not (command_prompt or self.prompt):
            raise ValueError("prompt is required for stream prompt commands")

        return self
