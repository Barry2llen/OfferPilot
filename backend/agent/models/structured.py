from __future__ import annotations

from typing import Any, Callable, overload, override
from pydantic import BaseModel, ValidationError

from langchain_core.exceptions import OutputParserException
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import BaseMessage, AIMessage, SystemMessage

from schemas.model_selection import ModelSelection
from utils.logger import logger
from utils.json import jsonify
from .chat import load_chat_model

class StructuredModel[Struct: dict[str, Any] |  BaseModel](
    Runnable[LanguageModelInput, Struct]
):
    
    # More methods can be added if needed.

    def __init__(
        self,
        model: Runnable[LanguageModelInput, dict[str, Any] | BaseModel],
        schema: type[Struct] | dict[str, Any] | None = None,
    ) -> None:
        self._model = model
        self._schema = schema

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
        checker: Callable[[Struct], Any] | None = None,
        max_repair_attempts: int = 0,
        **kwargs: Any,
    ) -> Struct: # pyright: ignore[reportReturnType]
        """
        Invoke the structured model asynchronously.

        When `max_repair_attempts` is greater than 0 and `input` is a
        `list[BaseMessage]`, Pydantic `ValidationError`s and LangChain
        `OutputParserException`s from the wrapped model, plus exceptions raised
        by `checker`, are treated as structured-output validation failures. The
        failed output, when available, and validation error are appended to the
        message list before retrying.

        Other exceptions from the wrapped model are not retried and are raised
        unchanged. Non-message-list inputs are invoked once because they cannot
        be safely extended with repair instructions.

        Args:
            input: Input passed to the wrapped structured model.
            config: Optional runnable configuration.
            checker: Optional post-validation hook. It should raise when the
                parsed result is semantically invalid.
            max_repair_attempts: Number of repair retries after the initial
                attempt. Must be non-negative.
            **kwargs: Additional keyword arguments forwarded to the wrapped
                model.
        """

        def optimize_error_message(error: Exception) -> str:
            _type = 'txt'
            if isinstance(error, ValidationError):
                res = error.json(include_url=False)
                _type = 'json'
            elif isinstance(error, OutputParserException):
                res = str(error)
            else:
                res = repr(error)
            return (
                    "Your previous output failed validation.\n\n"
                    f"Details:\n```{_type}\n{res}\n```\n\n"
                    "Please return a corrected schema."
                )

        if max_repair_attempts < 0:
            raise ValueError("max_repair_attempts must be non-negative")

        if checker is None and max_repair_attempts == 0:
            return await self._model.ainvoke(input, config=config, **kwargs) # type: ignore[return-value]

        if not isinstance(input, list) or not all(isinstance(i, BaseMessage) for i in input):
            logger.warning("Input is not list[BaseMessage] typed, skipping schema conformance check and repair.")
            result = await self._model.ainvoke(input, config=config, **kwargs)
            if checker is not None:
                checker(result) # type: ignore[arg-type]
            return result # type: ignore[return-value]

        repaired_input = input

        for attempt in range(max_repair_attempts + 1):
            result: dict[str, Any] | BaseModel | None = None
            try:
                logger.debug(f"Invoking structured model, attempt {attempt + 1}/{max_repair_attempts + 1}:\n{jsonify(repaired_input)}")
                result = await self._model.ainvoke(repaired_input, config=config, **kwargs)
            except (ValidationError, OutputParserException) as e:
                error = e
            else:
                try:
                    if checker is not None:
                        checker(result) # type: ignore[arg-type]
                except Exception as e:
                    error = e
                else:
                    return result # type: ignore[return-value]

            if attempt == max_repair_attempts:
                logger.error(f"Model output did not conform to schema after {max_repair_attempts} attempts: {error}")
                raise ValueError(f"Model output did not conform to schema after {max_repair_attempts} attempts.") from error

            repair_messages: list[BaseMessage] = []
            if result is not None:
                repair_messages.append(AIMessage(content=str(result)))
            repair_messages.append(
                SystemMessage(content=optimize_error_message(error))
            )
            repaired_input = repaired_input + repair_messages
            logger.warning(f"Model output did not conform to schema, attempting repair {attempt + 1}/{max_repair_attempts}:\n{error}")
    

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
    return StructuredModel(structured_model, schema=schema)

__all__ = [
    "StructuredModel",
    "load_structured_model",
]
