"""Модель Merchant — партнёр/поставщик услуги (ТЗ §15)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.enums import MerchantStatus

if TYPE_CHECKING:
    from app.benefits.models import Benefit
    from app.users.models import User


class Merchant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "merchants"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    status: Mapped[MerchantStatus] = mapped_column(
        SAEnum(MerchantStatus, name="merchant_status"),
        nullable=False,
        default=MerchantStatus.ACTIVE,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    users: Mapped[list[User]] = relationship(back_populates="merchant")
    benefits: Mapped[list[Benefit]] = relationship(back_populates="merchant")

    @property
    def is_active(self) -> bool:
        return self.status == MerchantStatus.ACTIVE

    def __repr__(self) -> str:
        return f"<Merchant {self.name!r} status={self.status}>"


__all__ = ["Merchant"]
