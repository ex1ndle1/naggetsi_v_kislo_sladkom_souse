"""Промокод — центральная механика получения льготы (NEXUS30 §11, §12).

Employee не оплачивает льготу внутри приложения.
Employee получает promo code, идёт на сайт merchant и использует его там.

Код: cryptographically secure, префикс категории/merchant + random groups.
Пример: FIT-8XK29-QJ4M7

Статусы:
  ISSUED   — выдан сотруднику, ожидает использования
  REDEEMED — использован у мерчанта (merchant validates в dashboard, §41)
  EXPIRED  — истёк срок действия
  REVOKED  — отозван админом
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.enums import PromoCodeStatus

if TYPE_CHECKING:
    from app.benefits.models import Benefit
    from app.redemptions.models import BenefitRedemption
    from app.users.models import User


class PromoCode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "promo_codes"

    code: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True, comment="FIT-8XK29-QJ4M7"
    )

    benefit_id: Mapped[UUID] = mapped_column(
        ForeignKey("benefits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    benefit: Mapped[Benefit] = relationship(back_populates="promo_codes")

    employee_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee: Mapped[User] = relationship(foreign_keys=[employee_id])

    redemption_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("benefit_redemptions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    redemption: Mapped[BenefitRedemption | None] = relationship(back_populates="promo_code")

    status: Mapped[PromoCodeStatus] = mapped_column(
        SAEnum(PromoCodeStatus, name="promo_code_status"),
        nullable=False,
        default=PromoCodeStatus.ISSUED,
        index=True,
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Кто подтвердил использование (merchant или admin).
    redeemed_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    redeemed_by: Mapped[User | None] = relationship(foreign_keys=[redeemed_by_id])

    def is_expired(self, now: datetime) -> bool:
        return self.expires_at <= now

    def can_be_redeemed(self, now: datetime) -> bool:
        return self.status == PromoCodeStatus.ISSUED and not self.is_expired(now)

    def __repr__(self) -> str:
        return f"<PromoCode {self.code!r} status={self.status}>"


__all__ = ["PromoCode"]
