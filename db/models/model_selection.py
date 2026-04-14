from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .model_provider import ModelProviderORM


class ModelSelectionORM(Base):
    """ORM model for configured model selections."""

    __tablename__ = "tb_model_selection"
    __table_args__ = (
        UniqueConstraint(
            "provider_name",
            "model_name",
            name="uq_tb_model_selection_provider_name_model_name",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_name: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("tb_model_provider.name"),
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)

    provider: Mapped[ModelProviderORM] = relationship(
        back_populates="model_selections",
        lazy="joined",
    )
