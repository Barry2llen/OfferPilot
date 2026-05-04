from __future__ import annotations

import random
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
    get_checkpoint_metadata,
)
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from db.engine import AsyncDatabaseManager, DatabaseManager
from db.models import (
    GraphCheckpointBlobORM,
    GraphCheckpointORM,
    GraphCheckpointWriteORM,
)
from db.repositories import AsyncCheckpointRepository, CheckpointRepository

ALLOWED_CHECKPOINT_MSGPACK_MODULES = [
    ("schemas.model_selection", "ModelSelection"),
]


class DatabaseCheckpointer(BaseCheckpointSaver[str]):
    """Persist LangGraph checkpoints in the configured relational database."""

    def __init__(
        self,
        sync_manager: DatabaseManager,
        async_manager: AsyncDatabaseManager,
        *,
        serde: Any | None = None,
    ) -> None:
        super().__init__(
            serde=serde
            or JsonPlusSerializer(
                allowed_msgpack_modules=ALLOWED_CHECKPOINT_MSGPACK_MODULES,
            )
        )
        self._sync_manager = sync_manager
        self._async_manager = async_manager

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id, checkpoint_ns, checkpoint_id = self._get_config_values(config)
        with self._sync_manager.session_scope() as session:
            repository = CheckpointRepository(session)
            row = repository.get_checkpoint(thread_id, checkpoint_ns, checkpoint_id)
            if row is None:
                return None

            writes = repository.list_writes(
                row.thread_id,
                row.checkpoint_ns,
                row.checkpoint_id,
            )
            checkpoint = self._deserialize_checkpoint(
                repository,
                row.thread_id,
                row.checkpoint_ns,
                row,
            )
            metadata = self.serde.loads_typed((row.metadata_type, row.metadata_payload))
            return self._build_checkpoint_tuple(
                config=config,
                row=row,
                checkpoint=checkpoint,
                metadata=metadata,
                writes=writes,
            )

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        before_id = get_checkpoint_id(before) if before is not None else None
        thread_ids = None
        checkpoint_ns = None
        target_checkpoint_id = None
        if config is not None:
            thread_id, checkpoint_ns, target_checkpoint_id = self._get_config_values(config)
            thread_ids = (thread_id,)

        with self._sync_manager.session_scope() as session:
            repository = CheckpointRepository(session)
            rows = repository.list_checkpoints(
                thread_ids=thread_ids,
                checkpoint_ns=checkpoint_ns,
            )
            remaining = limit
            for row in rows:
                if target_checkpoint_id and row.checkpoint_id != target_checkpoint_id:
                    continue
                if before_id and row.checkpoint_id >= before_id:
                    continue

                metadata = self.serde.loads_typed((row.metadata_type, row.metadata_payload))
                if filter and not self._metadata_matches(metadata, filter):
                    continue

                checkpoint = self._deserialize_checkpoint(
                    repository,
                    row.thread_id,
                    row.checkpoint_ns,
                    row,
                )
                writes = repository.list_writes(
                    row.thread_id,
                    row.checkpoint_ns,
                    row.checkpoint_id,
                )
                yield self._build_checkpoint_tuple(
                    config=config,
                    row=row,
                    checkpoint=checkpoint,
                    metadata=metadata,
                    writes=writes,
                )

                if remaining is not None:
                    remaining -= 1
                    if remaining <= 0:
                        break

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        thread_id, checkpoint_ns, parent_checkpoint_id = self._get_config_values(config)
        values = checkpoint.get("channel_values", {})
        checkpoint_body = checkpoint.copy()
        checkpoint_body.pop("channel_values", None)
        metadata_payload = get_checkpoint_metadata(config, metadata)

        checkpoint_row = GraphCheckpointORM(
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            checkpoint_id=checkpoint["id"],
            parent_checkpoint_id=parent_checkpoint_id,
            checkpoint_type=self.serde.dumps_typed(checkpoint_body)[0],
            checkpoint_payload=self.serde.dumps_typed(checkpoint_body)[1],
            metadata_type=self.serde.dumps_typed(metadata_payload)[0],
            metadata_payload=self.serde.dumps_typed(metadata_payload)[1],
            source=metadata_payload.get("source"),
            step=metadata_payload.get("step"),
            run_id=metadata_payload.get("run_id"),
        )
        blob_rows = [
            GraphCheckpointBlobORM(
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                channel=channel,
                version=str(version),
                value_type=value_pair[0],
                value_payload=value_pair[1],
            )
            for channel, version in new_versions.items()
            if channel in values
            for value_pair in [self.serde.dumps_typed(values[channel])]
        ]

        with self._sync_manager.session_scope() as session:
            repository = CheckpointRepository(session)
            repository.save_checkpoint(checkpoint_row)
            if blob_rows:
                repository.save_blobs(blob_rows)

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint["id"],
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id, checkpoint_ns, checkpoint_id = self._require_checkpoint_ref(config)
        keys = [
            (task_id, WRITES_IDX_MAP.get(channel, idx))
            for idx, (channel, _) in enumerate(writes)
        ]

        with self._sync_manager.session_scope() as session:
            repository = CheckpointRepository(session)
            existing = repository.get_existing_write_keys(
                thread_id,
                checkpoint_ns,
                checkpoint_id,
                keys,
            )

            rows: list[GraphCheckpointWriteORM] = []
            for idx, (channel, value) in enumerate(writes):
                write_idx = WRITES_IDX_MAP.get(channel, idx)
                if write_idx >= 0 and (task_id, write_idx) in existing:
                    continue

                value_type, value_payload = self.serde.dumps_typed(value)
                rows.append(
                    GraphCheckpointWriteORM(
                        thread_id=thread_id,
                        checkpoint_ns=checkpoint_ns,
                        checkpoint_id=checkpoint_id,
                        task_id=task_id,
                        write_idx=write_idx,
                        channel=channel,
                        value_type=value_type,
                        value_payload=value_payload,
                        task_path=task_path,
                    )
                )

            if rows:
                repository.save_writes(rows)

    def delete_thread(self, thread_id: str) -> None:
        with self._sync_manager.session_scope() as session:
            CheckpointRepository(session).delete_thread(thread_id)

    def delete_for_runs(self, run_ids: Sequence[str]) -> None:
        if not run_ids:
            return

        with self._sync_manager.session_scope() as session:
            repository = CheckpointRepository(session)
            rows = repository.list_checkpoints_for_run_ids(run_ids)
            keys = [
                (row.thread_id, row.checkpoint_ns, row.checkpoint_id)
                for row in rows
            ]
            repository.delete_checkpoints(keys)
            self._cleanup_orphan_blobs(repository, {row.thread_id for row in rows})

    def copy_thread(
        self,
        source_thread_id: str,
        target_thread_id: str,
    ) -> None:
        with self._sync_manager.session_scope() as session:
            repository = CheckpointRepository(session)
            source_rows = repository.list_checkpoints(thread_ids=(source_thread_id,))
            blob_rows = repository.list_blobs_for_threads((source_thread_id,))
            repository.delete_thread(target_thread_id)

            for row in source_rows:
                metadata = self.serde.loads_typed((row.metadata_type, row.metadata_payload))
                metadata["source"] = "fork"
                metadata_type, metadata_payload = self.serde.dumps_typed(metadata)
                repository.save_checkpoint(
                    GraphCheckpointORM(
                        thread_id=target_thread_id,
                        checkpoint_ns=row.checkpoint_ns,
                        checkpoint_id=row.checkpoint_id,
                        parent_checkpoint_id=row.parent_checkpoint_id,
                        checkpoint_type=row.checkpoint_type,
                        checkpoint_payload=row.checkpoint_payload,
                        metadata_type=metadata_type,
                        metadata_payload=metadata_payload,
                        source="fork",
                        step=row.step,
                        run_id=row.run_id,
                    )
                )

                writes = repository.list_writes(
                    row.thread_id,
                    row.checkpoint_ns,
                    row.checkpoint_id,
                )
                repository.save_writes(
                    [
                        GraphCheckpointWriteORM(
                            thread_id=target_thread_id,
                            checkpoint_ns=write.checkpoint_ns,
                            checkpoint_id=write.checkpoint_id,
                            task_id=write.task_id,
                            write_idx=write.write_idx,
                            channel=write.channel,
                            value_type=write.value_type,
                            value_payload=write.value_payload,
                            task_path=write.task_path,
                        )
                        for write in writes
                    ]
                )

            repository.save_blobs(
                [
                    GraphCheckpointBlobORM(
                        thread_id=target_thread_id,
                        checkpoint_ns=blob.checkpoint_ns,
                        channel=blob.channel,
                        version=blob.version,
                        value_type=blob.value_type,
                        value_payload=blob.value_payload,
                    )
                    for blob in blob_rows
                ]
            )

    def prune(
        self,
        thread_ids: Sequence[str],
        *,
        strategy: str = "keep_latest",
    ) -> None:
        if not thread_ids:
            return

        with self._sync_manager.session_scope() as session:
            repository = CheckpointRepository(session)
            if strategy == "delete":
                for thread_id in thread_ids:
                    repository.delete_thread(thread_id)
                return

            if strategy != "keep_latest":
                raise ValueError(f"Unsupported prune strategy: {strategy}")

            rows = repository.list_checkpoints(thread_ids=thread_ids)
            keep: set[tuple[str, str, str]] = set()
            seen_ns: set[tuple[str, str]] = set()
            for row in rows:
                ns_key = (row.thread_id, row.checkpoint_ns)
                if ns_key in seen_ns:
                    continue
                seen_ns.add(ns_key)
                keep.add((row.thread_id, row.checkpoint_ns, row.checkpoint_id))

            delete_keys = [
                (row.thread_id, row.checkpoint_ns, row.checkpoint_id)
                for row in rows
                if (row.thread_id, row.checkpoint_ns, row.checkpoint_id) not in keep
            ]
            repository.delete_checkpoints(delete_keys)
            self._cleanup_orphan_blobs(repository, set(thread_ids))

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id, checkpoint_ns, checkpoint_id = self._get_config_values(config)
        async with self._async_manager.session_scope() as session:
            repository = AsyncCheckpointRepository(session)
            row = await repository.get_checkpoint(thread_id, checkpoint_ns, checkpoint_id)
            if row is None:
                return None

            writes = await repository.list_writes(
                row.thread_id,
                row.checkpoint_ns,
                row.checkpoint_id,
            )
            checkpoint = await self._adeserialize_checkpoint(
                repository,
                row.thread_id,
                row.checkpoint_ns,
                row,
            )
            metadata = self.serde.loads_typed((row.metadata_type, row.metadata_payload))
            return self._build_checkpoint_tuple(
                config=config,
                row=row,
                checkpoint=checkpoint,
                metadata=metadata,
                writes=writes,
            )

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        before_id = get_checkpoint_id(before) if before is not None else None
        thread_ids = None
        checkpoint_ns = None
        target_checkpoint_id = None
        if config is not None:
            thread_id, checkpoint_ns, target_checkpoint_id = self._get_config_values(config)
            thread_ids = (thread_id,)

        async with self._async_manager.session_scope() as session:
            repository = AsyncCheckpointRepository(session)
            rows = await repository.list_checkpoints(
                thread_ids=thread_ids,
                checkpoint_ns=checkpoint_ns,
            )
            remaining = limit
            for row in rows:
                if target_checkpoint_id and row.checkpoint_id != target_checkpoint_id:
                    continue
                if before_id and row.checkpoint_id >= before_id:
                    continue

                metadata = self.serde.loads_typed((row.metadata_type, row.metadata_payload))
                if filter and not self._metadata_matches(metadata, filter):
                    continue

                checkpoint = await self._adeserialize_checkpoint(
                    repository,
                    row.thread_id,
                    row.checkpoint_ns,
                    row,
                )
                writes = await repository.list_writes(
                    row.thread_id,
                    row.checkpoint_ns,
                    row.checkpoint_id,
                )
                yield self._build_checkpoint_tuple(
                    config=config,
                    row=row,
                    checkpoint=checkpoint,
                    metadata=metadata,
                    writes=writes,
                )

                if remaining is not None:
                    remaining -= 1
                    if remaining <= 0:
                        break

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        thread_id, checkpoint_ns, parent_checkpoint_id = self._get_config_values(config)
        values = checkpoint.get("channel_values", {})
        checkpoint_body = checkpoint.copy()
        checkpoint_body.pop("channel_values", None)
        checkpoint_type, checkpoint_payload = self.serde.dumps_typed(checkpoint_body)
        metadata_payload = get_checkpoint_metadata(config, metadata)
        metadata_type, metadata_bytes = self.serde.dumps_typed(metadata_payload)

        checkpoint_row = GraphCheckpointORM(
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            checkpoint_id=checkpoint["id"],
            parent_checkpoint_id=parent_checkpoint_id,
            checkpoint_type=checkpoint_type,
            checkpoint_payload=checkpoint_payload,
            metadata_type=metadata_type,
            metadata_payload=metadata_bytes,
            source=metadata_payload.get("source"),
            step=metadata_payload.get("step"),
            run_id=metadata_payload.get("run_id"),
        )
        blob_rows = [
            GraphCheckpointBlobORM(
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                channel=channel,
                version=str(version),
                value_type=value_pair[0],
                value_payload=value_pair[1],
            )
            for channel, version in new_versions.items()
            if channel in values
            for value_pair in [self.serde.dumps_typed(values[channel])]
        ]

        async with self._async_manager.session_scope() as session:
            repository = AsyncCheckpointRepository(session)
            await repository.save_checkpoint(checkpoint_row)
            if blob_rows:
                await repository.save_blobs(blob_rows)

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint["id"],
            }
        }

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id, checkpoint_ns, checkpoint_id = self._require_checkpoint_ref(config)
        keys = [
            (task_id, WRITES_IDX_MAP.get(channel, idx))
            for idx, (channel, _) in enumerate(writes)
        ]

        async with self._async_manager.session_scope() as session:
            repository = AsyncCheckpointRepository(session)
            existing = await repository.get_existing_write_keys(
                thread_id,
                checkpoint_ns,
                checkpoint_id,
                keys,
            )

            rows: list[GraphCheckpointWriteORM] = []
            for idx, (channel, value) in enumerate(writes):
                write_idx = WRITES_IDX_MAP.get(channel, idx)
                if write_idx >= 0 and (task_id, write_idx) in existing:
                    continue

                value_type, value_payload = self.serde.dumps_typed(value)
                rows.append(
                    GraphCheckpointWriteORM(
                        thread_id=thread_id,
                        checkpoint_ns=checkpoint_ns,
                        checkpoint_id=checkpoint_id,
                        task_id=task_id,
                        write_idx=write_idx,
                        channel=channel,
                        value_type=value_type,
                        value_payload=value_payload,
                        task_path=task_path,
                    )
                )

            if rows:
                await repository.save_writes(rows)

    async def adelete_thread(self, thread_id: str) -> None:
        async with self._async_manager.session_scope() as session:
            await AsyncCheckpointRepository(session).delete_thread(thread_id)

    async def adelete_for_runs(self, run_ids: Sequence[str]) -> None:
        if not run_ids:
            return

        async with self._async_manager.session_scope() as session:
            repository = AsyncCheckpointRepository(session)
            rows = await repository.list_checkpoints_for_run_ids(run_ids)
            keys = [
                (row.thread_id, row.checkpoint_ns, row.checkpoint_id)
                for row in rows
            ]
            await repository.delete_checkpoints(keys)
            await self._acleanup_orphan_blobs(repository, {row.thread_id for row in rows})

    async def acopy_thread(
        self,
        source_thread_id: str,
        target_thread_id: str,
    ) -> None:
        async with self._async_manager.session_scope() as session:
            repository = AsyncCheckpointRepository(session)
            source_rows = await repository.list_checkpoints(thread_ids=(source_thread_id,))
            blob_rows = await repository.list_blobs_for_threads((source_thread_id,))
            await repository.delete_thread(target_thread_id)

            for row in source_rows:
                metadata = self.serde.loads_typed((row.metadata_type, row.metadata_payload))
                metadata["source"] = "fork"
                metadata_type, metadata_payload = self.serde.dumps_typed(metadata)
                await repository.save_checkpoint(
                    GraphCheckpointORM(
                        thread_id=target_thread_id,
                        checkpoint_ns=row.checkpoint_ns,
                        checkpoint_id=row.checkpoint_id,
                        parent_checkpoint_id=row.parent_checkpoint_id,
                        checkpoint_type=row.checkpoint_type,
                        checkpoint_payload=row.checkpoint_payload,
                        metadata_type=metadata_type,
                        metadata_payload=metadata_payload,
                        source="fork",
                        step=row.step,
                        run_id=row.run_id,
                    )
                )

                writes = await repository.list_writes(
                    row.thread_id,
                    row.checkpoint_ns,
                    row.checkpoint_id,
                )
                await repository.save_writes(
                    [
                        GraphCheckpointWriteORM(
                            thread_id=target_thread_id,
                            checkpoint_ns=write.checkpoint_ns,
                            checkpoint_id=write.checkpoint_id,
                            task_id=write.task_id,
                            write_idx=write.write_idx,
                            channel=write.channel,
                            value_type=write.value_type,
                            value_payload=write.value_payload,
                            task_path=write.task_path,
                        )
                        for write in writes
                    ]
                )

            await repository.save_blobs(
                [
                    GraphCheckpointBlobORM(
                        thread_id=target_thread_id,
                        checkpoint_ns=blob.checkpoint_ns,
                        channel=blob.channel,
                        version=blob.version,
                        value_type=blob.value_type,
                        value_payload=blob.value_payload,
                    )
                    for blob in blob_rows
                ]
            )

    async def aprune(
        self,
        thread_ids: Sequence[str],
        *,
        strategy: str = "keep_latest",
    ) -> None:
        if not thread_ids:
            return

        async with self._async_manager.session_scope() as session:
            repository = AsyncCheckpointRepository(session)
            if strategy == "delete":
                for thread_id in thread_ids:
                    await repository.delete_thread(thread_id)
                return

            if strategy != "keep_latest":
                raise ValueError(f"Unsupported prune strategy: {strategy}")

            rows = await repository.list_checkpoints(thread_ids=thread_ids)
            keep: set[tuple[str, str, str]] = set()
            seen_ns: set[tuple[str, str]] = set()
            for row in rows:
                ns_key = (row.thread_id, row.checkpoint_ns)
                if ns_key in seen_ns:
                    continue
                seen_ns.add(ns_key)
                keep.add((row.thread_id, row.checkpoint_ns, row.checkpoint_id))

            delete_keys = [
                (row.thread_id, row.checkpoint_ns, row.checkpoint_id)
                for row in rows
                if (row.thread_id, row.checkpoint_ns, row.checkpoint_id) not in keep
            ]
            await repository.delete_checkpoints(delete_keys)
            await self._acleanup_orphan_blobs(repository, set(thread_ids))

    def get_next_version(self, current: str | None, channel: None) -> str:
        if current is None:
            current_v = 0
        elif isinstance(current, int):
            current_v = current
        else:
            current_v = int(str(current).split(".")[0])
        next_v = current_v + 1
        next_h = random.random()
        return f"{next_v:032}.{next_h:016}"

    def _build_checkpoint_tuple(
        self,
        *,
        config: RunnableConfig | None,
        row: GraphCheckpointORM,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        writes: Sequence[GraphCheckpointWriteORM],
    ) -> CheckpointTuple:
        checkpoint_config = cast(
            RunnableConfig,
            {
                "configurable": {
                    "thread_id": row.thread_id,
                    "checkpoint_ns": row.checkpoint_ns,
                    "checkpoint_id": row.checkpoint_id,
                }
            },
        )
        parent_config = (
            cast(
                RunnableConfig,
                {
                    "configurable": {
                        "thread_id": row.thread_id,
                        "checkpoint_ns": row.checkpoint_ns,
                        "checkpoint_id": row.parent_checkpoint_id,
                    }
                },
            )
            if row.parent_checkpoint_id
            else None
        )
        return CheckpointTuple(
            config=checkpoint_config,
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=parent_config,
            pending_writes=[
                (
                    write.task_id,
                    write.channel,
                    self.serde.loads_typed((write.value_type, write.value_payload)),
                )
                for write in writes
            ],
        )

    def _deserialize_checkpoint(
        self,
        repository: CheckpointRepository,
        thread_id: str,
        checkpoint_ns: str,
        row: GraphCheckpointORM,
    ) -> Checkpoint:
        checkpoint = self.serde.loads_typed((row.checkpoint_type, row.checkpoint_payload))
        versions = {
            channel: str(version)
            for channel, version in checkpoint["channel_versions"].items()
        }
        blobs = repository.list_blobs(thread_id, checkpoint_ns, versions)
        channel_values = {
            blob.channel: self.serde.loads_typed((blob.value_type, blob.value_payload))
            for blob in blobs
        }
        return cast(Checkpoint, {**checkpoint, "channel_values": channel_values})

    async def _adeserialize_checkpoint(
        self,
        repository: AsyncCheckpointRepository,
        thread_id: str,
        checkpoint_ns: str,
        row: GraphCheckpointORM,
    ) -> Checkpoint:
        checkpoint = self.serde.loads_typed((row.checkpoint_type, row.checkpoint_payload))
        versions = {
            channel: str(version)
            for channel, version in checkpoint["channel_versions"].items()
        }
        blobs = await repository.list_blobs(thread_id, checkpoint_ns, versions)
        channel_values = {
            blob.channel: self.serde.loads_typed((blob.value_type, blob.value_payload))
            for blob in blobs
        }
        return cast(Checkpoint, {**checkpoint, "channel_values": channel_values})

    def _cleanup_orphan_blobs(
        self,
        repository: CheckpointRepository,
        thread_ids: set[str],
    ) -> None:
        if not thread_ids:
            return

        checkpoints = repository.list_checkpoints(thread_ids=tuple(thread_ids))
        referenced = {
            (row.thread_id, row.checkpoint_ns, channel, str(version))
            for row in checkpoints
            for channel, version in self.serde.loads_typed(
                (row.checkpoint_type, row.checkpoint_payload)
            )["channel_versions"].items()
        }
        blobs = repository.list_blobs_for_threads(tuple(thread_ids))
        delete_keys = [
            (blob.thread_id, blob.checkpoint_ns, blob.channel, blob.version)
            for blob in blobs
            if (blob.thread_id, blob.checkpoint_ns, blob.channel, blob.version)
            not in referenced
        ]
        repository.delete_blobs(delete_keys)

    async def _acleanup_orphan_blobs(
        self,
        repository: AsyncCheckpointRepository,
        thread_ids: set[str],
    ) -> None:
        if not thread_ids:
            return

        checkpoints = await repository.list_checkpoints(thread_ids=tuple(thread_ids))
        referenced = {
            (row.thread_id, row.checkpoint_ns, channel, str(version))
            for row in checkpoints
            for channel, version in self.serde.loads_typed(
                (row.checkpoint_type, row.checkpoint_payload)
            )["channel_versions"].items()
        }
        blobs = await repository.list_blobs_for_threads(tuple(thread_ids))
        delete_keys = [
            (blob.thread_id, blob.checkpoint_ns, blob.channel, blob.version)
            for blob in blobs
            if (blob.thread_id, blob.checkpoint_ns, blob.channel, blob.version)
            not in referenced
        ]
        await repository.delete_blobs(delete_keys)

    @staticmethod
    def _metadata_matches(
        metadata: CheckpointMetadata,
        expected: dict[str, Any],
    ) -> bool:
        return all(metadata.get(key) == value for key, value in expected.items())

    @staticmethod
    def _get_config_values(config: RunnableConfig) -> tuple[str, str, str | None]:
        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id")
        if not thread_id:
            raise ValueError("Checkpoint operations require configurable.thread_id.")
        checkpoint_ns = configurable.get("checkpoint_ns", "")
        checkpoint_id = configurable.get("checkpoint_id")
        return str(thread_id), str(checkpoint_ns), checkpoint_id

    def _require_checkpoint_ref(self, config: RunnableConfig) -> tuple[str, str, str]:
        thread_id, checkpoint_ns, checkpoint_id = self._get_config_values(config)
        if not checkpoint_id:
            raise ValueError(
                "Checkpoint writes require configurable.checkpoint_id."
            )
        return thread_id, checkpoint_ns, checkpoint_id
