from __future__ import annotations

from typing import Any, overload, override
from pydantic import BaseModel

from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.language_models import LanguageModelInput

from schemas.model_selection import ModelSelection
from . import load_chat_model

class StructuredModel[Struct: dict[str, Any] |  BaseModel](
    Runnable[LanguageModelInput, Struct]
):
    
    # More methods can be added if needed.

    def __init__(self, model: Runnable[LanguageModelInput, dict[str, Any] | BaseModel]) -> None:
        self._model = model

    @override
    def invoke(
        self,
        input: LanguageModelInput,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Struct:
        return self._model.invoke(input, config=config, **kwargs) # type: ignore[return-value]
    
    @override
    async def ainvoke(
        self,
        input: LanguageModelInput,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Struct:
        return await self._model.ainvoke(input, config=config, **kwargs) # type: ignore[return-value]
    
@overload
def load_structured_model[T: BaseModel](
    model_selection: ModelSelection,
    schema: type[T],
) -> StructuredModel[T]:
    ...

@overload
def load_structured_model(
    model_selection: ModelSelection,
    schema: dict[str, Any],
) -> StructuredModel[dict[str, Any]]:
    ...

def load_structured_model[T: BaseModel](
    model_selection: ModelSelection,
    schema: type[T] | dict[str, Any],
) -> StructuredModel[T] | StructuredModel[dict[str, Any]]:
    structured_model = load_chat_model(model_selection).with_structured_output(schema)
    return StructuredModel(structured_model)

__all__ = [
    "StructuredModel",
    "load_structured_model",
]
