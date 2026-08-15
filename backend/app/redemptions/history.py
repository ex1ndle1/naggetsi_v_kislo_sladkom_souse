"""История сотрудника: выданные промокоды и факты получения льгот (NEXUS30 §35).

Выборка всегда ограничена ``employee_id`` из JWT: сотрудник не может запросить
чужую историю, потому что идентификатор владельца в запрос не принимается.

Скидка берётся из ``BenefitPlanOffer`` по тарифу самого сотрудника, а не из
момента выдачи: льгота могла сменить условия, и показывать нужно то, что мерчант
примет сейчас.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.benefits.models import Benefit
from app.benefits.plan_offers import BenefitPlanOffer
from app.core.enums import PromoCodeStatus, UserPlan
from app.promo_codes.models import PromoCode
from app.redemptions.models import BenefitRedemption
from app.redemptions.schemas import MyPromoCodeItem, MyRedemptionItem

__all__ = ["list_my_promo_codes", "list_my_redemptions"]


async def _discounts_for(db: AsyncSession, benefit_ids: set[UUID], plan: UserPlan) -> dict[UUID, Decimal]:
    """Скидки по тарифу сотрудника одним запросом — вместо запроса на строку."""
    if not benefit_ids:
        return {}

    rows = await db.execute(
        select(BenefitPlanOffer.benefit_id, BenefitPlanOffer.discount_percent).where(
            BenefitPlanOffer.benefit_id.in_(benefit_ids),
            BenefitPlanOffer.plan == plan,
        )
    )
    return {benefit_id: percent for benefit_id, percent in rows.all()}


async def list_my_promo_codes(
    db: AsyncSession,
    *,
    employee_id: UUID,
    plan: UserPlan,
    status: PromoCodeStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[MyPromoCodeItem], int]:
    """Промокоды сотрудника, новые первыми.

    Returns:
        (страница, всего).
    """
    conditions = [PromoCode.employee_id == employee_id]
    if status is not None:
        conditions.append(PromoCode.status == status)

    total = await db.scalar(select(func.count()).select_from(PromoCode).where(*conditions))

    stmt = (
        select(PromoCode)
        .where(*conditions)
        .options(selectinload(PromoCode.benefit).selectinload(Benefit.merchant))
        .order_by(PromoCode.issued_at.desc())
        .limit(limit)
        .offset(offset)
    )
    codes = list((await db.scalars(stmt)).all())
    discounts = await _discounts_for(db, {code.benefit_id for code in codes}, plan)

    items = [
        MyPromoCodeItem(
            id=code.id,
            code=code.code,
            status=code.status,
            issued_at=code.issued_at,
            expires_at=code.expires_at,
            redeemed_at=code.redeemed_at,
            benefit_id=code.benefit_id,
            benefit_title=code.benefit.title,
            merchant_name=code.benefit.merchant.name,
            destination_url=code.benefit.destination_url,
            discount_percent=discounts.get(code.benefit_id),
        )
        for code in codes
    ]
    return items, total or 0


async def list_my_redemptions(
    db: AsyncSession,
    *,
    employee_id: UUID,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[MyRedemptionItem], int]:
    """Факты получения льгот сотрудником, новые первыми.

    Returns:
        (страница, всего).
    """
    total = await db.scalar(
        select(func.count()).select_from(BenefitRedemption).where(BenefitRedemption.employee_id == employee_id)
    )

    stmt = (
        select(BenefitRedemption)
        .where(BenefitRedemption.employee_id == employee_id)
        .options(
            selectinload(BenefitRedemption.benefit).selectinload(Benefit.merchant),
            selectinload(BenefitRedemption.promo_code),
        )
        .order_by(BenefitRedemption.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    redemptions = list((await db.scalars(stmt)).all())

    items = [
        MyRedemptionItem(
            id=redemption.id,
            status=redemption.status,
            created_at=redemption.created_at,
            redeemed_at=redemption.redeemed_at,
            benefit_id=redemption.benefit_id,
            benefit_title=redemption.benefit.title,
            benefit_category=redemption.benefit.category,
            merchant_name=redemption.benefit.merchant.name,
            promo_code=redemption.promo_code.code if redemption.promo_code else None,
            promo_status=redemption.promo_code.status if redemption.promo_code else None,
            promo_expires_at=(redemption.promo_code.expires_at if redemption.promo_code else None),
        )
        for redemption in redemptions
    ]
    return items, total or 0
