"""Модель Benefit — льгота/предложение (NEXUS30 §7, §9).

ИЗМЕНЕНО: убрана цена (price/discount_price/currency) — теперь только процент скидки
в BenefitPlanOffer. Merchant указывает, на сколько процентов сотрудник получает скидку,
а точную сумму считает сам merchant при использовании promo code.

company_id nullable: NULL = платформенное предложение, доступно всем компаниям.
usage_limit: ограничение общего количества использований льготы (не per-employee).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.enums import BenefitCategory

if TYPE_CHECKING:
    from app.benefits.plan_offers import BenefitPlanOffer
    from app.companies.models import Company
    from app.merchants.models import Merchant
    from app.promo_codes.models import PromoCode
    from app.redemptions.models import BenefitRedemption


class Benefit(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "benefits"

    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[BenefitCategory] = mapped_column(
        SAEnum(BenefitCategory, name="benefit_category"), nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    # Куда идёт сотрудник использовать promo code (NEXUS30 §29, §30).
    destination_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Период действия льготы (NEXUS30 §7).
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Общий лимит выдач по льготе; NULL = без ограничения.
    usage_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Сколько кодов может получить один сотрудник (NEXUS30 §15 duplicate redemption).
    max_redemptions_per_employee: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="1 = одноразовая льгота"
    )
    # Срок жизни выданного promo code в днях (NEXUS30 §29: Expires: 30 days).
    promo_valid_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)

    merchant_id: Mapped[UUID] = mapped_column(
        ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    merchant: Mapped[Merchant] = relationship(back_populates="benefits")

    # NULL = платформенное предложение, доступно всем. Иначе — корпоративная льгота.
    company_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    company: Mapped[Company | None] = relationship()

    plan_offers: Mapped[list[BenefitPlanOffer]] = relationship(
        back_populates="benefit", cascade="all, delete-orphan", lazy="selectin"
    )
    promo_codes: Mapped[list[PromoCode]] = relationship(back_populates="benefit")
    redemptions: Mapped[list[BenefitRedemption]] = relationship(back_populates="benefit")

    def is_within_validity(self, now: datetime) -> bool:
        """Проверка периода действия льготы (NEXUS30 §14.6)."""
        if self.valid_from is not None and now < self.valid_from:
            return False
        return not (self.valid_until is not None and now >= self.valid_until)

    def __repr__(self) -> str:
        return f"<Benefit {self.title!r} cat={self.category} active={self.is_active}>"


__all__ = ["Benefit"]
