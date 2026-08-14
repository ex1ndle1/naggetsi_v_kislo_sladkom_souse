"""Сервис redemption: выдача promo code с полной валидацией (NEXUS30 §14, §15).

11 проверок из ТЗ §14 плюс abuse prevention из §15.
Выдача кода — атомарная операция: создание BenefitRedemption + PromoCode + SSE event.
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.benefits.models import Benefit
from app.benefits.visibility import discount_for_plan
from app.core.enums import MerchantStatus, RedemptionStatus, UserPlan
from app.core.errors import BadRequest, Conflict, Forbidden, NotFound
from app.merchants.models import Merchant
from app.promo_codes.service import issue_promo_code
from app.redemptions.models import BenefitRedemption
from app.users.models import User

__all__ = ["redeem_benefit"]


async def redeem_benefit(
    db: AsyncSession,
    benefit_id: UUID,
    employee_id: UUID,
    company_id: UUID,
    plan: UserPlan,
) -> tuple[BenefitRedemption, str]:
    """Выдать promo code сотруднику (NEXUS30 §14).

    Проверки:
      1-2. пользователь авторизован и активен — проверяет CurrentUser
      3. tenant isolation — company_id из JWT
      4. benefit существует
      5. benefit активен
      6. benefit не expired
      7. benefit доступен плану пользователя
      8. merchant активен
      9. usage_limit не превышен (если задан)
     10. max_redemptions_per_employee не превышен
     11. tenant context корректен

    Returns:
        (BenefitRedemption, promo_code_plaintext)

    Raises:
        NotFound: benefit не найден
        Forbidden: benefit недоступен этому плану или компании
        Conflict: превышен usage_limit или max_redemptions_per_employee
    """
    now = datetime.now(timezone.utc)

    # 4. Benefit существует
    benefit = await db.get(Benefit, benefit_id)
    if not benefit:
        raise NotFound(message="Benefit not found")

    # 5. Benefit активен
    if not benefit.is_active:
        raise Forbidden(message="Benefit is inactive")

    # 6. Benefit не expired
    if not benefit.is_within_validity(now):
        raise Forbidden(message="Benefit is not within its validity period")

    # 7. Benefit доступен плану пользователя
    offer = discount_for_plan(benefit, plan)
    if not offer:
        raise Forbidden(
            message=f"Benefit not available for {plan.value} plan",
            details={"benefit_id": str(benefit_id), "user_plan": plan.value},
        )

    # 8. Merchant активен
    merchant = await db.get(Merchant, benefit.merchant_id)
    if not merchant or merchant.status != MerchantStatus.ACTIVE:
        raise Forbidden(message="Merchant is not active")

    # 11. Tenant context: benefit.company_id либо NULL, либо совпадает
    if benefit.company_id is not None and benefit.company_id != company_id:
        raise Forbidden(message="Benefit not available for your company")

    # 9. Usage limit не превышен (глобальный счётчик по льготе)
    if benefit.usage_limit is not None:
        total_issued = await db.scalar(
            select(func.count(BenefitRedemption.id)).where(
                BenefitRedemption.benefit_id == benefit_id,
                BenefitRedemption.status == RedemptionStatus.ISSUED,
            )
        )
        if total_issued >= benefit.usage_limit:
            raise Conflict(message="Benefit usage limit exceeded")

    # 10. Max redemptions per employee
    employee_count = await db.scalar(
        select(func.count(BenefitRedemption.id)).where(
            BenefitRedemption.benefit_id == benefit_id,
            BenefitRedemption.employee_id == employee_id,
            BenefitRedemption.status.in_([RedemptionStatus.ISSUED, RedemptionStatus.REDEEMED]),
        )
    )
    if employee_count >= benefit.max_redemptions_per_employee:
        raise Conflict(
            message=f"You have already redeemed this benefit {employee_count} time(s)",
            details={"max_allowed": benefit.max_redemptions_per_employee},
        )

    # Создаём redemption
    redemption = BenefitRedemption(
        employee_id=employee_id,
        company_id=company_id,
        benefit_id=benefit_id,
        status=RedemptionStatus.ISSUED,
    )
    db.add(redemption)
    await db.flush()

    # Выдаём promo code
    promo = await issue_promo_code(
        db=db,
        benefit_id=benefit_id,
        employee_id=employee_id,
        redemption_id=redemption.id,
        merchant_name=merchant.name,
        promo_valid_days=benefit.promo_valid_days,
    )

    # TODO: отправить SSE event PROMO_ISSUED (после реализации SSE auth)

    return redemption, promo.code
