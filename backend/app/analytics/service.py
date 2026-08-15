"""Агрегаты для дашбордов и AI-отчётов (NEXUS30 §37, §38, §19).

Один и тот же расчёт обслуживает HTTP-эндпоинты и вход AI-сценария 3: если бы
отчёт считался отдельно, цифры в UI и в тексте модели расходились бы.

Все запросы ограничены арендатором: company_id и merchant_id приходят из JWT,
никогда из тела запроса.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.benefits.models import Benefit
from app.core.enums import PromoCodeStatus, UserPlan, UserRole
from app.merchants.models import Merchant
from app.plans.models import PlanAllocation
from app.promo_codes.models import PromoCode
from app.redemptions.models import BenefitRedemption
from app.users.models import User

__all__ = [
    "CompanyAnalytics",
    "MerchantAnalytics",
    "PlanUsage",
    "company_analytics",
    "merchant_analytics",
]


@dataclass(frozen=True)
class PlanUsage:
    """Занятость мест по одному тарифу."""

    plan: UserPlan
    allocated: int
    assigned: int

    @property
    def available(self) -> int:
        return self.allocated - self.assigned

    @property
    def utilization_percent(self) -> float:
        if self.allocated == 0:
            return 0.0
        return round(self.assigned / self.allocated * 100, 1)


@dataclass(frozen=True)
class CompanyAnalytics:
    """Сводка по компании: места, сотрудники, активность по льготам."""

    company_id: UUID
    seats: list[PlanUsage]
    active_employees: int
    promo_codes_issued: int
    promo_codes_redeemed: int
    redemptions_total: int
    top_categories: list[dict[str, Any]] = field(default_factory=list)
    top_merchants: list[dict[str, Any]] = field(default_factory=list)
    top_benefits: list[dict[str, Any]] = field(default_factory=list)

    @property
    def redemption_rate_percent(self) -> float:
        """Доля выданных кодов, доведённых до использования у мерчанта."""
        if self.promo_codes_issued == 0:
            return 0.0
        return round(self.promo_codes_redeemed / self.promo_codes_issued * 100, 1)

    @property
    def seats_allocated(self) -> int:
        return sum(usage.allocated for usage in self.seats)

    @property
    def seats_assigned(self) -> int:
        return sum(usage.assigned for usage in self.seats)

    def to_prompt_payload(self) -> dict[str, Any]:
        """Плоский словарь для передачи в LLM.

        Только агрегаты: ни email'ов, ни имён, ни промокодов — модель не должна
        получать персональные данные (NEXUS30 §20).
        """
        return {
            "seats": [
                {
                    "plan": usage.plan.value,
                    "allocated": usage.allocated,
                    "assigned": usage.assigned,
                    "available": usage.available,
                    "utilization_percent": usage.utilization_percent,
                }
                for usage in self.seats
            ],
            "seats_allocated": self.seats_allocated,
            "seats_assigned": self.seats_assigned,
            "active_employees": self.active_employees,
            "promo_codes_issued": self.promo_codes_issued,
            "promo_codes_redeemed": self.promo_codes_redeemed,
            "redemption_rate_percent": self.redemption_rate_percent,
            "top_categories": self.top_categories,
            "top_merchants": self.top_merchants,
            "top_benefits": self.top_benefits,
        }


@dataclass(frozen=True)
class MerchantAnalytics:
    """Сводка по мерчанту: сколько кодов выдано и сколько реально использовано."""

    merchant_id: UUID
    benefits_total: int
    benefits_active: int
    promo_codes_issued: int
    promo_codes_redeemed: int
    promo_codes_expired: int
    promo_codes_revoked: int = 0
    top_benefits: list[dict[str, Any]] = field(default_factory=list)
    redemption_trend: list[dict[str, Any]] = field(default_factory=list)

    @property
    def redemption_rate_percent(self) -> float:
        if self.promo_codes_issued == 0:
            return 0.0
        return round(self.promo_codes_redeemed / self.promo_codes_issued * 100, 1)

    @property
    def benefits_inactive(self) -> int:
        return self.benefits_total - self.benefits_active

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["merchant_id"] = str(self.merchant_id)
        payload["redemption_rate_percent"] = self.redemption_rate_percent
        payload["benefits_inactive"] = self.benefits_inactive
        return payload


async def company_analytics(db: AsyncSession, company_id: UUID) -> CompanyAnalytics:
    """Считает сводку компании одним набором агрегатов.

    Промокоды считаются через join на redemption, а не по employee_id: сотрудник
    может быть удалён, а история использования у мерчанта останется.
    """
    seat_rows = (
        await db.execute(
            select(PlanAllocation.plan, PlanAllocation.allocated, PlanAllocation.assigned)
            .where(PlanAllocation.company_id == company_id)
            .order_by(PlanAllocation.plan)
        )
    ).all()
    seats = [PlanUsage(plan=row[0], allocated=row[1], assigned=row[2]) for row in seat_rows]

    active_employees = (
        await db.scalar(
            select(func.count(User.id)).where(
                User.company_id == company_id,
                User.role == UserRole.EMPLOYEE,
                User.is_active.is_(True),
            )
        )
    ) or 0

    promo_status_rows = (
        await db.execute(
            select(PromoCode.status, func.count(PromoCode.id))
            .join(BenefitRedemption, BenefitRedemption.id == PromoCode.redemption_id)
            .where(BenefitRedemption.company_id == company_id)
            .group_by(PromoCode.status)
        )
    ).all()
    promo_by_status = {row[0]: row[1] for row in promo_status_rows}
    promo_issued = sum(promo_by_status.values())
    promo_redeemed = promo_by_status.get(PromoCodeStatus.REDEEMED, 0)

    redemptions_total = (
        await db.scalar(select(func.count(BenefitRedemption.id)).where(BenefitRedemption.company_id == company_id))
    ) or 0

    category_rows = (
        await db.execute(
            select(Benefit.category, func.count(BenefitRedemption.id).label("count"))
            .join(BenefitRedemption, BenefitRedemption.benefit_id == Benefit.id)
            .where(BenefitRedemption.company_id == company_id)
            .group_by(Benefit.category)
            .order_by(func.count(BenefitRedemption.id).desc())
            .limit(5)
        )
    ).all()

    merchant_rows = (
        await db.execute(
            select(Merchant.name, func.count(BenefitRedemption.id).label("count"))
            .join(Benefit, Benefit.merchant_id == Merchant.id)
            .join(BenefitRedemption, BenefitRedemption.benefit_id == Benefit.id)
            .where(BenefitRedemption.company_id == company_id)
            .group_by(Merchant.name)
            .order_by(func.count(BenefitRedemption.id).desc())
            .limit(5)
        )
    ).all()

    benefit_rows = (
        await db.execute(
            select(Benefit.title, func.count(BenefitRedemption.id).label("count"))
            .join(BenefitRedemption, BenefitRedemption.benefit_id == Benefit.id)
            .where(BenefitRedemption.company_id == company_id)
            .group_by(Benefit.title)
            .order_by(func.count(BenefitRedemption.id).desc())
            .limit(5)
        )
    ).all()

    return CompanyAnalytics(
        company_id=company_id,
        seats=seats,
        active_employees=active_employees,
        promo_codes_issued=promo_issued,
        promo_codes_redeemed=promo_redeemed,
        redemptions_total=redemptions_total,
        top_categories=[{"category": row[0].value, "redemptions": row[1]} for row in category_rows],
        top_merchants=[{"merchant": row[0], "redemptions": row[1]} for row in merchant_rows],
        top_benefits=[{"benefit": row[0], "redemptions": row[1]} for row in benefit_rows],
    )


async def merchant_analytics(db: AsyncSession, merchant_id: UUID) -> MerchantAnalytics:
    """Считает сводку мерчанта по его собственным льготам."""
    benefits_total = (await db.scalar(select(func.count(Benefit.id)).where(Benefit.merchant_id == merchant_id))) or 0
    benefits_active = (
        await db.scalar(
            select(func.count(Benefit.id)).where(Benefit.merchant_id == merchant_id, Benefit.is_active.is_(True))
        )
    ) or 0

    promo_status_rows = (
        await db.execute(
            select(PromoCode.status, func.count(PromoCode.id))
            .join(Benefit, Benefit.id == PromoCode.benefit_id)
            .where(Benefit.merchant_id == merchant_id)
            .group_by(PromoCode.status)
        )
    ).all()
    promo_by_status = {row[0]: row[1] for row in promo_status_rows}

    benefit_rows = (
        await db.execute(
            select(
                Benefit.title,
                func.count(BenefitRedemption.id).label("issued"),
                func.count(BenefitRedemption.redeemed_at).label("redeemed"),
            )
            .join(BenefitRedemption, BenefitRedemption.benefit_id == Benefit.id)
            .where(Benefit.merchant_id == merchant_id)
            .group_by(Benefit.title)
            .order_by(func.count(BenefitRedemption.id).desc())
            .limit(10)
        )
    ).all()

    # Динамика за 30 дней: считаем по redeemed_at, а не по created_at — интересен
    # момент, когда код реально погасили у мерчанта, а не когда его выдали.
    since = datetime.now(UTC) - timedelta(days=30)
    trend_rows = (
        await db.execute(
            select(
                cast(BenefitRedemption.redeemed_at, Date).label("day"),
                func.count(BenefitRedemption.id).label("count"),
            )
            .join(Benefit, Benefit.id == BenefitRedemption.benefit_id)
            .where(
                Benefit.merchant_id == merchant_id,
                BenefitRedemption.redeemed_at.is_not(None),
                BenefitRedemption.redeemed_at >= since,
            )
            .group_by(cast(BenefitRedemption.redeemed_at, Date))
            .order_by(cast(BenefitRedemption.redeemed_at, Date))
        )
    ).all()

    return MerchantAnalytics(
        merchant_id=merchant_id,
        benefits_total=benefits_total,
        benefits_active=benefits_active,
        promo_codes_issued=sum(promo_by_status.values()),
        promo_codes_redeemed=promo_by_status.get(PromoCodeStatus.REDEEMED, 0),
        promo_codes_expired=promo_by_status.get(PromoCodeStatus.EXPIRED, 0),
        promo_codes_revoked=promo_by_status.get(PromoCodeStatus.REVOKED, 0),
        top_benefits=[{"benefit": row[0], "issued": row[1], "redeemed": row[2]} for row in benefit_rows],
        redemption_trend=[{"day": row[0].isoformat(), "count": row[1]} for row in trend_rows],
    )
