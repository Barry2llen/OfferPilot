
from typing import (
    Protocol,
    Callable
)
from dataclasses import dataclass

from langchain_core.messages import SystemMessage

from ..graphs.base import Runtime

type Prompts = (
    list[SystemMessage] |
    list[str]           |
    SystemMessage       |
    str                 
)

class PromptBuilder(Protocol):
    def __call__(self, runtime: Runtime) -> Prompts: ...

@dataclass
class PromptFragment:
    name: str
    content: str | Callable[[Runtime], str]
    enabled: bool | Callable[[Runtime], bool] = True

    def is_enabled(self, runtime: Runtime) -> bool:
        if callable(self.enabled):
            return self.enabled(runtime)
        return self.enabled
    
    def raw_content(self, runtime: Runtime) -> str:
        if callable(self.content):
            return self.content(runtime)
        return self.content
    
    def to_message(self, runtime: Runtime) -> SystemMessage:
        return SystemMessage(content=self.raw_content(runtime).strip())

class PromptComposer:
    def __init__(self, fragments: list[PromptFragment]):
        self.fragments = fragments

    def __call__(self, runtime: Runtime) -> list[SystemMessage]:
        
        prompt = "\n".join(
            f"{fragment.name}:\n{fragment.raw_content(runtime).strip()}"
            for fragment in self.fragments
            if fragment.is_enabled(runtime)
        )

        return [SystemMessage(content=prompt)]
    
def default_system_prompt_builder(runtime: Runtime) -> list[SystemMessage]:
    return []

def normalize_system_prompts(
    system_prompts: Prompts | PromptBuilder | None,
) -> PromptBuilder:
    if system_prompts is None:
        return lambda runtime: []

    if callable(system_prompts):
        return system_prompts

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
    "normalize_system_prompts",
]