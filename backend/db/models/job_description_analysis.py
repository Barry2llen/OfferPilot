from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class JobDescriptionAnalysisORM(Base):
    """ORM model for persisted JD analysis results."""

    __tablename__ = "tb_job_description_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="processing"
    )
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_image_file_ids: Mapped[Any] = mapped_column(
        JSON, default=list, nullable=False
    )
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[Any] = mapped_column(JSON, default=dict, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_selection_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("tb_model_selection.id", ondelete="SET NULL"),
        nullable=True,
    )
    job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    primary_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    block_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fact_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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
