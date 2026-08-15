"""План-специфичные условия льготы (NEXUS30 §7).

Одна льгота может иметь разные условия для разных планов:
  Fitness Club: STANDARD=5%, PLUS=15%, PRO=45%

Если строка BenefitPlanOffer не существует → льгота недоступна этому плану.
Backend ОБЯЗАН фильтровать benefits по плану пользователя (NEXUS30 §8).
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.enums import UserPlan

if TYPE_CHECKING:
    from app.benefits.models import Benefit


class BenefitPlanOffer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "benefit_plan_offers"
    __table_args__ = (
        UniqueConstraint("benefit_id", "plan", name="uq_benefit_plan_offer"),
        # Без префикса ck_: его добавит NAMING_CONVENTION вместе с именем таблицы.
        CheckConstraint(
            "discount_percent >= 0 AND discount_percent <= 100",
            name="discount_percent_range",
        ),
    )

    benefit_id: Mapped[UUID] = mapped_column(ForeignKey("benefits.id", ondelete="CASCADE"), nullable=False, index=True)
    benefit: Mapped[Benefit] = relationship(back_populates="plan_offers")

    plan: Mapped[UserPlan] = mapped_column(SAEnum(UserPlan, name="user_plan"), nullable=False, index=True)
    discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, comment="Процент скидки: 0.00-100.00"
    )
    is_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="Можно временно отключить оффер для плана"
    )

    def __repr__(self) -> str:
        return f"<BenefitPlanOffer plan={self.plan} discount={self.discount_percent}%>"


__all__ = ["BenefitPlanOffer"]
