"""Модель User — все пользователи платформы (ТЗ §15).

company_id nullable: у MERCHANT и PLATFORM_ADMIN компании нет.
merchant_id nullable: связывает MERCHANT-пользователя с мерчантом.
password_hash через argon2-cffi (не passlib), is_active для блокировок.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.enums import UserPlan, UserRole

if TYPE_CHECKING:
    from app.companies.models import Company
    from app.merchants.models import Merchant


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole, name="user_role"), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    # NEXUS30: план доступа (STANDARD/PLUS/PRO). NULL только для MERCHANT/PLATFORM_ADMIN.
    plan: Mapped[UserPlan | None] = mapped_column(SAEnum(UserPlan, name="user_plan"), nullable=True, index=True)

    # EMPLOYEE / COMPANY_ADMIN → company_id заполнено, иначе NULL.
    company_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    company: Mapped[Company | None] = relationship(back_populates="users")

    # MERCHANT → merchant_id заполнено, иначе NULL.
    merchant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("merchants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    merchant: Mapped[Merchant | None] = relationship(back_populates="users")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def __repr__(self) -> str:
        return f"<User {self.email!r} role={self.role} active={self.is_active}>"


__all__ = ["User"]
