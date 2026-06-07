import inspect

import pytest

from agent.nodes.wrappers import require_fields


def test_require_fields_preserves_sync_function_and_result() -> None:
    @require_fields("value")
    def node(state: dict[str, object]) -> dict[str, object]:
        return {"result": state["value"]}

    assert not inspect.iscoroutinefunction(node)
    assert node({"value": "ok"}) == {"result": "ok"}


async def test_require_fields_preserves_async_function_and_awaits_result() -> None:
    @require_fields("value")
    async def node(state: dict[str, object]) -> dict[str, object]:
        return {"result": state["value"]}

    assert inspect.iscoroutinefunction(node)
    assert await node({"value": "ok"}) == {"result": "ok"}


def test_require_fields_sync_wrapper_rejects_missing_fields() -> None:
    @require_fields("value")
    def node(state: dict[str, object]) -> dict[str, object]:
        return state

    with pytest.raises(ValueError, match="Missing required fields: value"):
        node({})


async def test_require_fields_async_wrapper_rejects_missing_fields() -> None:
    @require_fields("value")
    async def node(state: dict[str, object]) -> dict[str, object]:
        return state

    with pytest.raises(ValueError, match="Missing required fields: value"):
        await node({})
