from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ResumeExtractionORM(Base):
    """ORM model for persisted resume extraction results."""

    __tablename__ = "tb_resume_extraction"

    resume_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tb_resume.id", ondelete="CASCADE"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unparsed")
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    sections: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_selection_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("tb_model_selection.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
