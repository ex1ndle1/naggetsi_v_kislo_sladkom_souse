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
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
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
        # Имена без префикса ck_ и без имени таблицы: конвенция из NAMING_CONVENTION
        # подставляет их в шаблон "ck_%(table_name)s_%(constraint_name)s", поэтому
        # готовое "ck_..." дало бы двойной префикс и расхождение с миграцией.
        CheckConstraint("allocated >= 0", name="allocated_non_negative"),
        CheckConstraint("assigned >= 0", name="assigned_non_negative"),
        CheckConstraint("assigned <= allocated", name="assigned_within_allocated"),
    )

    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    company: Mapped[Company] = relationship(back_populates="plan_allocations")

    plan: Mapped[UserPlan] = mapped_column(SAEnum(UserPlan, name="user_plan"), nullable=False, index=True)
    allocated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assigned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    @property
    def available(self) -> int:
        return self.allocated - self.assigned

    def __repr__(self) -> str:
        return f"<PlanAllocation plan={self.plan} allocated={self.allocated} assigned={self.assigned}>"


__all__ = ["PlanAllocation"]
