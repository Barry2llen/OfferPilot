import pytest
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel

from agent.models import structured as structured_module
from agent.models.structured import StructuredModel


def test_structured_model_delegates_invoke_to_wrapped_runnable() -> None:
    wrapped = RunnableLambda(lambda input_: {"value": input_})
    model: StructuredModel[dict] = StructuredModel(wrapped)

    assert model.invoke("resume") == {"value": "resume"}


async def test_structured_model_delegates_ainvoke_to_wrapped_runnable() -> None:
    wrapped = RunnableLambda(lambda input_: {"value": input_})
    model: StructuredModel[dict] = StructuredModel(wrapped)

    assert await model.ainvoke("resume") == {"value": "resume"}


def test_load_structured_model_keeps_default_structured_output_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    wrapped = RunnableLambda(lambda input_: {"value": input_})

    class FakeChatModel:
        def with_structured_output(self, schema, **kwargs):
            captured["schema"] = schema
            captured["kwargs"] = kwargs
            return wrapped

    monkeypatch.setattr(
        structured_module,
        "load_chat_model",
        lambda model_selection: FakeChatModel(),
    )

    model = structured_module.load_structured_model(None, {"name": "Result"})

    assert model._model is wrapped
    assert captured == {"schema": {"name": "Result"}, "kwargs": {}}


def test_load_structured_model_forwards_explicit_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    wrapped = RunnableLambda(lambda input_: {"value": input_})

    class FakeChatModel:
        def with_structured_output(self, schema, **kwargs):
            captured["schema"] = schema
            captured["kwargs"] = kwargs
            return wrapped

    monkeypatch.setattr(
        structured_module,
        "load_chat_model",
        lambda model_selection: FakeChatModel(),
    )

    model = structured_module.load_structured_model(
        None,
        {"name": "Result"},
        method="function_calling",
    )

    assert model._model is wrapped
    assert captured == {
        "schema": {"name": "Result"},
        "kwargs": {"method": "function_calling"},
    }


async def test_structured_model_preserves_wrapped_ainvoke_exception() -> None:
    async def fail(_input: object) -> dict:
        raise RuntimeError("provider unavailable")

    model: StructuredModel[dict] = StructuredModel(RunnableLambda(fail))

    with pytest.raises(RuntimeError, match="provider unavailable"):
        await model.ainvoke(
            [HumanMessage(content="resume")],
            checker=lambda _result: None,
            max_repair_attempts=1,
        )


async def test_structured_model_repairs_only_after_checker_failure() -> None:
    received_inputs: list[list[object]] = []

    async def respond(input_: list[object]) -> dict[str, str]:
        received_inputs.append(input_)
        if len(received_inputs) == 1:
            return {"value": "bad"}
        return {"value": "ok"}

    def checker(result: dict[str, str]) -> None:
        if result["value"] != "ok":
            raise ValueError("value must be ok")

    model: StructuredModel[dict[str, str]] = StructuredModel(RunnableLambda(respond))

    assert await model.ainvoke(
        [HumanMessage(content="resume")],
        checker=checker,
        max_repair_attempts=1,
    ) == {"value": "ok"}
    assert len(received_inputs) == 2
    assert received_inputs[1][0] == HumanMessage(content="resume")
    assert received_inputs[1][1] == AIMessage(content="{'value': 'bad'}")
    assert isinstance(received_inputs[1][2], SystemMessage)


async def test_structured_model_repairs_after_pydantic_validation_error() -> None:
    class ExpectedResult(BaseModel):
        value: int

    received_inputs: list[list[object]] = []

    async def respond(input_: list[object]) -> dict[str, str]:
        received_inputs.append(input_)
        if len(received_inputs) == 1:
            ExpectedResult.model_validate({"value": "bad"})
        return {"value": "ok"}

    model: StructuredModel[dict[str, str]] = StructuredModel(RunnableLambda(respond))

    assert await model.ainvoke(
        [HumanMessage(content="resume")],
        max_repair_attempts=1,
    ) == {"value": "ok"}
    assert len(received_inputs) == 2
    assert received_inputs[1][0] == HumanMessage(content="resume")
    assert isinstance(received_inputs[1][1], SystemMessage)


async def test_structured_model_repairs_after_output_parser_exception() -> None:
    received_inputs: list[list[object]] = []

    async def respond(input_: list[object]) -> dict[str, str]:
        received_inputs.append(input_)
        if len(received_inputs) == 1:
            raise OutputParserException("Failed to parse structured output")
        return {"value": "ok"}

    model: StructuredModel[dict[str, str]] = StructuredModel(RunnableLambda(respond))

    assert await model.ainvoke(
        [HumanMessage(content="resume")],
        max_repair_attempts=1,
    ) == {"value": "ok"}
    assert len(received_inputs) == 2
    assert received_inputs[1][0] == HumanMessage(content="resume")
    assert isinstance(received_inputs[1][1], SystemMessage)
