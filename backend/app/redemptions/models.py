"""BenefitRedemption — активация льготы сотрудником (NEXUS30 §13).

Это НЕ заявка на покупку. Это факт получения promo code и его последующего
использования у merchant.

Lifecycle:
  ISSUED   — promo code выдан, сотрудник видит его
  REDEEMED — merchant/admin подтвердил использование кода
  EXPIRED  — истёк срок действия кода
  CANCELLED — отменено админом

Замена legacy Application из первоначального ТЗ.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.enums import RedemptionStatus

if TYPE_CHECKING:
    from app.benefits.models import Benefit
    from app.companies.models import Company
    from app.promo_codes.models import PromoCode
    from app.users.models import User


class BenefitRedemption(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "benefit_redemptions"

    employee_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee: Mapped[User] = relationship(foreign_keys=[employee_id])

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company: Mapped[Company] = relationship()

    benefit_id: Mapped[UUID] = mapped_column(
        ForeignKey("benefits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    benefit: Mapped[Benefit] = relationship(back_populates="redemptions")

    promo_code: Mapped[PromoCode | None] = relationship(
        back_populates="redemption", uselist=False
    )

    status: Mapped[RedemptionStatus] = mapped_column(
        SAEnum(RedemptionStatus, name="redemption_status"),
        nullable=False,
        default=RedemptionStatus.ISSUED,
        index=True,
    )
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<BenefitRedemption employee={self.employee_id} "
            f"benefit={self.benefit_id} status={self.status}>"
        )


__all__ = ["BenefitRedemption"]
