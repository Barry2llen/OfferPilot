from collections.abc import Sequence

from sqlalchemy import Select, delete, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from db.models import (
    GraphCheckpointBlobORM,
    GraphCheckpointORM,
    GraphCheckpointWriteORM,
)


class CheckpointRepository:
    """Synchronous repository for persisted graph checkpoints."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_checkpoint(
        self,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str | None = None,
    ) -> GraphCheckpointORM | None:
        statement = select(GraphCheckpointORM).where(
            GraphCheckpointORM.thread_id == thread_id,
            GraphCheckpointORM.checkpoint_ns == checkpoint_ns,
        )
        if checkpoint_id is not None:
            statement = statement.where(GraphCheckpointORM.checkpoint_id == checkpoint_id)
        else:
            statement = statement.order_by(GraphCheckpointORM.checkpoint_id.desc()).limit(1)

        return self._session.scalar(statement)

    def list_checkpoints(
        self,
        *,
        thread_ids: Sequence[str] | None = None,
        checkpoint_ns: str | None = None,
    ) -> list[GraphCheckpointORM]:
        statement: Select[tuple[GraphCheckpointORM]] = select(GraphCheckpointORM)
        if thread_ids:
            statement = statement.where(GraphCheckpointORM.thread_id.in_(thread_ids))
        if checkpoint_ns is not None:
            statement = statement.where(GraphCheckpointORM.checkpoint_ns == checkpoint_ns)

        statement = statement.order_by(
            GraphCheckpointORM.thread_id.asc(),
            GraphCheckpointORM.checkpoint_ns.asc(),
            GraphCheckpointORM.checkpoint_id.desc(),
        )
        return self._session.scalars(statement).all()

    def list_latest_checkpoints_by_thread(
        self,
        *,
        checkpoint_ns: str = "",
        limit: int = 20,
        offset: int = 0,
    ) -> list[GraphCheckpointORM]:
        latest = (
            select(
                GraphCheckpointORM.thread_id.label("thread_id"),
                func.max(GraphCheckpointORM.checkpoint_id).label("checkpoint_id"),
            )
            .where(GraphCheckpointORM.checkpoint_ns == checkpoint_ns)
            .group_by(GraphCheckpointORM.thread_id)
            .subquery()
        )
        statement = (
            select(GraphCheckpointORM)
            .join(
                latest,
                (GraphCheckpointORM.thread_id == latest.c.thread_id)
                & (GraphCheckpointORM.checkpoint_id == latest.c.checkpoint_id),
            )
            .where(GraphCheckpointORM.checkpoint_ns == checkpoint_ns)
            .order_by(
                GraphCheckpointORM.created_at.desc(),
                GraphCheckpointORM.checkpoint_id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        return self._session.scalars(statement).all()

    def list_checkpoints_for_run_ids(
        self, run_ids: Sequence[str]
    ) -> list[GraphCheckpointORM]:
        if not run_ids:
            return []

        statement = select(GraphCheckpointORM).where(GraphCheckpointORM.run_id.in_(run_ids))
        return self._session.scalars(statement).all()

    def list_writes(
        self,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str,
    ) -> list[GraphCheckpointWriteORM]:
        statement = (
            select(GraphCheckpointWriteORM)
            .where(
                GraphCheckpointWriteORM.thread_id == thread_id,
                GraphCheckpointWriteORM.checkpoint_ns == checkpoint_ns,
                GraphCheckpointWriteORM.checkpoint_id == checkpoint_id,
            )
            .order_by(GraphCheckpointWriteORM.id.asc())
        )
        return self._session.scalars(statement).all()

    def get_existing_write_keys(
        self,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str,
        keys: Sequence[tuple[str, int]],
    ) -> set[tuple[str, int]]:
        if not keys:
            return set()

        statement = select(
            GraphCheckpointWriteORM.task_id,
            GraphCheckpointWriteORM.write_idx,
        ).where(
            GraphCheckpointWriteORM.thread_id == thread_id,
            GraphCheckpointWriteORM.checkpoint_ns == checkpoint_ns,
            GraphCheckpointWriteORM.checkpoint_id == checkpoint_id,
            tuple_(
                GraphCheckpointWriteORM.task_id,
                GraphCheckpointWriteORM.write_idx,
            ).in_(keys),
        )
        return set(self._session.execute(statement).all())

    def list_blobs(
        self,
        thread_id: str,
        checkpoint_ns: str,
        versions: dict[str, str],
    ) -> list[GraphCheckpointBlobORM]:
        if not versions:
            return []

        pairs = [(channel, version) for channel, version in versions.items()]
        statement = select(GraphCheckpointBlobORM).where(
            GraphCheckpointBlobORM.thread_id == thread_id,
            GraphCheckpointBlobORM.checkpoint_ns == checkpoint_ns,
            tuple_(
                GraphCheckpointBlobORM.channel,
                GraphCheckpointBlobORM.version,
            ).in_(pairs),
        )
        return self._session.scalars(statement).all()

    def list_blobs_for_threads(
        self, thread_ids: Sequence[str]
    ) -> list[GraphCheckpointBlobORM]:
        if not thread_ids:
            return []

        statement = select(GraphCheckpointBlobORM).where(
            GraphCheckpointBlobORM.thread_id.in_(thread_ids)
        )
        return self._session.scalars(statement).all()

    def save_checkpoint(self, checkpoint: GraphCheckpointORM) -> None:
        self._session.merge(checkpoint)
        self._session.flush()

    def save_blobs(self, blobs: Sequence[GraphCheckpointBlobORM]) -> None:
        for blob in blobs:
            self._session.merge(blob)
        self._session.flush()

    def save_writes(self, writes: Sequence[GraphCheckpointWriteORM]) -> None:
        for write in writes:
            statement = select(GraphCheckpointWriteORM).where(
                GraphCheckpointWriteORM.thread_id == write.thread_id,
                GraphCheckpointWriteORM.checkpoint_ns == write.checkpoint_ns,
                GraphCheckpointWriteORM.checkpoint_id == write.checkpoint_id,
                GraphCheckpointWriteORM.task_id == write.task_id,
                GraphCheckpointWriteORM.write_idx == write.write_idx,
            )
            existing = self._session.scalar(statement)
            if existing is None:
                self._session.add(write)
                continue

            existing.channel = write.channel
            existing.value_type = write.value_type
            existing.value_payload = write.value_payload
            existing.task_path = write.task_path
        self._session.flush()

    def delete_thread(self, thread_id: str) -> None:
        self._session.execute(
            delete(GraphCheckpointWriteORM).where(GraphCheckpointWriteORM.thread_id == thread_id)
        )
        self._session.execute(
            delete(GraphCheckpointBlobORM).where(GraphCheckpointBlobORM.thread_id == thread_id)
        )
        self._session.execute(
            delete(GraphCheckpointORM).where(GraphCheckpointORM.thread_id == thread_id)
        )
        self._session.flush()

    def delete_checkpoints(
        self, keys: Sequence[tuple[str, str, str]]
    ) -> None:
        if not keys:
            return

        self._session.execute(
            delete(GraphCheckpointWriteORM).where(
                tuple_(
                    GraphCheckpointWriteORM.thread_id,
                    GraphCheckpointWriteORM.checkpoint_ns,
                    GraphCheckpointWriteORM.checkpoint_id,
                ).in_(keys)
            )
        )
        self._session.execute(
            delete(GraphCheckpointORM).where(
                tuple_(
                    GraphCheckpointORM.thread_id,
                    GraphCheckpointORM.checkpoint_ns,
                    GraphCheckpointORM.checkpoint_id,
                ).in_(keys)
            )
        )
        self._session.flush()

    def delete_blobs(self, keys: Sequence[tuple[str, str, str, str]]) -> None:
        if not keys:
            return

        self._session.execute(
            delete(GraphCheckpointBlobORM).where(
                tuple_(
                    GraphCheckpointBlobORM.thread_id,
                    GraphCheckpointBlobORM.checkpoint_ns,
                    GraphCheckpointBlobORM.channel,
                    GraphCheckpointBlobORM.version,
                ).in_(keys)
            )
        )
        self._session.flush()


class AsyncCheckpointRepository:
    """Asynchronous repository for persisted graph checkpoints."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_checkpoint(
        self,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str | None = None,
    ) -> GraphCheckpointORM | None:
        statement = select(GraphCheckpointORM).where(
            GraphCheckpointORM.thread_id == thread_id,
            GraphCheckpointORM.checkpoint_ns == checkpoint_ns,
        )
        if checkpoint_id is not None:
            statement = statement.where(GraphCheckpointORM.checkpoint_id == checkpoint_id)
        else:
            statement = statement.order_by(GraphCheckpointORM.checkpoint_id.desc()).limit(1)

        return await self._session.scalar(statement)

    async def list_checkpoints(
        self,
        *,
        thread_ids: Sequence[str] | None = None,
        checkpoint_ns: str | None = None,
    ) -> list[GraphCheckpointORM]:
        statement: Select[tuple[GraphCheckpointORM]] = select(GraphCheckpointORM)
        if thread_ids:
            statement = statement.where(GraphCheckpointORM.thread_id.in_(thread_ids))
        if checkpoint_ns is not None:
            statement = statement.where(GraphCheckpointORM.checkpoint_ns == checkpoint_ns)

        statement = statement.order_by(
            GraphCheckpointORM.thread_id.asc(),
            GraphCheckpointORM.checkpoint_ns.asc(),
            GraphCheckpointORM.checkpoint_id.desc(),
        )
        return (await self._session.scalars(statement)).all()

    async def list_checkpoints_for_run_ids(
        self, run_ids: Sequence[str]
    ) -> list[GraphCheckpointORM]:
        if not run_ids:
            return []

        statement = select(GraphCheckpointORM).where(GraphCheckpointORM.run_id.in_(run_ids))
        return (await self._session.scalars(statement)).all()

    async def list_writes(
        self,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str,
    ) -> list[GraphCheckpointWriteORM]:
        statement = (
            select(GraphCheckpointWriteORM)
            .where(
                GraphCheckpointWriteORM.thread_id == thread_id,
                GraphCheckpointWriteORM.checkpoint_ns == checkpoint_ns,
                GraphCheckpointWriteORM.checkpoint_id == checkpoint_id,
            )
            .order_by(GraphCheckpointWriteORM.id.asc())
        )
        return (await self._session.scalars(statement)).all()

    async def get_existing_write_keys(
        self,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str,
        keys: Sequence[tuple[str, int]],
    ) -> set[tuple[str, int]]:
        if not keys:
            return set()

        statement = select(
            GraphCheckpointWriteORM.task_id,
            GraphCheckpointWriteORM.write_idx,
        ).where(
            GraphCheckpointWriteORM.thread_id == thread_id,
            GraphCheckpointWriteORM.checkpoint_ns == checkpoint_ns,
            GraphCheckpointWriteORM.checkpoint_id == checkpoint_id,
            tuple_(
                GraphCheckpointWriteORM.task_id,
                GraphCheckpointWriteORM.write_idx,
            ).in_(keys),
        )
        return set((await self._session.execute(statement)).all())

    async def list_blobs(
        self,
        thread_id: str,
        checkpoint_ns: str,
        versions: dict[str, str],
    ) -> list[GraphCheckpointBlobORM]:
        if not versions:
            return []

        pairs = [(channel, version) for channel, version in versions.items()]
        statement = select(GraphCheckpointBlobORM).where(
            GraphCheckpointBlobORM.thread_id == thread_id,
            GraphCheckpointBlobORM.checkpoint_ns == checkpoint_ns,
            tuple_(
                GraphCheckpointBlobORM.channel,
                GraphCheckpointBlobORM.version,
            ).in_(pairs),
        )
        return (await self._session.scalars(statement)).all()

    async def list_blobs_for_threads(
        self, thread_ids: Sequence[str]
    ) -> list[GraphCheckpointBlobORM]:
        if not thread_ids:
            return []

        statement = select(GraphCheckpointBlobORM).where(
            GraphCheckpointBlobORM.thread_id.in_(thread_ids)
        )
        return (await self._session.scalars(statement)).all()

    async def save_checkpoint(self, checkpoint: GraphCheckpointORM) -> None:
        await self._session.merge(checkpoint)
        await self._session.flush()

    async def save_blobs(self, blobs: Sequence[GraphCheckpointBlobORM]) -> None:
        for blob in blobs:
            await self._session.merge(blob)
        await self._session.flush()

    async def save_writes(self, writes: Sequence[GraphCheckpointWriteORM]) -> None:
        for write in writes:
            statement = select(GraphCheckpointWriteORM).where(
                GraphCheckpointWriteORM.thread_id == write.thread_id,
                GraphCheckpointWriteORM.checkpoint_ns == write.checkpoint_ns,
                GraphCheckpointWriteORM.checkpoint_id == write.checkpoint_id,
                GraphCheckpointWriteORM.task_id == write.task_id,
                GraphCheckpointWriteORM.write_idx == write.write_idx,
            )
            existing = await self._session.scalar(statement)
            if existing is None:
                self._session.add(write)
                continue

            existing.channel = write.channel
            existing.value_type = write.value_type
            existing.value_payload = write.value_payload
            existing.task_path = write.task_path
        await self._session.flush()

    async def delete_thread(self, thread_id: str) -> None:
        await self._session.execute(
            delete(GraphCheckpointWriteORM).where(GraphCheckpointWriteORM.thread_id == thread_id)
        )
        await self._session.execute(
            delete(GraphCheckpointBlobORM).where(GraphCheckpointBlobORM.thread_id == thread_id)
        )
        await self._session.execute(
            delete(GraphCheckpointORM).where(GraphCheckpointORM.thread_id == thread_id)
        )
        await self._session.flush()

    async def delete_checkpoints(
        self, keys: Sequence[tuple[str, str, str]]
    ) -> None:
        if not keys:
            return

        await self._session.execute(
            delete(GraphCheckpointWriteORM).where(
                tuple_(
                    GraphCheckpointWriteORM.thread_id,
                    GraphCheckpointWriteORM.checkpoint_ns,
                    GraphCheckpointWriteORM.checkpoint_id,
                ).in_(keys)
            )
        )
        await self._session.execute(
            delete(GraphCheckpointORM).where(
                tuple_(
                    GraphCheckpointORM.thread_id,
                    GraphCheckpointORM.checkpoint_ns,
                    GraphCheckpointORM.checkpoint_id,
                ).in_(keys)
            )
        )
        await self._session.flush()

    async def delete_blobs(self, keys: Sequence[tuple[str, str, str, str]]) -> None:
        if not keys:
            return

        await self._session.execute(
            delete(GraphCheckpointBlobORM).where(
                tuple_(
                    GraphCheckpointBlobORM.thread_id,
                    GraphCheckpointBlobORM.checkpoint_ns,
                    GraphCheckpointBlobORM.channel,
                    GraphCheckpointBlobORM.version,
                ).in_(keys)
            )
        )
        await self._session.flush()
