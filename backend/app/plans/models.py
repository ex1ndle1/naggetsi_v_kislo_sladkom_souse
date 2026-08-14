"""Seat allocation — сколько мест каждого тарифа компания приобрела (NEXUS30 §2, §4).

allocated — куплено по B2B-контракту.
assigned  — уже выдано сотрудникам; поддерживается транзакционно при назначении плана.
available — вычисляемое, никогда не хранится.

Уникальность (company_id, plan): у компании ровно одна строка на каждый тариф.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.enums import UserPlan

if TYPE_CHECKING:
    from app.companies.models import Company


class PlanAllocation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "plan_allocations"
    __table_args__ = (
        UniqueConstraint("company_id", "plan", name="uq_plan_allocation_company_plan"),
        CheckConstraint("allocated >= 0", name="ck_plan_allocation_allocated_non_negative"),
        CheckConstraint("assigned >= 0", name="ck_plan_allocation_assigned_non_negative"),
        CheckConstraint("assigned <= allocated", name="ck_plan_allocation_assigned_within_allocated"),
    )

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company: Mapped[Company] = relationship(back_populates="plan_allocations")

    plan: Mapped[UserPlan] = mapped_column(
        SAEnum(UserPlan, name="user_plan"), nullable=False, index=True
    )
    allocated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assigned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    @property
    def available(self) -> int:
        return self.allocated - self.assigned

    def __repr__(self) -> str:
        return (
            f"<PlanAllocation plan={self.plan} "
            f"allocated={self.allocated} assigned={self.assigned}>"
        )


__all__ = ["PlanAllocation"]
