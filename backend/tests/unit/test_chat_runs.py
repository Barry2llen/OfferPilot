import asyncio
import json
import threading
from time import monotonic
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import FastAPI
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
    message_to_dict,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy import Table

from agent.base import BaseAgentState
from agent.graphs.model_call import ModelCallGraph
from agent.interactions import (
    InteractionBroker,
    InteractionContext,
    InteractionError,
    ask_user,
)
from schemas.config import Config
from services.chat_runs import ChatRunManager


async def test_missing_input_type_normalizes_and_accepts_retry():
    async def publish(*args):
        pass

    broker = InteractionBroker(publish)
    task = asyncio.create_task(
        broker.ask(InteractionContext(broker, "r", "t"), {"message": "retry"})
    )
    await until(lambda: broker.list_pending("r"))
    pending = broker.list_pending("r")[0]
    assert pending["type"] == "error"
    await broker.submit("r", pending["request_id"], {"type": "retry"})
    assert await task == {"type": "retry"}


async def test_empty_replay_buffer_always_sends_snapshot(manager):
    run = await submit(manager)
    rid = run["run_id"]
    await until(lambda: manager.broker.list_pending(rid))
    manager.limits = manager.limits.model_copy(update={"replay_bytes": 1})
    cursor = manager.runs[rid].sequence
    await manager.publish(rid, "token", {"content": "missing"})
    assert not manager.runs[rid].events
    for after in (cursor, -1, 0):
        stream = manager.stream(rid, after)
        event = await anext(stream)
        assert "event: snapshot" in event and "missing" in event
        await stream.aclose()
    await manager.shutdown()


async def test_result_survives_eviction_restart_and_does_not_use_latest_turn(manager):
    first = await submit(manager, "first")
    assert await manager.result(first["run_id"]) == "first"
    second = await submit(manager, "second")
    assert await manager.result(second["run_id"]) == "second"
    manager.runs[first["run_id"]].finished_at = monotonic() - 3600
    manager._prune()
    assert first["run_id"] not in manager.runs
    restarted = ChatRunManager(
        config=manager.config, database=manager.database, agent=manager.agent
    )
    assert await restarted.result(first["run_id"]) == "first"
    await restarted.shutdown()
    await manager.shutdown()


async def test_admission_parallel_threads_shared_key_fifo_and_delete_drain(manager):
    entered, release = threading.Event(), threading.Event()
    prepared = []

    def prepare():
        entered.set()
        assert release.wait(5)
        prepared.append("one")
        return {
            "prompt": "done",
            "selection_id": 1,
            "locale": "en-US",
            "file_ids": [],
            "human_message": message_to_dict(HumanMessage(content="done", id="m")),
        }

    slow = asyncio.create_task(
        manager.enqueue(
            key="slow", fingerprint="same", thread_id="slow-thread", prepare=prepare
        )
    )
    await until(entered.is_set)
    duplicate = asyncio.create_task(
        manager.enqueue(
            key="slow", fingerprint="same", thread_id="slow-thread", prepare=prepare
        )
    )
    following = asyncio.create_task(submit(manager, "following", tid="slow-thread"))
    fast = await asyncio.wait_for(submit(manager, "fast", tid="other"), 2)
    assert await manager.result(fast["run_id"]) == "fast"
    deletion = asyncio.create_task(manager.delete_thread("slow-thread"))
    await until(lambda: "slow-thread" in manager.deleting)
    with pytest.raises(InteractionError):
        await submit(manager, "rejected", tid="slow-thread")
    assert not deletion.done()
    release.set()
    first, same = await asyncio.gather(slow, duplicate)
    assert first["run_id"] == same["run_id"]
    await asyncio.gather(following, return_exceptions=True)
    assert await deletion
    assert prepared == ["one"]
    assert await manager.list("slow-thread") == []
    assert "slow-thread" not in manager.queues
    assert not await manager.delete_thread("unknown")
    await submit(manager, "reused", tid="unknown")
    await manager.shutdown()


async def test_failed_delete_keeps_guard_until_retry(manager):
    def fail():
        raise RuntimeError("storage unavailable")

    with pytest.raises(RuntimeError):
        await manager.delete_thread("thread", fail)
    with pytest.raises(InteractionError):
        await submit(manager, "blocked")
    assert not await manager.delete_thread("thread", lambda: False)
    run = await submit(manager, "works")
    assert await manager.result(run["run_id"]) == "works"
    await manager.shutdown()


async def test_cancel_finishes_open_tools_once_and_sync_error_is_status_aware(manager):
    run = await submit(manager)
    rid = run["run_id"]
    await until(lambda: manager.broker.list_pending(rid))
    await manager.publish(
        rid, "tool_start", {"tool_call_id": "open", "tool_name": "work"}
    )
    await manager.publish(
        rid, "tool_start", {"tool_call_id": "done", "tool_name": "work"}
    )
    await manager.publish(
        rid, "tool_end", {"tool_call_id": "done", "tool_name": "work", "output": "ok"}
    )
    await manager.cancel(rid)
    projection = manager.runs[rid].projection
    terminals = [
        event for event in projection if event["event"] in {"tool_end", "tool_error"}
    ]
    assert [(event["data"]["tool_call_id"], event["event"]) for event in terminals] == [
        ("done", "tool_end"),
        ("open", "tool_error"),
    ]
    with pytest.raises(InteractionError, match="cancelled"):
        await manager.result(rid)


async def test_unknown_errors_are_not_exposed_and_list_does_not_refetch(
    manager, monkeypatch
):
    run = await submit(manager, "fail")
    await manager.runs[run["run_id"]].done.wait()
    assert "deliberate failure" not in json.dumps(await manager.get(run["run_id"]))
    manager.runs.clear()
    monkeypatch.setattr(
        manager.repository, "get", lambda *args: pytest.fail("N+1 query")
    )
    assert len(await manager.list("thread")) == 1


def test_run_errors_preserve_specific_reasons_in_both_locales():
    from exceptions import ModelCallExecutionError
    from utils.i18n import localize_error

    error = ModelCallExecutionError("Too many pending input requests.")
    assert localize_error(error, "en-US") == str(error)
    assert "上限" in localize_error(error, "zh-CN")


async def test_same_thread_preparation_preserves_fifo(manager):
    entered, release = threading.Event(), threading.Event()
    prepared = []

    def prepare(value):
        if value == "first":
            entered.set()
            assert release.wait(5)
        prepared.append(value)
        return {
            "prompt": value,
            "selection_id": 1,
            "locale": "en-US",
            "human_message": message_to_dict(HumanMessage(content=value, id=value)),
        }

    first = asyncio.create_task(
        manager.enqueue(
            key="a", fingerprint="a", thread_id="t", prepare=lambda: prepare("first")
        )
    )
    await until(entered.is_set)
    second = asyncio.create_task(
        manager.enqueue(
            key="b", fingerprint="b", thread_id="t", prepare=lambda: prepare("second")
        )
    )
    await asyncio.sleep(0)
    assert prepared == []
    release.set()
    one, two = await asyncio.gather(first, second)
    assert prepared == ["first", "second"]
    assert one["sequence"] < two["sequence"]
    assert await manager.result(two["run_id"]) == "second"
    await manager.shutdown()


async def test_legacy_result_uses_only_requested_turn_or_returns_conflict(
    manager, monkeypatch
):
    run = await submit(manager, "legacy", key="human-id")
    await manager.result(run["run_id"])
    manager.runs[run["run_id"]].row["submission"].pop("final_result")

    async def snapshot(*args, **kwargs):
        return SimpleNamespace(
            values={
                "messages": [
                    HumanMessage(content="legacy", id="human-id"),
                    AIMessage(content="original"),
                    HumanMessage(content="later"),
                    AIMessage(content="wrong answer"),
                ]
            }
        )

    monkeypatch.setattr(manager.agent, "aget_state", snapshot)
    assert await manager.result(run["run_id"]) == "original"
    manager.runs[run["run_id"]].row["submission"]["human_message"]["data"]["id"] = (
        "absent"
    )
    with pytest.raises(InteractionError) as error:
        await manager.result(run["run_id"])
    assert error.value.status_code == 409


async def test_conversation_page_query_compiles_for_both_databases(
    manager, monkeypatch
):
    from sqlalchemy.dialects import postgresql, sqlite
    from sqlalchemy.orm import Session

    original = Session.execute
    statements = []

    def capture(self, statement, *args, **kwargs):
        statements.append(statement)
        return original(self, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "execute", capture)
    run = await submit(manager, "done")
    await manager.result(run["run_id"])
    statements.clear()
    page = manager.repository.conversation_page(1, 0)
    assert len(page) == 1
    assert len(statements) == 1
    for dialect in (sqlite.dialect(), postgresql.dialect()):
        sql = str(statements[0].compile(dialect=dialect))
        assert "UNION ALL" in sql and "LIMIT" in sql
    await manager.shutdown()


async def until(predicate):
    async with asyncio.timeout(5):
        while not predicate():
            await asyncio.sleep(0.005)


def question():
    return {
        "type": "query",
        "question": "Choose",
        "firstChoice": "A",
        "secondChoice": "B",
        "thirdChoice": "C",
    }


async def test_broker_early_answer_and_duplicate_conflict():
    broker: InteractionBroker

    async def publish(rid: str, event: str, data: dict[str, Any]) -> None:
        if event == "input_required":
            await broker.submit(rid, data["request_id"], {"choice": "firstChoice"})

    broker = InteractionBroker(publish)
    answer = await broker.ask(InteractionContext(broker, "r", "t"), question())
    assert answer == {"choice": "firstChoice", "note": None}
    request_id = next(iter(broker.items))[1]
    await broker.submit("r", request_id, {"choice": "firstChoice"})
    with pytest.raises(InteractionError) as error:
        await broker.submit("r", request_id, {"choice": "secondChoice"})
    assert error.value.status_code == 409
    with pytest.raises(InteractionError):
        await broker.submit("other-run", request_id, {"choice": "firstChoice"})


async def test_broker_parallel_reverse_answers_and_sequential_questions():
    async def publish(*args):
        pass

    broker = InteractionBroker(publish)
    contexts = [
        InteractionContext(broker, "r", "t", tool_call_id=str(i)) for i in range(2)
    ]

    async def worker(context):
        return [
            await broker.ask(context, question()),
            await broker.ask(context, question()),
        ]

    tasks = [asyncio.create_task(worker(context)) for context in contexts]
    for round_index in range(2):
        await until(lambda: len(broker.list_pending("r")) == 2)
        for item in reversed(broker.list_pending("r")):
            await broker.submit(
                "r",
                item["request_id"],
                {"choice": "other", "note": item["tool_call_id"] + str(round_index)},
            )
    results = await asyncio.gather(*tasks)
    assert [[a["note"] for a in answers] for answers in results] == [
        ["00", "01"],
        ["10", "11"],
    ]
    assert len(broker.items) == 4


async def test_broker_timeout_and_cancel_leave_no_waiters():
    async def publish(*args):
        pass

    broker = InteractionBroker(publish, timeout=0.01)
    with pytest.raises(TimeoutError):
        await broker.ask(InteractionContext(broker, "r", "t"), question())
    assert broker.list_pending("r") == []
    request_id = next(iter(broker.items))[1]
    with pytest.raises(InteractionError) as error:
        await broker.submit("r", request_id, {"choice": "firstChoice"})
    assert error.value.status_code == 410


@pytest.fixture
def manager(temporary_database_manager, monkeypatch):
    temporary_database_manager.initialize_tables()

    class Agent:
        async def aget_state(self, *args, **kwargs):
            return SimpleNamespace(values={}, tasks=(), next=())

        async def aupdate_state(self, *args, **kwargs):
            pass

        async def astream_events(self, state, config, **kwargs):
            prompt = state["messages"][0].content
            if prompt == "ask":
                await ask_user(question())
            if prompt == "fail":
                raise ValueError("deliberate failure")
            yield {
                "event": "on_chain_end",
                "data": {"output": {"messages": [AIMessage(content=prompt)]}},
            }

    result = ChatRunManager(
        config=Config(), database=temporary_database_manager, agent=Agent()
    )

    async def selection(_):
        return SimpleNamespace(supports_image_input=True)

    monkeypatch.setattr(result, "_selection", selection)
    return result


async def submit(manager, prompt="ask", tid="thread", key=None, interactive=True):
    key = key or f"{tid}-{prompt}"
    return await manager.enqueue(
        key=key,
        fingerprint=prompt,
        thread_id=tid,
        interactive=interactive,
        prepare=lambda: {
            "prompt": prompt,
            "selection_id": 1,
            "locale": "en-US",
            "file_ids": [],
            "human_message": message_to_dict(HumanMessage(content=prompt, id=key)),
        },
    )


async def test_fifo_wait_cancel_and_failed_run_advance(manager):
    first = await submit(manager)
    second = await submit(manager, "fail")
    third = await submit(manager, "done")
    await until(lambda: manager.broker.list_pending(first["run_id"]))
    assert (await manager.get(second["run_id"]))["status"] == "queued"
    await manager.cancel(first["run_id"])
    await manager.runs[third["run_id"]].done.wait()
    assert [
        (await manager.get(r["run_id"]))["status"] for r in [first, second, third]
    ] == ["cancelled", "failed", "completed"]
    assert not manager.broker.list_pending(first["run_id"])


async def test_two_threads_and_idempotent_enqueue(manager):
    first = await submit(manager, tid="one")
    second = await submit(manager, tid="two")
    assert (await submit(manager, tid="one"))["run_id"] == first["run_id"]
    await until(
        lambda: (
            len(manager.broker.list_pending(first["run_id"])) == 1
            and len(manager.broker.list_pending(second["run_id"])) == 1
        )
    )
    request = manager.broker.list_pending(second["run_id"])[0]
    await manager.broker.submit(
        second["run_id"], request["request_id"], {"choice": "firstChoice"}
    )
    await manager.runs[second["run_id"]].done.wait()
    assert (await manager.get(first["run_id"]))["status"] == "waiting_input"
    await manager.shutdown()


async def test_disconnect_snapshot_and_expired_replay(manager):
    manager.limits = manager.limits.model_copy(
        update={"replay_events": 2, "subscriber_events": 1}
    )
    run = await submit(manager)
    rid = run["run_id"]
    await until(lambda: manager.broker.list_pending(rid))
    stream = manager.stream(rid)
    assert "input_required" not in await anext(
        stream
    )  # pending requests live in the snapshot field
    await stream.aclose()
    assert (await manager.get(rid))["status"] == "waiting_input"
    for _ in range(5):
        await manager.publish(rid, "token", {"content": "a"})
    reconnect = manager.stream(rid, 1)
    snapshot = await anext(reconnect)
    assert "event: snapshot" in snapshot and "aaaaa" in snapshot
    assert "request_id" in snapshot
    await reconnect.aclose()
    await manager.shutdown()


async def test_sync_input_fails_instead_of_waiting_and_restart_marks_orphans(manager):
    run = await submit(manager, interactive=False)
    await manager.runs[run["run_id"]].done.wait()
    assert (await manager.get(run["run_id"]))["status"] == "failed"
    active = await submit(manager, tid="restart")
    queued = await submit(manager, "later", tid="restart")
    await until(lambda: manager.broker.list_pending(active["run_id"]))
    manager.repository.recover()
    assert manager.repository.get(active["run_id"])["status"] == "interrupted"
    assert manager.repository.get(queued["run_id"])["status"] == "cancelled"
    await manager.shutdown()


async def test_real_graph_cancel_closes_tools_before_next_prompt(manager, monkeypatch):
    effects = []

    @tool
    async def write_once() -> str:
        """Record a side effect."""
        effects.append("write")
        return "written"

    @tool
    async def wait_for_user() -> str:
        """Wait for a decision."""
        effects.append("before")
        await ask_user(question())
        effects.append("after")
        return "answered"

    class Model:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            if messages[-1].content == "ask":
                return AIMessage(
                    content="",
                    tool_calls=[
                        {"id": "write", "name": "write_once", "args": {}},
                        {"id": "ask", "name": "wait_for_user", "args": {}},
                    ],
                )
            # Every assistant tool call must have a result before the next prompt.
            calls = {c["id"] for m in messages for c in getattr(m, "tool_calls", [])}
            answers = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
            assert calls <= answers
            return AIMessage(content="finished")

    monkeypatch.setattr("agent.graphs.model_call.load_chat_model", lambda _: Model())
    inner = ModelCallGraph(
        tools=[write_once, wait_for_user], config=Config()
    ).get_compiled_graph()
    root = (
        StateGraph(BaseAgentState)
        .add_node("model_call", inner)
        .add_edge(START, "model_call")
        .add_edge("model_call", END)
    )
    manager.agent = root.compile(checkpointer=InMemorySaver())

    async def selection(_):
        return None

    monkeypatch.setattr(manager, "_selection", selection)
    # Avoid a model-capability check for this text-only fixture.
    monkeypatch.setattr(
        "services.chat_runs.ChatFileService.thread_requires_image_input",
        lambda *args: False,
    )
    first = await submit(manager)
    second = await submit(manager, "next")
    await until(lambda: manager.broker.list_pending(first["run_id"]))
    await until(
        lambda: any(
            e["event"] == "tool_end" for e in manager.runs[first["run_id"]].projection
        )
    )
    await manager.cancel(first["run_id"])
    await manager.runs[second["run_id"]].done.wait()
    assert (await manager.get(second["run_id"]))["status"] == "completed"
    assert effects == ["write", "before"]
    snapshot = await manager.agent.aget_state({"configurable": {"thread_id": "thread"}})
    assert not snapshot.next
    tools = [m for m in snapshot.values["messages"] if isinstance(m, ToolMessage)]
    assert {m.tool_call_id for m in tools} == {"write", "ask"}
    assert next(m for m in tools if m.tool_call_id == "write").content == "written"


async def test_slow_subscriber_is_detached_and_reconnects_with_snapshot(manager):
    manager.limits = manager.limits.model_copy(update={"subscriber_events": 1})
    run = await submit(manager)
    rid = run["run_id"]
    await until(lambda: manager.broker.list_pending(rid))
    stream = manager.stream(rid)
    await anext(stream)
    await manager.publish(rid, "token", {"content": "one"})
    await manager.publish(rid, "token", {"content": "two"})
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    assert not manager.runs[rid].subscribers
    assert (await manager.get(rid))["status"] == "waiting_input"
    await manager.shutdown()


async def test_legacy_interrupt_checkpoint_is_closed_without_replay(manager):
    from langgraph.types import interrupt

    executions = []

    def legacy_node(state):
        executions.append("old")
        interrupt({"type": "query"})
        return state

    saver = InMemorySaver()
    old_inner = (
        StateGraph(BaseAgentState)
        .add_node("interrupt_tool", legacy_node)
        .add_edge(START, "interrupt_tool")
        .add_edge("interrupt_tool", END)
        .compile()
    )
    old_root = (
        StateGraph(BaseAgentState)
        .add_node("model_call", old_inner)
        .add_edge(START, "model_call")
        .add_edge("model_call", END)
        .compile(checkpointer=saver)
    )
    config: RunnableConfig = {"configurable": {"thread_id": "legacy"}}
    await old_root.ainvoke(
        {
            "messages": [
                HumanMessage(content="old", id="human"),
                AIMessage(
                    content="",
                    id="ai",
                    tool_calls=[{"id": "old-call", "name": "query", "args": {}}],
                ),
                ToolMessage(
                    content="[INTERRUPT_TOOL_CALLED]",
                    tool_call_id="old-call",
                    id="placeholder",
                ),
            ]
        },
        config,
    )
    inner = ModelCallGraph(config=Config()).get_compiled_graph()
    manager.agent = (
        StateGraph(BaseAgentState)
        .add_node("model_call", inner)
        .add_edge(START, "model_call")
        .add_edge("model_call", END)
        .compile(checkpointer=saver)
    )
    await manager._close_checkpoint("legacy")
    snapshot = await manager.agent.aget_state(config)
    assert not snapshot.next
    assert executions == ["old"]
    assert snapshot.values["messages"][-1].status == "error"
    assert snapshot.values["messages"][-1].content != "[INTERRUPT_TOOL_CALLED]"


async def test_limits_queue_removal_and_delete_before_checkpoint(manager):
    manager.limits = manager.limits.model_copy(
        update={"max_active": 1, "max_queued_per_thread": 1}
    )
    first = await submit(manager)
    await until(lambda: manager.broker.list_pending(first["run_id"]))
    second = await submit(manager, "second")
    with pytest.raises(InteractionError) as error:
        await submit(manager, "overflow")
    assert error.value.status_code == 429
    other = await submit(manager, "new-thread", tid="unstarted")
    assert (await manager.get(other["run_id"]))["status"] == "queued"
    assert (await manager.unstarted_history("unstarted"))["message_count"] == 0
    assert await manager.delete_thread("unstarted")
    assert await manager.list("unstarted") == []
    replacement = await submit(manager, "deleted", tid="unstarted")
    assert replacement["run_id"] != other["run_id"]
    await manager.cancel(second["run_id"])
    await manager.shutdown()
    assert not manager.active and all(
        run.done.is_set() for run in manager.runs.values()
    )


async def test_checkpoint_finalization_failure_fails_queue_and_blocks_thread(
    manager, monkeypatch
):
    async def fail(*args, **kwargs):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(manager.agent, "aupdate_state", fail)
    first = await submit(manager)
    second = await submit(manager, "next")
    await until(lambda: manager.broker.list_pending(first["run_id"]))
    await manager.cancel(first["run_id"])
    assert (await manager.get(second["run_id"]))["status"] == "failed"
    with pytest.raises(InteractionError):
        await submit(manager, "after-finalization-error")


async def test_disconnected_submission_keeps_owned_admission(manager):
    from threading import Event

    started, release = Event(), Event()

    def prepare():
        started.set()
        assert release.wait(5)
        return {
            "prompt": "done",
            "selection_id": 1,
            "locale": "en-US",
            "file_ids": [],
            "human_message": message_to_dict(HumanMessage(content="done", id="owned")),
        }

    request = asyncio.create_task(
        manager.enqueue(
            key="owned", fingerprint="owned", thread_id="owned", prepare=prepare
        )
    )
    await until(started.is_set)
    request.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request
    release.set()
    await until(lambda: bool(manager.runs))
    run = next(iter(manager.runs.values()))
    await run.done.wait()
    assert run.row["status"] == "completed"
    await manager.shutdown()


def test_sqlite_postgres_run_table_ddl():
    from sqlalchemy.dialects import postgresql, sqlite
    from sqlalchemy.schema import CreateTable

    from db.models import ChatRunORM

    for dialect in (postgresql.dialect(), sqlite.dialect()):
        ddl = str(
            CreateTable(cast(Table, ChatRunORM.__table__)).compile(dialect=dialect)
        )
        assert "UNIQUE (idempotency_key)" in ddl
        assert "submission JSON" in ddl


def test_http_native_answers_queue_and_migration(temporary_app_config, monkeypatch):
    import time

    from fastapi.testclient import TestClient

    from agent.tools.query import query
    from main import create_app

    class Model:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            if isinstance(messages[-1], HumanMessage) and messages[-1].content == "ask":
                args = {
                    "question": "Pick",
                    "firstChoice": "A",
                    "firstChoiceDescription": "A",
                    "secondChoice": "B",
                    "secondChoiceDescription": "B",
                    "thirdChoice": "C",
                    "thirdChoiceDescription": "C",
                }
                return AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "query", "id": str(i), "args": args} for i in range(2)
                    ],
                )
            return AIMessage(content="done")

    monkeypatch.setattr("agent.graphs.model_call.load_chat_model", lambda _: Model())
    with TestClient(create_app(temporary_app_config)) as client:
        inner = ModelCallGraph(config=Config(), tools=[query]).get_compiled_graph()
        graph = (
            StateGraph(BaseAgentState)
            .add_node("model_call", inner)
            .add_edge(START, "model_call")
            .add_edge("model_call", END)
        )
        cast(FastAPI, client.app).state.chat_runs.agent = graph.compile(
            checkpointer=cast(FastAPI, client.app).state.checkpointer
        )
        assert (
            client.post(
                "/model-providers", json={"provider": "OpenAI", "name": "test"}
            ).status_code
            == 200
        )
        selection = client.post(
            "/model-selections", json={"provider_name": "test", "model_name": "test"}
        ).json()["id"]
        body = {"prompt": "ask", "selection_id": selection, "thread_id": "http"}
        response = client.post(
            "/ai/chat/runs", json=body, headers={"Idempotency-Key": "first"}
        )
        assert response.status_code == 202
        rid = response.json()["run_id"]
        assert (
            client.post(
                "/ai/chat/runs", json=body, headers={"Idempotency-Key": "first"}
            ).json()["run_id"]
            == rid
        )
        assert (
            client.post(
                "/ai/chat/runs",
                json={**body, "prompt": "changed"},
                headers={"Idempotency-Key": "first"},
            ).status_code
            == 409
        )
        second = client.post("/ai/chat/runs", json={**body, "prompt": "next"}).json()

        def wait_for(predicate):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                value = client.get(f"/ai/chat/runs/{rid}").json()
                if predicate(value):
                    return value
                time.sleep(0.01)
            raise AssertionError("Run did not reach expected state")

        pending = wait_for(lambda value: len(value["pending_inputs"]) == 2)[
            "pending_inputs"
        ]
        assert len({item["tool_call_id"] for item in pending}) == 2
        assert (
            client.get(f"/ai/chat/runs/{second['run_id']}").json()["status"] == "queued"
        )
        for item in reversed(pending):
            url = f"/ai/chat/runs/{rid}/inputs/{item['request_id']}"
            answer = {"answer": {"choice": "firstChoice"}}
            assert (
                client.post(url, json={"answer": {"choice": "invalid"}}).status_code
                == 422
            )
            assert client.post(url, json=answer).status_code == 200
            assert client.post(url, json=answer).status_code == 200
            assert (
                client.post(
                    url, json={"answer": {"choice": "secondChoice"}}
                ).status_code
                == 409
            )
        wait_for(lambda value: value["status"] == "completed")
        rid = second["run_id"]
        wait_for(lambda value: value["status"] == "completed")
        history = client.get("/ai/chats/http/history").json()["messages"]
        assert len([m for m in history if m["role"] == "tool"]) == 2
        assert (
            client.post(
                "/ai/chat/stream",
                json={
                    "selection_id": selection,
                    "thread_id": "http",
                    "command": {"type": "retry"},
                },
            ).status_code
            == 410
        )
        assert (
            client.post("/ai/chat", json={**body, "thread_id": "sync"}).status_code
            == 502
        )
        schema = client.get("/openapi.json").json()
        for path in (
            "/ai/chat/runs",
            "/ai/chat/runs/{run_id}/events",
            "/ai/chat/runs/{run_id}/inputs/{request_id}",
        ):
            for operation in schema["paths"][path].values():
                assert (
                    operation["summary"]
                    and operation["description"]
                    and operation["responses"]
                )
