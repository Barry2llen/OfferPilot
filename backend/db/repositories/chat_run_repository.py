from sqlalchemy import delete, func, literal, select, union_all, update

from db.models.chat_run import ChatRunORM
from db.models.graph_checkpoint import GraphCheckpointORM


class ChatRunRepository:
    """Each operation owns a short session; no session survives an await."""

    def __init__(self, database):
        self.sessions = database.get_session_factory()

    @staticmethod
    def _data(row):
        return {
            key: getattr(row, key)
            for key in (
                "sequence",
                "run_id",
                "idempotency_key",
                "fingerprint",
                "thread_id",
                "status",
                "submission",
                "detail",
                "created_at",
            )
        }

    def recover(self):
        with self.sessions.begin() as session:
            session.execute(
                update(ChatRunORM)
                .where(ChatRunORM.status.in_(["running", "waiting_input"]))
                .values(
                    status="interrupted",
                    detail="Backend stopped; execution cannot be resumed.",
                )
            )
            session.execute(
                update(ChatRunORM)
                .where(ChatRunORM.status == "queued")
                .values(status="cancelled", detail="Backend stopped before execution.")
            )

    def create(self, **values):
        with self.sessions.begin() as session:
            row = ChatRunORM(**values)
            session.add(row)
            session.flush()
            return self._data(row)

    def get(self, run_id):
        with self.sessions() as session:
            row = session.scalar(select(ChatRunORM).where(ChatRunORM.run_id == run_id))
            return self._data(row) if row else None

    def by_key(self, key):
        with self.sessions() as session:
            row = session.scalar(
                select(ChatRunORM).where(ChatRunORM.idempotency_key == key)
            )
            return self._data(row) if row else None

    def list(self, thread_id):
        with self.sessions() as session:
            return [
                self._data(row)
                for row in session.scalars(
                    select(ChatRunORM)
                    .where(ChatRunORM.thread_id == thread_id)
                    .order_by(ChatRunORM.sequence)
                )
            ]

    def status(self, run_id, status, detail=None, submission=None):
        with self.sessions.begin() as session:
            session.execute(
                update(ChatRunORM)
                .where(ChatRunORM.run_id == run_id)
                .values(
                    **{
                        "status": status,
                        "detail": detail,
                        **(
                            {"submission": submission} if submission is not None else {}
                        ),
                    }
                )
            )

    def delete_thread(self, thread_id):
        with self.sessions.begin() as session:
            session.execute(delete(ChatRunORM).where(ChatRunORM.thread_id == thread_id))

    def unstarted_threads(self):
        with self.sessions() as session:
            checkpoint_exists = (
                select(GraphCheckpointORM.thread_id)
                .where(
                    GraphCheckpointORM.thread_id == ChatRunORM.thread_id,
                    GraphCheckpointORM.checkpoint_ns == "",
                )
                .exists()
            )
            return list(
                session.scalars(
                    select(ChatRunORM.thread_id).distinct().where(~checkpoint_exists)
                )
            )

    def conversation_page(self, limit: int, offset: int):
        latest = (
            select(
                GraphCheckpointORM.thread_id.label("thread_id"),
                func.max(GraphCheckpointORM.checkpoint_id).label("checkpoint_id"),
            )
            .where(GraphCheckpointORM.checkpoint_ns == "")
            .group_by(GraphCheckpointORM.thread_id)
            .subquery()
        )
        checkpoints = (
            select(
                GraphCheckpointORM.thread_id.label("thread_id"),
                GraphCheckpointORM.created_at.label("updated_at"),
                literal(True).label("has_checkpoint"),
                GraphCheckpointORM.checkpoint_id.label("sort_id"),
            )
            .join(
                latest,
                (GraphCheckpointORM.thread_id == latest.c.thread_id)
                & (GraphCheckpointORM.checkpoint_id == latest.c.checkpoint_id),
            )
            .where(GraphCheckpointORM.checkpoint_ns == "")
        )
        unstarted = (
            select(
                ChatRunORM.thread_id.label("thread_id"),
                func.max(ChatRunORM.created_at).label("updated_at"),
                literal(False).label("has_checkpoint"),
                literal("").label("sort_id"),
            )
            .where(
                ~select(latest.c.thread_id)
                .where(latest.c.thread_id == ChatRunORM.thread_id)
                .exists()
            )
            .group_by(ChatRunORM.thread_id)
        )
        combined = union_all(checkpoints, unstarted).subquery()
        with self.sessions() as session:
            return list(
                session.execute(
                    select(combined)
                    .order_by(
                        combined.c.updated_at.desc(),
                        combined.c.sort_id.desc(),
                        combined.c.thread_id.asc(),
                    )
                    .offset(offset)
                    .limit(limit)
                ).mappings()
            )

    def unstarted_rows(self):
        with self.sessions() as session:
            checkpoint_exists = (
                select(GraphCheckpointORM.thread_id)
                .where(
                    GraphCheckpointORM.thread_id == ChatRunORM.thread_id,
                    GraphCheckpointORM.checkpoint_ns == "",
                )
                .exists()
            )
            return [
                self._data(row)
                for row in session.scalars(
                    select(ChatRunORM)
                    .where(~checkpoint_exists)
                    .order_by(ChatRunORM.sequence)
                )
            ]
