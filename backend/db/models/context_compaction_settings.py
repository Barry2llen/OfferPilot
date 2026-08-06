from sqlalchemy import CheckConstraint, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .model_selection import ModelSelectionORM


class ContextCompactionSettingsORM(Base):
    """Global singleton setting for the optional auto-compaction model."""

    __tablename__ = "tb_context_compaction_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_tb_context_compaction_settings_singleton"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    model_selection_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("tb_model_selection.id", ondelete="SET NULL"),
        nullable=True,
    )

    model_selection: Mapped[ModelSelectionORM | None] = relationship(
        lazy="joined",
    )
