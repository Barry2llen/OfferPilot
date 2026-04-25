import asyncio

from langgraph.checkpoint.serde.types import ERROR

from agent.checkpointers import DatabaseCheckpointer
from db.engine import AsyncDatabaseManager, DatabaseManager
from db.repositories import CheckpointRepository


def make_config(
    thread_id: str,
    checkpoint_id: str | None = None,
    checkpoint_ns: str = "",
) -> dict:
    configurable = {
        "thread_id": thread_id,
        "checkpoint_ns": checkpoint_ns,
    }
    if checkpoint_id is not None:
        configurable["checkpoint_id"] = checkpoint_id
    return {"configurable": configurable}


def make_checkpoint(
    checkpoint_id: str,
    *,
    message: str,
    version: str,
    updated_channels: list[str] | None = None,
) -> dict:
    return {
        "v": 2,
        "id": checkpoint_id,
        "ts": "2026-04-23T00:00:00+00:00",
        "channel_values": {"messages": [message]},
        "channel_versions": {"messages": version},
        "versions_seen": {"model": {"messages": version}},
        "updated_channels": updated_channels,
        "pending_sends": [],
    }


def create_checkpointer(
    sync_manager: DatabaseManager,
    async_manager: AsyncDatabaseManager,
) -> DatabaseCheckpointer:
    sync_manager.initialize_tables()
    asyncio.run(async_manager.initialize_tables())
    return DatabaseCheckpointer(sync_manager, async_manager)


def test_database_checkpointer_round_trip_and_list_filters(
    temporary_database_manager: DatabaseManager,
    temporary_async_database_manager: AsyncDatabaseManager,
) -> None:
    checkpointer = create_checkpointer(
        temporary_database_manager,
        temporary_async_database_manager,
    )

    first_checkpoint = make_checkpoint(
        "00000000000000000000000000000001.0000000000000001",
        message="hello",
        version="00000000000000000000000000000001.0000000000000001",
        updated_channels=["messages"],
    )
    second_checkpoint = make_checkpoint(
        "00000000000000000000000000000002.0000000000000001",
        message="world",
        version="00000000000000000000000000000002.0000000000000001",
        updated_channels=["messages"],
    )

    first_config = checkpointer.put(
        make_config("thread-sync"),
        first_checkpoint,
        {"source": "input", "step": -1, "run_id": "run-1", "parents": {}},
        first_checkpoint["channel_versions"],
    )
    second_config = checkpointer.put(
        first_config,
        second_checkpoint,
        {"source": "loop", "step": 0, "run_id": "run-2", "parents": {"": first_checkpoint["id"]}},
        second_checkpoint["channel_versions"],
    )

    latest = checkpointer.get_tuple(make_config("thread-sync"))
    assert latest is not None
    assert latest.config["configurable"]["checkpoint_id"] == second_checkpoint["id"]
    assert latest.checkpoint["channel_values"]["messages"] == ["world"]
    assert latest.parent_config == {
        "configurable": {
            "thread_id": "thread-sync",
            "checkpoint_ns": "",
            "checkpoint_id": first_checkpoint["id"],
        }
    }

    filtered = list(
        checkpointer.list(
            make_config("thread-sync"),
            filter={"run_id": "run-1"},
        )
    )
    assert [item.checkpoint["id"] for item in filtered] == [first_checkpoint["id"]]

    before_items = list(
        checkpointer.list(
            make_config("thread-sync"),
            before=second_config,
            limit=1,
        )
    )
    assert [item.checkpoint["id"] for item in before_items] == [first_checkpoint["id"]]


def test_database_checkpointer_put_writes_is_idempotent_and_overwrites_error_entries(
    temporary_database_manager: DatabaseManager,
    temporary_async_database_manager: AsyncDatabaseManager,
) -> None:
    checkpointer = create_checkpointer(
        temporary_database_manager,
        temporary_async_database_manager,
    )
    checkpoint = make_checkpoint(
        "00000000000000000000000000000001.0000000000000001",
        message="hello",
        version="00000000000000000000000000000001.0000000000000001",
        updated_channels=["messages"],
    )
    config = checkpointer.put(
        make_config("thread-writes"),
        checkpoint,
        {"source": "input", "step": -1, "run_id": "run-writes", "parents": {}},
        checkpoint["channel_versions"],
    )

    checkpointer.put_writes(
        config,
        [("messages", {"value": 1}), ("summary", {"value": 2})],
        task_id="task-1",
        task_path="model",
    )
    checkpointer.put_writes(
        config,
        [("messages", {"value": 999})],
        task_id="task-1",
        task_path="model",
    )
    checkpointer.put_writes(
        config,
        [(ERROR, {"value": "first"})],
        task_id="task-1",
        task_path="model",
    )
    checkpointer.put_writes(
        config,
        [(ERROR, {"value": "replaced"})],
        task_id="task-1",
        task_path="model",
    )

    result = checkpointer.get_tuple(config)
    assert result is not None
    assert result.pending_writes == [
        ("task-1", "messages", {"value": 1}),
        ("task-1", "summary", {"value": 2}),
        ("task-1", ERROR, {"value": "replaced"}),
    ]


def test_checkpoint_repository_lists_latest_checkpoint_per_thread(
    temporary_database_manager: DatabaseManager,
    temporary_async_database_manager: AsyncDatabaseManager,
) -> None:
    checkpointer = create_checkpointer(
        temporary_database_manager,
        temporary_async_database_manager,
    )
    first_checkpoint = make_checkpoint(
        "00000000000000000000000000000001.0000000000000001",
        message="first",
        version="00000000000000000000000000000001.0000000000000001",
        updated_channels=["messages"],
    )
    second_checkpoint = make_checkpoint(
        "00000000000000000000000000000003.0000000000000001",
        message="second",
        version="00000000000000000000000000000003.0000000000000001",
        updated_channels=["messages"],
    )
    other_thread_checkpoint = make_checkpoint(
        "00000000000000000000000000000002.0000000000000001",
        message="other",
        version="00000000000000000000000000000002.0000000000000001",
        updated_channels=["messages"],
    )

    first_config = checkpointer.put(
        make_config("thread-latest"),
        first_checkpoint,
        {"source": "input", "step": -1, "run_id": "run-first", "parents": {}},
        first_checkpoint["channel_versions"],
    )
    checkpointer.put(
        first_config,
        second_checkpoint,
        {
            "source": "loop",
            "step": 0,
            "run_id": "run-second",
            "parents": {"": first_checkpoint["id"]},
        },
        second_checkpoint["channel_versions"],
    )
    checkpointer.put(
        make_config("thread-other"),
        other_thread_checkpoint,
        {"source": "input", "step": -1, "run_id": "run-other", "parents": {}},
        other_thread_checkpoint["channel_versions"],
    )

    with temporary_database_manager.session_scope() as session:
        rows = CheckpointRepository(session).list_latest_checkpoints_by_thread(
            limit=1,
            offset=0,
        )

    assert [(row.thread_id, row.checkpoint_id) for row in rows] == [
        ("thread-latest", second_checkpoint["id"]),
    ]


def test_database_checkpointer_copy_delete_for_runs_and_prune_keep_latest(
    temporary_database_manager: DatabaseManager,
    temporary_async_database_manager: AsyncDatabaseManager,
) -> None:
    checkpointer = create_checkpointer(
        temporary_database_manager,
        temporary_async_database_manager,
    )
    first_checkpoint = make_checkpoint(
        "00000000000000000000000000000001.0000000000000001",
        message="first",
        version="00000000000000000000000000000001.0000000000000001",
        updated_channels=["messages"],
    )
    second_checkpoint = make_checkpoint(
        "00000000000000000000000000000002.0000000000000001",
        message="stale-channel-value-should-not-be-used",
        version="00000000000000000000000000000001.0000000000000001",
        updated_channels=None,
    )

    first_config = checkpointer.put(
        make_config("thread-maintenance"),
        first_checkpoint,
        {"source": "input", "step": -1, "run_id": "run-keep", "parents": {}},
        first_checkpoint["channel_versions"],
    )
    second_config = checkpointer.put(
        first_config,
        second_checkpoint,
        {"source": "loop", "step": 0, "run_id": "run-drop", "parents": {"": first_checkpoint["id"]}},
        {},
    )

    checkpointer.copy_thread("thread-maintenance", "thread-copy")
    copied = checkpointer.get_tuple(make_config("thread-copy"))
    assert copied is not None
    assert copied.metadata["source"] == "fork"
    assert copied.checkpoint["channel_values"]["messages"] == ["first"]

    checkpointer.delete_for_runs(["run-drop"])
    remaining = checkpointer.get_tuple(make_config("thread-maintenance"))
    assert remaining is not None
    assert remaining.checkpoint["id"] == first_checkpoint["id"]

    # Reinsert the second checkpoint so prune can validate blob cleanup semantics.
    checkpointer.put(
        first_config,
        second_checkpoint,
        {"source": "loop", "step": 0, "run_id": "run-drop", "parents": {"": first_checkpoint["id"]}},
        {},
    )
    checkpointer.prune(["thread-maintenance"])
    pruned = checkpointer.get_tuple(make_config("thread-maintenance"))
    assert pruned is not None
    assert pruned.checkpoint["id"] == second_checkpoint["id"]
    assert pruned.checkpoint["channel_values"]["messages"] == ["first"]

    checkpointer.delete_thread("thread-copy")
    assert checkpointer.get_tuple(make_config("thread-copy")) is None


def test_database_checkpointer_async_round_trip(
    temporary_database_manager: DatabaseManager,
    temporary_async_database_manager: AsyncDatabaseManager,
) -> None:
    checkpointer = create_checkpointer(
        temporary_database_manager,
        temporary_async_database_manager,
    )

    async def run() -> None:
        checkpoint = make_checkpoint(
            "00000000000000000000000000000001.0000000000000001",
            message="async",
            version="00000000000000000000000000000001.0000000000000001",
            updated_channels=["messages"],
        )
        saved_config = await checkpointer.aput(
            make_config("thread-async"),
            checkpoint,
            {"source": "input", "step": -1, "run_id": "run-async", "parents": {}},
            checkpoint["channel_versions"],
        )
        await checkpointer.aput_writes(
            saved_config,
            [("messages", {"value": "async-write"})],
            task_id="task-async",
            task_path="async-model",
        )

        loaded = await checkpointer.aget_tuple(make_config("thread-async"))
        assert loaded is not None
        assert loaded.checkpoint["channel_values"]["messages"] == ["async"]
        assert loaded.pending_writes == [
            ("task-async", "messages", {"value": "async-write"})
        ]

        listed = [
            item async for item in checkpointer.alist(
                make_config("thread-async"),
                filter={"run_id": "run-async"},
            )
        ]
        assert [item.checkpoint["id"] for item in listed] == [checkpoint["id"]]

    asyncio.run(run())
