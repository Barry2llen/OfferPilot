
from typing import (
    Protocol,
    Callable,
    overload
)
from dataclasses import dataclass

from langgraph._internal._typing import StateLike
from langchain_core.messages import SystemMessage

from ..base import GraphRuntime, BaseAgentState

type Prompts = (
    list[SystemMessage] |
    list[str]           |
    SystemMessage       |
    str                 
)

class PromptBuilder[State: StateLike = BaseAgentState](Protocol):
    def __call__(self, runtime: GraphRuntime[State]) -> Prompts: ...

class PromptMessageBuilder[State: StateLike = BaseAgentState](Protocol):
    def __call__(self, runtime: GraphRuntime[State]) -> list[SystemMessage]: ...

@dataclass
class PromptFragment[State: StateLike = BaseAgentState]:
    name: str
    content: str | Callable[[GraphRuntime[State]], str]
    enabled: bool | Callable[[GraphRuntime[State]], bool] = True

    def is_enabled(self, runtime: GraphRuntime[State]) -> bool:
        if callable(self.enabled):
            return self.enabled(runtime)
        return self.enabled
    
    def raw_content(self, runtime: GraphRuntime[State]) -> str:
        if callable(self.content):
            return self.content(runtime)
        return self.content
    
    def to_message(self, runtime: GraphRuntime[State]) -> SystemMessage:
        return SystemMessage(content=self.raw_content(runtime).strip())

class PromptComposer[State: StateLike = BaseAgentState]:
    def __init__(self, fragments: list[PromptFragment[State]]):
        self.fragments = fragments

    def raw_prompt(self, runtime: GraphRuntime[State]) -> str:
        return "\n\n".join(
            f"{fragment.name.title()}:\n{fragment.raw_content(runtime).strip()}"
            for fragment in self.fragments
            if fragment.is_enabled(runtime)
        )

    def __call__(self, runtime: GraphRuntime[State]) -> list[SystemMessage]:
        return [SystemMessage(content=self.raw_prompt(runtime))]

@overload
def normalize_system_prompts(
    system_prompts: Prompts | None,
) -> list[SystemMessage]:
    ...

@overload
def normalize_system_prompts[State: StateLike = BaseAgentState](
    system_prompts: PromptBuilder[State],
) -> PromptMessageBuilder[State]:
    ...

def normalize_system_prompts[State: StateLike = BaseAgentState](
    system_prompts: Prompts | PromptBuilder[State] | None,
) -> PromptMessageBuilder[State] | list[SystemMessage]:
    if system_prompts is None:
        return []

    if callable(system_prompts):
        def build_messages(runtime: GraphRuntime[State]) -> list[SystemMessage]:
            normalized = normalize_system_prompts(system_prompts(runtime))
            return normalized(runtime) if callable(normalized) else normalized

        return build_messages

    if isinstance(system_prompts, str):
        prompts = [SystemMessage(content=system_prompts)]

    elif isinstance(system_prompts, SystemMessage):
        prompts = [system_prompts]

    elif isinstance(system_prompts, list):
        if any(not isinstance(prompt, (str, SystemMessage)) for prompt in system_prompts):
            raise ValueError(
                "system_prompts list must contain only str or SystemMessage instances."
            )

        prompts = [
            SystemMessage(content=prompt)
            if isinstance(prompt, str)
            else prompt
            for prompt in system_prompts
        ]

    else:
        raise ValueError(
            "system_prompts must be a str, SystemMessage, list, callable, or None."
        )

    return lambda runtime: prompts

__all__ = [
    "Prompts",
    "PromptBuilder",
    "PromptFragment",
    "PromptComposer",
    "PromptMessageBuilder",
    "normalize_system_prompts",
]
