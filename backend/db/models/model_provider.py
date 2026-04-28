from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ModelProviderORM(Base):
    """ORM model for configured chat model providers."""

    __tablename__ = "tb_model_provider"
    __table_args__ = (
        CheckConstraint(
            "provider IN ('openai', 'anthropic', 'google', 'deepseek', 'openai compatible')",
            name="ck_tb_model_provider_provider",
        ),
    )

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_selections: Mapped[list["ModelSelectionORM"]] = relationship(
        back_populates="provider",
        passive_deletes=True,
    )
