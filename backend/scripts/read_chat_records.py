from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import BaseMessage

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agent.checkpointers import DatabaseCheckpointer
from db.engine import AsyncDatabaseManager, DatabaseManager
from db.repositories import CheckpointRepository
from schemas.config.database import SQLiteDatabaseConfig


ROLE_BY_MESSAGE_TYPE = {
    "human": "user",
    "ai": "assistant",
    "tool": "tool",
    "system": "system",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="读取本地 SQLite 中的 LangGraph AI 聊天记录。",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/offer_pilot.db"),
        help="SQLite 数据库路径，默认 data/offer_pilot.db。",
    )
    parser.add_argument(
        "--thread-id",
        help="只查看指定 thread_id。",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="未指定 thread_id 时，最多读取多少个最新会话。默认 20。",
    )
    parser.add_argument(
        "--all-checkpoints",
        action="store_true",
        help="输出匹配会话的所有 checkpoint，而不是只输出最新 checkpoint。",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="以缩进 JSON 输出。",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="只输出 checkpoint 元数据、消息数量和消息类型，不输出完整 messages。",
    )
    return parser.parse_args()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = parse_args()
    database_path = args.db.resolve()
    if not database_path.exists():
        raise SystemExit(f"数据库文件不存在: {database_path}")

    config = SQLiteDatabaseConfig(path=str(database_path))
    sync_manager = DatabaseManager(config)
    async_manager = AsyncDatabaseManager(config)
    checkpointer = DatabaseCheckpointer(sync_manager, async_manager)

    try:
        records = read_records(
            sync_manager=sync_manager,
            checkpointer=checkpointer,
            thread_id=args.thread_id,
            limit=args.limit,
            all_checkpoints=args.all_checkpoints,
            summary_only=args.summary_only,
        )
    finally:
        sync_manager.dispose()

    indent = 2 if args.pretty else None
    print(json.dumps(records, ensure_ascii=False, indent=indent))


def read_records(
    *,
    sync_manager: DatabaseManager,
    checkpointer: DatabaseCheckpointer,
    thread_id: str | None,
    limit: int,
    all_checkpoints: bool,
    summary_only: bool,
) -> dict[str, Any]:
    with sync_manager.session_scope() as session:
        repository = CheckpointRepository(session)
        if thread_id:
            rows = repository.list_checkpoints(thread_ids=(thread_id,), checkpoint_ns="")
            if not all_checkpoints:
                rows = rows[:1]
        elif all_checkpoints:
            rows = repository.list_checkpoints(checkpoint_ns="")
            rows = rows[:limit]
        else:
            rows = repository.list_latest_checkpoints_by_thread(limit=limit)

        checkpoints = []
        for row in rows:
            checkpoint_tuple = checkpointer.get_tuple(
                {
                    "configurable": {
                        "thread_id": row.thread_id,
                        "checkpoint_ns": row.checkpoint_ns,
                        "checkpoint_id": row.checkpoint_id,
                    }
                }
            )
            messages = []
            if checkpoint_tuple is not None:
                raw_messages = checkpoint_tuple.checkpoint.get("channel_values", {}).get(
                    "messages"
                )
                if isinstance(raw_messages, list):
                    messages = raw_messages

            checkpoint_payload = {
                "thread_id": row.thread_id,
                "checkpoint_ns": row.checkpoint_ns,
                "checkpoint_id": row.checkpoint_id,
                "parent_checkpoint_id": row.parent_checkpoint_id,
                "source": row.source,
                "step": row.step,
                "run_id": row.run_id,
                "created_at": _jsonable(row.created_at),
                "message_count": len(messages),
                "message_types": [_message_type(message) for message in messages],
            }
            if not summary_only:
                checkpoint_payload["messages"] = [
                    _message_to_payload(message) for message in messages
                ]
            checkpoints.append(checkpoint_payload)

        return {
            "checkpoint_count": len(checkpoints),
            "checkpoints": checkpoints,
        }


def _message_to_payload(message: Any) -> dict[str, Any]:
    message_type = _message_type(message)
    payload: dict[str, Any] = {
        "role": ROLE_BY_MESSAGE_TYPE.get(message_type, message_type),
        "type": message_type,
        "content": _jsonable(_message_content(message)),
    }

    for attr in ("name", "tool_call_id", "status"):
        value = _message_attr(message, attr)
        if value is not None:
            payload[attr] = _jsonable(value)

    additional_kwargs = _message_attr(message, "additional_kwargs")
    if additional_kwargs:
        payload["additional_kwargs"] = _jsonable(additional_kwargs)

    response_metadata = _message_attr(message, "response_metadata")
    if response_metadata:
        payload["response_metadata"] = _jsonable(response_metadata)

    tool_calls = _message_attr(message, "tool_calls")
    if tool_calls:
        payload["tool_calls"] = _jsonable(tool_calls)

    invalid_tool_calls = _message_attr(message, "invalid_tool_calls")
    if invalid_tool_calls:
        payload["invalid_tool_calls"] = _jsonable(invalid_tool_calls)

    return payload


def _message_type(message: Any) -> str:
    if isinstance(message, BaseMessage):
        return message.type
    if isinstance(message, dict):
        return str(message.get("type") or "message")
    return type(message).__name__


def _message_content(message: Any) -> Any:
    if isinstance(message, BaseMessage):
        return message.content
    if isinstance(message, dict) and "content" in message:
        return message["content"]
    return message


def _message_attr(message: Any, attr: str) -> Any:
    if isinstance(message, BaseMessage):
        return getattr(message, attr, None)
    if isinstance(message, dict):
        return message.get(attr)
    return None


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseMessage):
        return _message_to_payload(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime | date):
        return value.isoformat()

    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


if __name__ == "__main__":
    main()
