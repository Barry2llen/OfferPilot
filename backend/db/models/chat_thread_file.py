from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ChatThreadFileORM(Base):
    """ORM model for chat thread to file associations."""

    __tablename__ = "tb_chat_thread_file"

    thread_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    file_id: Mapped[str] = mapped_column(
        String(6),
        ForeignKey("tb_chat_file.id", ondelete="CASCADE"),
        primary_key=True,
    )
    injection_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        nullable=False,
    )
