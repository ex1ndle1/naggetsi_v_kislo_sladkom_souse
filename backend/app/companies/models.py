"""Модель Company — корпоративный клиент платформы (NEXUS30 §1, §2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.enums import CompanyStatus

if TYPE_CHECKING:
    from app.invites.models import InviteToken
    from app.plans.models import PlanAllocation
    from app.users.models import User


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    status: Mapped[CompanyStatus] = mapped_column(
        SAEnum(CompanyStatus, name="company_status"),
        nullable=False,
        default=CompanyStatus.ACTIVE,
    )

    users: Mapped[list[User]] = relationship(back_populates="company")
    plan_allocations: Mapped[list[PlanAllocation]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    invite_tokens: Mapped[list[InviteToken]] = relationship(back_populates="company", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Company {self.name!r} status={self.status}>"


__all__ = ["Company"]
