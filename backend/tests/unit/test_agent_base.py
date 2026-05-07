import asyncio
from typing import Any

from agent.base import BaseWorkflow
from schemas.config import Config


class FakeCompiledGraph:
    def __init__(self) -> None:
        self.invoke_calls: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.stream_calls: list[tuple[dict[str, Any], dict[str, Any], str]] = []

    def invoke(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        self.invoke_calls.append((state, config))
        return {"result": "sync"}

    async def astream_events(
        self,
        state: dict[str, Any],
        config: dict[str, Any],
        *,
        version: str,
    ):
        self.stream_calls.append((state, config, version))
        yield {
            "event": "on_chain_end",
            "data": {"output": {"result": "stream"}},
        }


class FakeAgent:
    def __init__(self, config: Config, graph: FakeCompiledGraph) -> None:
        self.config = config
        self._graph = graph

    def get_agent(self) -> FakeCompiledGraph:
        return self._graph


class FakeWorkflow(BaseWorkflow[str, dict[str, Any]]):
    def _construct_initial_state(self, value: str) -> dict[str, Any]:
        return {"input": value}

    def _get_result(self, state: dict[str, Any]) -> str:
        return str(state["result"])


def test_base_workflow_passes_graph_recursion_limit_to_invoke() -> None:
    graph = FakeCompiledGraph()
    workflow = FakeWorkflow(FakeAgent(Config(graph_recursion_limit=250), graph))

    assert workflow.invoke("hello") == "sync"
    assert graph.invoke_calls == [
        (
            {"input": "hello"},
            {"recursion_limit": 250},
        )
    ]


def test_base_workflow_passes_graph_recursion_limit_to_astream_events() -> None:
    graph = FakeCompiledGraph()
    workflow = FakeWorkflow(FakeAgent(Config(graph_recursion_limit=250), graph))

    result = asyncio.run(workflow.astream_events("hello"))

    assert result == "stream"
    assert graph.stream_calls == [
        (
            {"input": "hello"},
            {"recursion_limit": 250},
            "v2",
        )
    ]
