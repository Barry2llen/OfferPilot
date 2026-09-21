"""Single-process chat scheduling, replay and checkpoint termination."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from time import monotonic
from typing import Any
from uuid import uuid4

from langchain_core.messages import ToolMessage, messages_from_dict
from langgraph.graph.message import add_messages

from agent.interactions import (
    InteractionBroker,
    InteractionContext,
    InteractionError,
    interaction_context,
)
from db.engine import DatabaseManager
from db.repositories import (
    ChatFileRepository,
    ChatThreadFileRepository,
    ModelSelectionRepository,
)
from db.repositories.chat_run_repository import ChatRunRepository
from schemas.config import Config
from schemas.model_selection import ModelSelection
from services.chat_events import (
    _extract_chunk_reasoning,
    _extract_chunk_text,
    _extract_content,
    _extract_event_output,
)
from services.chat_file_service import ChatFileService
from services.model_selection_service import ModelSelectionService
from utils.i18n import localize_error
from utils.stream import render_sse_event, to_jsonable
from utils.tool_outputs import summarize_tool_output

TERMINAL = {"completed", "failed", "cancelled", "interrupted"}


@dataclass
class ChatRun:
    row: dict[str, Any]
    task: asyncio.Task | None = None
    events: deque[tuple[int, str, int]] = field(default_factory=deque)
    subscribers: set[asyncio.Queue[str | None]] = field(default_factory=set)
    sequence: int = 0
    event_bytes: int = 0
    projection: list[dict[str, Any]] = field(default_factory=list)
    finished_at: float | None = None
    status_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    cancel_requested: bool = False
    done: asyncio.Event = field(default_factory=asyncio.Event)


class ChatRunManager:
    def __init__(
        self, *, config: Config, database: DatabaseManager, agent: Any
    ) -> None:
        self.config = config
        self.limits = config.chat_runs
        self.database = database
        self.agent = agent
        self.repository = ChatRunRepository(database)
        self.repository.recover()
        self.runs: dict[str, ChatRun] = {}
        self.queues: dict[str, deque[str]] = {}
        self.active: dict[str, str] = {}
        self.blocked: set[str] = set()
        self.deleting: set[str] = set()
        self.closing = False
        self.admission_lock = asyncio.Lock()
        self.admissions: set[asyncio.Task] = set()
        self.broker = InteractionBroker(
            self.publish,
            limit=self.limits.max_pending_inputs,
            timeout=self.limits.input_timeout_seconds,
        )

    async def lookup_key(self, key: str, fingerprint: str) -> dict[str, Any] | None:
        row = await asyncio.to_thread(self.repository.by_key, key)
        if row and row["fingerprint"] != fingerprint:
            raise InteractionError(
                "The idempotency key was used for a different request."
            )
        return self.describe(row) if row else None

    async def enqueue(
        self,
        *,
        key: str,
        fingerprint: str,
        thread_id: str,
        prepare: Callable[[], dict[str, Any]],
        interactive: bool = True,
    ) -> dict[str, Any]:
        task = asyncio.create_task(
            self._enqueue(
                key=key,
                fingerprint=fingerprint,
                thread_id=thread_id,
                prepare=prepare,
                interactive=interactive,
            )
        )
        self.admissions.add(task)

        def finished(task):
            self.admissions.discard(task)
            if not task.cancelled():
                task.exception()

        task.add_done_callback(finished)
        return await asyncio.shield(task)

    async def _enqueue(
        self,
        *,
        key: str,
        fingerprint: str,
        thread_id: str,
        prepare: Callable[[], dict[str, Any]],
        interactive: bool,
    ) -> dict[str, Any]:
        async with self.admission_lock:
            previous = await self.lookup_key(key, fingerprint)
            if previous:
                return previous
            if self.closing or thread_id in self.deleting or thread_id in self.blocked:
                raise InteractionError("This conversation cannot accept a new run.")
            queue = self.queues.setdefault(thread_id, deque())
            if len(queue) >= self.limits.max_queued_per_thread:
                raise InteractionError("The conversation queue is full.", 429)
            # Serialize admission only; answers never wait for this lock.
            submission = await asyncio.to_thread(prepare)
            submission["interactive"] = interactive
            row = await asyncio.to_thread(
                self.repository.create,
                run_id=uuid4().hex,
                idempotency_key=key,
                fingerprint=fingerprint,
                thread_id=thread_id,
                status="queued",
                submission=submission,
            )
            run = ChatRun(row)
            self.runs[row["run_id"]] = run
            queue.append(row["run_id"])
            self._schedule()
            return self.describe(row)

    def _prune(self) -> None:
        cutoff = monotonic() - self.limits.terminal_retention_seconds
        for rid, run in list(self.runs.items()):
            if (
                run.finished_at is not None
                and run.finished_at < cutoff
                and not run.subscribers
            ):
                self.runs.pop(rid)
                self.broker.forget(rid)

    def _schedule(self) -> None:
        self._prune()
        if self.closing:
            return
        for tid, queue in self.queues.items():
            if len(self.active) >= self.limits.max_active:
                break
            if (
                not queue
                or tid in self.active
                or tid in self.deleting
                or tid in self.blocked
            ):
                continue
            rid = queue.popleft()
            self.active[tid] = rid
            self.runs[rid].task = asyncio.create_task(self._execute(self.runs[rid]))

    def describe(self, row: dict[str, Any]) -> dict[str, Any]:
        rid = row["run_id"]
        run = self.runs.get(rid)
        submission = row["submission"]
        return {
            "run_id": rid,
            "thread_id": row["thread_id"],
            "status": row["status"],
            "sequence": row["sequence"],
            "prompt": submission["prompt"],
            "message_id": submission["human_message"]["data"].get("id", ""),
            "selection_id": submission["selection_id"],
            "detail": localize_error(row["detail"], submission["locale"])
            if row.get("detail")
            else None,
            "pending_inputs": self.broker.list_pending(rid),
            "last_event_id": run.sequence if run else 0,
            "resolved_attachments": submission.get("resolved_attachments", []),
            "requires_image_input": submission.get("requires_image_input", False),
            "attachment_count": submission.get("attachment_count", 0),
        }

    async def get(self, rid: str) -> dict[str, Any]:
        self._prune()
        row = (
            self.runs[rid].row
            if rid in self.runs
            else await asyncio.to_thread(self.repository.get, rid)
        )
        if row is None:
            raise InteractionError("Chat run not found.", 404)
        return self.describe(row)

    async def list(self, tid: str) -> list[dict[str, Any]]:
        rows = await asyncio.to_thread(self.repository.list, tid)
        return [await self.get(row["run_id"]) for row in rows]

    async def unstarted_history(self, tid: str) -> dict[str, Any] | None:
        rows = await asyncio.to_thread(self.repository.list, tid)
        if not rows:
            return None
        latest = rows[-1]
        return {
            "thread_id": tid,
            "title": rows[0]["submission"]["prompt"][:40] or tid,
            "last_message_preview": latest["submission"]["prompt"][:80],
            "message_count": 0,
            "messages": [],
            "updated_at": latest["created_at"],
            "attachment_count": latest["submission"].get("attachment_count", 0),
            "requires_image_input": latest["submission"].get(
                "requires_image_input", False
            ),
        }

    async def unstarted_histories(self) -> list[dict[str, Any]]:
        threads = await asyncio.to_thread(self.repository.unstarted_threads)
        return [
            history
            for tid in threads
            if (history := await self.unstarted_history(tid)) is not None
        ]

    async def _status(
        self, run: ChatRun, status: str, detail: str | None = None
    ) -> None:
        async with run.status_lock:
            if status in {"running", "waiting_input"}:
                status = (
                    "waiting_input"
                    if self.broker.list_pending(run.row["run_id"])
                    else "running"
                )
            run.row.update(status=status, detail=detail)
            write = asyncio.create_task(
                asyncio.to_thread(
                    self.repository.status, run.row["run_id"], status, detail
                )
            )
            try:
                await asyncio.shield(write)
            except asyncio.CancelledError:
                await write
                raise
            await self.publish(
                run.row["run_id"], "run_status", {"status": status, "detail": detail}
            )

    async def publish(self, rid: str, event: str, data: dict[str, Any]) -> None:
        run = self.runs[rid]
        data = to_jsonable(data)
        run.sequence += 1
        data = {
            "thread_id": run.row["thread_id"],
            **data,
            "run_id": rid,
            "event_id": run.sequence,
        }
        item = {"event": event, "data": data}
        encoded = render_sse_event(event, data)
        size = len(encoded.encode())
        run.events.append((run.sequence, encoded, size))
        run.event_bytes += size
        while (
            len(run.events) > self.limits.replay_events
            or run.event_bytes > self.limits.replay_bytes
        ):
            run.event_bytes -= run.events.popleft()[2]
        # The snapshot stores the current display, not an unbounded token event log.
        if (
            event in {"token", "reasoning"}
            and run.projection
            and run.projection[-1]["event"] == event
        ):
            run.projection[-1]["data"]["content"] += data.get("content", "")
        elif event not in {"input_required", "input_resolved", "run_status"}:
            run.projection.append(item)
        for queue in tuple(run.subscribers):
            if queue.full():
                run.subscribers.discard(queue)
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(None)
            else:
                queue.put_nowait(encoded)
        if event in {"input_required", "input_resolved"}:
            await self._status(run, "running")

    async def stream(self, rid: str, after: int = 0) -> AsyncIterator[str]:
        current = await self.get(rid)
        run = self.runs.get(rid)
        if run is None:
            yield render_sse_event("snapshot", {**current, "events": [], "event_id": 0})
            return
        queue = asyncio.Queue(maxsize=self.limits.subscriber_events)
        # No await between capturing the watermark/history and subscribing.
        if (
            after == 0
            or (after >= 0 and run.events and after < run.events[0][0] - 1)
            or after > run.sequence
        ):
            initial = [
                render_sse_event(
                    "snapshot",
                    {**current, "events": run.projection, "event_id": run.sequence},
                )
            ]
        else:
            initial = [encoded for seq, encoded, _ in run.events if seq > after]
        run.subscribers.add(queue)
        try:
            for encoded in initial:
                yield encoded
            while not run.done.is_set() or not queue.empty():
                try:
                    encoded = await asyncio.wait_for(queue.get(), 15)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if encoded is None:
                    return
                yield encoded
        finally:
            run.subscribers.discard(queue)

    async def _selection(self, selection_id: int) -> ModelSelection:
        return await asyncio.to_thread(self._selection_sync, selection_id)

    def _selection_sync(self, selection_id: int) -> ModelSelection:
        with self.database.get_session_factory()() as session:
            selection = ModelSelectionService(
                ModelSelectionRepository(session)
            ).get_by_id(selection_id)
            if selection is None:
                raise ValueError(f"Model selection not found: {selection_id}")
            return selection

    async def _close_checkpoint(self, tid: str, messages: Sequence = ()) -> None:
        config = {"configurable": {"thread_id": tid}}
        snapshot = await self.agent.aget_state(config, subgraphs=True)
        if not snapshot.next and not messages:
            return
        if not snapshot.values and not messages:
            return
        collected = list(snapshot.values.get("messages", []))
        # Supervisor has one nested model_call graph; its state may not yet be committed to the parent.
        for task in snapshot.tasks:
            child = getattr(task, "state", None)
            if child is not None and hasattr(child, "values"):
                collected = add_messages(collected, child.values.get("messages", []))
        collected = add_messages(collected, list(messages))
        answered = {
            msg.tool_call_id
            for msg in collected
            if isinstance(msg, ToolMessage) and msg.content != "[INTERRUPT_TOOL_CALLED]"
        }
        repairs = []
        for msg in collected:
            for call in getattr(msg, "tool_calls", []):
                if call["id"] not in answered:
                    placeholder = next(
                        (
                            m
                            for m in collected
                            if isinstance(m, ToolMessage)
                            and m.tool_call_id == call["id"]
                        ),
                        None,
                    )
                    repairs.append(
                        ToolMessage(
                            id=placeholder.id if placeholder else None,
                            tool_call_id=call["id"],
                            name=call["name"],
                            status="error",
                            content="Execution ended. The result is unknown; do not automatically repeat this operation.",
                        )
                    )
        values = {
            "messages": add_messages(collected, repairs),
            "context_compaction": None,
            "context_compaction_error": None,
            "context_compaction_event_pending": False,
        }
        # Completing the parent node discards the interrupted child continuation.
        await self.agent.aupdate_state(config, values, as_node="model_call")

    async def _execute(self, run: ChatRun) -> None:
        rid, tid = run.row["run_id"], run.row["thread_id"]
        sub = run.row["submission"]
        context = InteractionContext(
            self.broker,
            rid,
            tid,
            interactive=sub["interactive"],
            resolve_model=lambda: self._selection(sub["selection_id"]),
            locale=sub["locale"],
        )
        token = interaction_context.set(context)
        status, detail = "completed", None
        try:
            await self._status(run, "running")
            await self._close_checkpoint(tid)
            selection = await self._selection(sub["selection_id"])

            def validate_files():
                with self.database.get_session_factory()() as session:
                    files = ChatFileService(
                        ChatFileRepository(session),
                        ChatThreadFileRepository(session),
                        upload_dir=self.config.chat_file_upload_dir,
                    )
                    for file_id in sub.get("file_ids", []):
                        files.get_file_detail(file_id)

            await asyncio.to_thread(validate_files)
            initial = messages_from_dict([sub["human_message"]])
            context.messages.extend(initial)
            await self.publish(rid, "thread", self.describe(run.row))
            final_state = None
            async for event in self.agent.astream_events(
                {"model": selection, "messages": initial},
                {
                    "configurable": {"thread_id": tid},
                    "recursion_limit": self.config.graph_recursion_limit,
                },
                version="v2",
            ):
                name, kind = event.get("name"), event.get("event")
                data = event.get("data") or {}
                if kind == "on_custom_event":
                    if name == "on_app_tool_start":
                        await self.publish(
                            rid,
                            "tool_start",
                            {
                                "tool_name": data["tool_name"],
                                "input": data.get("input"),
                                "tool_call_id": data["tool_call_id"],
                            },
                        )
                    elif name == "on_app_tool_end":
                        output = data.get("output")
                        failed = getattr(output, "status", None) == "error"
                        await self.publish(
                            rid,
                            "tool_error" if failed else "tool_end",
                            {
                                "tool_name": data["tool_name"],
                                "tool_call_id": data["tool_call_id"],
                                **(
                                    {"detail": str(getattr(output, "content", output))}
                                    if failed
                                    else {
                                        "output": summarize_tool_output(
                                            data["tool_name"], output
                                        )
                                    }
                                ),
                            },
                        )
                    elif name == "on_tool_call_error":
                        await self.publish(
                            rid, "tool_error", {**data, "detail": data.get("error")}
                        )
                    elif name in {"on_context_compaction", "on_reasoning_done"}:
                        await self.publish(rid, name.removeprefix("on_"), data)
                elif kind in {"on_chat_model_stream", "on_llm_stream"}:
                    chunk = data.get("chunk")
                    text, reasoning = (
                        _extract_chunk_text(chunk),
                        _extract_chunk_reasoning(chunk),
                    )
                    if text:
                        await self.publish(rid, "token", {"content": text})
                    elif reasoning:
                        await self.publish(rid, "reasoning", {"content": reasoning})
                output = _extract_event_output(event)
                if output is not None:
                    final_state = output
            await self.publish(
                rid,
                "final",
                {
                    "content": _extract_content(
                        final_state.get("messages", []) if final_state else []
                    )
                },
            )
        except asyncio.CancelledError:
            status = "cancelled"
        except Exception as error:
            status, detail = (
                "failed",
                localize_error(
                    "User input timed out."
                    if isinstance(error, TimeoutError)
                    else str(error),
                    sub["locale"],
                ),
            )
            await self.publish(rid, "error", {"detail": detail})
        finally:
            self.broker.cancel_run(rid)
            try:
                if status != "completed":
                    await self._close_checkpoint(tid, context.messages)
            except Exception as error:
                status, detail = "failed", f"Checkpoint finalization failed: {error}"
                self.blocked.add(tid)
                for queued in list(self.queues.get(tid, [])):
                    await self._finish_queued(queued, "failed", detail)
                self.queues[tid].clear()
            await self._status(run, status, detail)
            run.finished_at = monotonic()
            run.done.set()
            interaction_context.reset(token)
            self.active.pop(tid, None)
            self._schedule()
        if status == "cancelled":
            raise asyncio.CancelledError

    async def _finish_queued(
        self, rid: str, status: str = "cancelled", detail: str | None = None
    ) -> None:
        run = self.runs[rid]
        await self._status(run, status, detail)
        run.finished_at = monotonic()
        run.done.set()

    async def cancel(self, rid: str) -> dict[str, Any]:
        current = await self.get(rid)
        if current["status"] in TERMINAL:
            run = self.runs.get(rid)
            if run is not None and not run.done.is_set():
                if run.task is not None:
                    await asyncio.gather(run.task, return_exceptions=True)
                else:
                    await run.done.wait()
            return await self.get(rid)
        run = self.runs[rid]
        if run.task is not None:
            # Let a newly scheduled coroutine enter its cleanup scope before cancelling.
            if not run.cancel_requested:
                run.cancel_requested = True
                await asyncio.sleep(0)
                run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
        else:
            self.queues[run.row["thread_id"]].remove(rid)
            await self._finish_queued(rid)
        return await self.get(rid)

    async def delete_thread(self, tid: str) -> bool:
        async with self.admission_lock:
            self.deleting.add(tid)
        existed = bool(await asyncio.to_thread(self.repository.list, tid))
        for rid in list(self.queues.get(tid, [])):
            await self.cancel(rid)
        if tid in self.active:
            await self.cancel(self.active[tid])
        await asyncio.to_thread(self.repository.delete_thread, tid)
        for rid, run in list(self.runs.items()):
            if run.row["thread_id"] == tid:
                self.runs.pop(rid)
                self.broker.forget(rid)
        return existed

    async def shutdown(self) -> None:
        async with self.admission_lock:
            self.closing = True
        if self.admissions:
            await asyncio.gather(*tuple(self.admissions), return_exceptions=True)
        for rid, run in list(self.runs.items()):
            if not run.done.is_set():
                await self.cancel(rid)
