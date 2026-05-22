from langchain_core.runnables import RunnableLambda

from agent.models.structured import StructuredModel


def test_structured_model_delegates_invoke_to_wrapped_runnable() -> None:
    wrapped = RunnableLambda(lambda input_: {"value": input_})
    model: StructuredModel[dict] = StructuredModel(wrapped)

    assert model.invoke("resume") == {"value": "resume"}


async def test_structured_model_delegates_ainvoke_to_wrapped_runnable() -> None:
    wrapped = RunnableLambda(lambda input_: {"value": input_})
    model: StructuredModel[dict] = StructuredModel(wrapped)

    assert await model.ainvoke("resume") == {"value": "resume"}
