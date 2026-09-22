"""Regression coverage for the second native-interaction review."""

import asyncio
import json
import threading
from contextlib import contextmanager
from hashlib import sha256
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import HTTPException
from sqlalchemy import Table, create_engine, func, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable
from starlette.requests import Request

from api.routes import ai
from db.models.chat_run import ChatRunORM
from exceptions import ModelCallExecutionError
from schemas.ai import AIChatHistoryListResponse
from services import UploadedChatFile
from utils.i18n import localize_error, public_run_error


def test_known_english_errors_are_not_hidden():
    for error in [
        ModelCallExecutionError("The model call failed."),
        "Model provider not found: demo",
    ]:
        assert public_run_error(error, "en-US") == localize_error(error, "en-US")
        assert public_run_error(error, "zh-CN") == localize_error(error, "zh-CN")
    assert "secret" not in public_run_error(RuntimeError("secret"), "en-US")
    assert localize_error("secret", "en-US") == "secret"


def request_for(manager, key=None):
    headers = [] if key is None else [(b"idempotency-key", key.encode())]
    return Request(
        {
            "type": "http",
            "headers": headers,
            "app": SimpleNamespace(state=SimpleNamespace(chat_runs=manager)),
        }
    )


@pytest.mark.parametrize("key", ["", "x" * 129])
async def test_invalid_key_rejected_before_lookup(monkeypatch, key):
    async def parse(*args, **kwargs):
        return ai.ParsedAIChatPayload(1, "hello", None, None, [], [])

    monkeypatch.setattr(ai, "_parse_ai_chat_payload", parse)
    with pytest.raises(HTTPException) as error:
        await ai._submit_chat_run(request_for(None, key))
    assert error.value.status_code == 422
    assert localize_error(error.value.detail, "en-US") == "Invalid idempotency key."
    assert localize_error(error.value.detail, "zh-CN") != error.value.detail


async def test_fingerprint_worker_yields_and_preserves_algorithm(monkeypatch):
    payload = ai.ParsedAIChatPayload(
        1,
        "hello",
        None,
        None,
        ["file"],
        [
            UploadedChatFile(
                filename="a.txt", content_type="text/plain", content=b"hello"
            )
        ],
    )
    original = ai._chat_fingerprint
    expected = sha256(
        json.dumps(
            {
                "thread_id": None,
                "selection_id": 1,
                "prompt": "hello",
                "command": None,
                "file_ids": ["file"],
                "interactive": True,
                "locale": "zh-CN",
                "uploads": [("a.txt", "text/plain", sha256(b"hello").hexdigest())],
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    started, release = threading.Event(), threading.Event()
    loop_thread = threading.get_ident()

    def fingerprint(*args):
        assert threading.get_ident() != loop_thread
        started.set()
        assert release.wait(3)
        return original(*args)

    async def parse(*args, **kwargs):
        return payload

    async def lookup(key, digest):
        assert len(key) == 32
        assert digest == expected
        return {"run_id": "existing"}

    monkeypatch.setattr(ai, "_parse_ai_chat_payload", parse)
    monkeypatch.setattr(ai, "_chat_fingerprint", fingerprint)
    task = asyncio.create_task(
        ai._submit_chat_run(request_for(SimpleNamespace(lookup_key=lookup)))
    )
    try:
        assert await asyncio.to_thread(started.wait, 2)
        assert not task.done()
    finally:
        release.set()
    assert await task == {"run_id": "existing"}
    assert original(payload, True, "en-US") != expected


@pytest.mark.parametrize("listing", [False, True])
async def test_history_worker_owns_session_and_does_not_block(monkeypatch, listing):
    entered, release = threading.Event(), threading.Event()
    owner = threading.get_ident()
    lifecycle = []

    @contextmanager
    def session_factory():
        lifecycle.append(("open", threading.get_ident()))
        try:
            yield SimpleNamespace()
        finally:
            lifecycle.append(("close", threading.get_ident()))

    class History:
        def __init__(self, *args):
            pass

        def get_history(self, tid):
            assert threading.get_ident() != owner
            entered.set()
            assert release.wait(3)
            return None

    async def unstarted(tid):
        return None

    manager = SimpleNamespace(
        repository=SimpleNamespace(
            conversation_page=lambda *args: [{"has_checkpoint": True, "thread_id": "t"}]
        ),
        unstarted_history=unstarted,
    )
    req = request_for(manager)
    req.app.state.database = SimpleNamespace(
        get_session_factory=lambda: session_factory
    )
    req.app.state.checkpointer = None
    monkeypatch.setattr(ai, "ChatHistoryService", History)
    task = asyncio.create_task(
        ai.list_chat_histories(req, 20, 0) if listing else ai.get_chat_history("t", req)
    )
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        assert not task.done()
    finally:
        release.set()
    if listing:
        assert cast(AIChatHistoryListResponse, await task).items == []
    else:
        with pytest.raises(HTTPException) as error:
            await task
        assert error.value.status_code == 404
    assert [event for event, _ in lifecycle] == ["open", "close"]
    assert lifecycle[0][1] == lifecycle[1][1] != owner


@pytest.mark.parametrize("legacy", [False, True])
def test_database_timestamp_supports_legacy_table_without_default(legacy):
    table = cast(Table, ChatRunORM.__table__)
    ddl = str(CreateTable(table).compile(dialect=sqlite.dialect()))
    assert "CURRENT_TIMESTAMP" in str(
        CreateTable(table).compile(dialect=postgresql.dialect())
    )
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            ddl.replace("DEFAULT CURRENT_TIMESTAMP", "") if legacy else ddl
        )
    with Session(engine) as session:
        before = session.scalar(select(func.current_timestamp()))
        assert before is not None
        row = ChatRunORM(
            run_id="r",
            idempotency_key="k",
            fingerprint="f",
            thread_id="t",
            status="queued",
            submission={},
        )
        session.add(row)
        session.flush()
        after = session.scalar(select(func.current_timestamp()))
        assert after is not None
        assert before <= row.created_at <= after
        assert not table.c.created_at.nullable
    engine.dispose()
