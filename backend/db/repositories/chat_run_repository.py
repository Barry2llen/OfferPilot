from sqlalchemy import delete, select, update

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

    def status(self, run_id, status, detail=None):
        with self.sessions.begin() as session:
            session.execute(
                update(ChatRunORM)
                .where(ChatRunORM.run_id == run_id)
                .values(status=status, detail=detail)
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
