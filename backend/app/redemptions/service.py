"""Выдача промокода с полной проверкой права на льготу (NEXUS30 §14, §15).

Одна точка входа для всех проверок §14. Разнести их по роутерам нельзя: любой
пропущенный вызов означал бы выдачу кода в обход лимита или тарифа.

Транзакцию открывает и коммитит вызывающий роутер — здесь только флашится, чтобы
запись льготы, промокод и журнал попали в БД одним куском либо не попали вовсе.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit.service import record_audit
from app.benefits.models import Benefit
from app.benefits.visibility import discount_for_plan
from app.core.enums import AuditAction, MerchantStatus, RedemptionStatus, UserPlan
from app.core.errors import Conflict, Forbidden, NotFound
from app.promo_codes.models import PromoCode
from app.promo_codes.service import issue_promo_code
from app.redemptions.models import BenefitRedemption

__all__ = ["redeem_benefit"]

# Статусы, которые занимают место в лимитах. CANCELLED и EXPIRED не занимают:
# сотрудник, чей код истёк, должен иметь возможность получить новый.
_COUNTED_STATUSES = (RedemptionStatus.ISSUED, RedemptionStatus.REDEEMED)


async def _reject(
    db: AsyncSession,
    *,
    employee_id: UUID,
    company_id: UUID,
    benefit_id: UUID,
    reason: str,
) -> None:
    """Записать отказ в журнал.

    Отказы фиксируются наравне с успехами: без них не видно попыток обойти лимиты
    (NEXUS30 §15, §16).
    """
    record_audit(
        db,
        action=AuditAction.REDEMPTION_REJECTED,
        actor_id=employee_id,
        company_id=company_id,
        entity_type="Benefit",
        entity_id=benefit_id,
        meta={"reason": reason},
    )
    await db.flush()


async def redeem_benefit(
    db: AsyncSession,
    benefit_id: UUID,
    employee_id: UUID,
    company_id: UUID,
    plan: UserPlan,
) -> tuple[BenefitRedemption, PromoCode]:
    """Выдать сотруднику промокод на льготу.

    Проверки §14 по порядку: 1-2 (авторизация и активность) выполняет зависимость
    ``get_current_user``, 3 и 11 (арендатор) — сверка ``company_id`` из JWT,
    4-8 — состояние льготы и мерчанта, 9-10 — лимиты.

    Returns:
        Созданная запись погашения и выданный промокод.

    Raises:
        NotFound: льготы нет.
        Forbidden: льгота неактивна, вне срока, не для этого тарифа или чужой компании.
        Conflict: исчерпан общий лимит или лимит на сотрудника.
    """
    now = datetime.now(UTC)

    # Блокировка строки льготы сериализует параллельные выдачи по одной льготе:
    # без неё два одновременных запроса оба проходят проверку usage_limit и
    # выдают на один код больше разрешённого.
    benefit = await db.scalar(
        select(Benefit)
        .where(Benefit.id == benefit_id)
        .options(selectinload(Benefit.plan_offers), selectinload(Benefit.merchant))
        .with_for_update(of=Benefit)
    )
    if benefit is None:
        raise NotFound(message="Benefit not found")

    if not benefit.is_active:
        await _reject(
            db,
            employee_id=employee_id,
            company_id=company_id,
            benefit_id=benefit_id,
            reason="benefit_inactive",
        )
        raise Forbidden(message="Benefit is inactive")

    if not benefit.is_within_validity(now):
        await _reject(
            db,
            employee_id=employee_id,
            company_id=company_id,
            benefit_id=benefit_id,
            reason="benefit_out_of_validity",
        )
        raise Forbidden(message="Benefit is not within its validity period")

    # Арендатор: корпоративная льгота доступна только своей компании.
    if benefit.company_id is not None and benefit.company_id != company_id:
        await _reject(
            db,
            employee_id=employee_id,
            company_id=company_id,
            benefit_id=benefit_id,
            reason="foreign_company_benefit",
        )
        # NotFound, а не Forbidden: существование чужой корпоративной льготы —
        # сама по себе информация, которую сотрудник знать не должен.
        raise NotFound(message="Benefit not found")

    offer = discount_for_plan(benefit, plan)
    if offer is None:
        await _reject(
            db,
            employee_id=employee_id,
            company_id=company_id,
            benefit_id=benefit_id,
            reason="plan_not_eligible",
        )
        raise Forbidden(
            message=f"Benefit is not available for the {plan.value} plan",
            details={"benefit_id": str(benefit_id), "plan": plan.value},
        )

    merchant = benefit.merchant
    if merchant.status != MerchantStatus.ACTIVE:
        await _reject(
            db,
            employee_id=employee_id,
            company_id=company_id,
            benefit_id=benefit_id,
            reason="merchant_inactive",
        )
        raise Forbidden(message="Merchant is not active")

    # Общий лимит: считаем и выданные, и подтверждённые — обе категории израсходовали
    # место. Считать только ISSUED значило бы освобождать лимит при использовании кода.
    if benefit.usage_limit is not None:
        total_used = (
            await db.scalar(
                select(func.count(BenefitRedemption.id)).where(
                    BenefitRedemption.benefit_id == benefit_id,
                    BenefitRedemption.status.in_(_COUNTED_STATUSES),
                )
            )
        ) or 0
        if total_used >= benefit.usage_limit:
            await _reject(
                db,
                employee_id=employee_id,
                company_id=company_id,
                benefit_id=benefit_id,
                reason="usage_limit_exceeded",
            )
            raise Conflict(
                message="Benefit usage limit has been reached",
                details={"usage_limit": benefit.usage_limit},
            )

    employee_used = (
        await db.scalar(
            select(func.count(BenefitRedemption.id)).where(
                BenefitRedemption.benefit_id == benefit_id,
                BenefitRedemption.employee_id == employee_id,
                BenefitRedemption.status.in_(_COUNTED_STATUSES),
            )
        )
    ) or 0
    if employee_used >= benefit.max_redemptions_per_employee:
        await _reject(
            db,
            employee_id=employee_id,
            company_id=company_id,
            benefit_id=benefit_id,
            reason="duplicate_redemption",
        )
        raise Conflict(
            message="You have already redeemed this benefit",
            details={
                "already_redeemed": employee_used,
                "max_allowed": benefit.max_redemptions_per_employee,
            },
        )

    redemption = BenefitRedemption(
        employee_id=employee_id,
        company_id=company_id,
        benefit_id=benefit_id,
        status=RedemptionStatus.ISSUED,
    )
    db.add(redemption)
    await db.flush()

    promo = await issue_promo_code(
        db=db,
        benefit_id=benefit_id,
        employee_id=employee_id,
        redemption_id=redemption.id,
        merchant_name=merchant.name,
        promo_valid_days=benefit.promo_valid_days,
    )

    record_audit(
        db,
        action=AuditAction.REDEMPTION_CREATED,
        actor_id=employee_id,
        company_id=company_id,
        entity_type="BenefitRedemption",
        entity_id=redemption.id,
        meta={
            "benefit_id": str(benefit_id),
            "promo_code_id": str(promo.id),
            "discount_percent": float(offer.discount_percent),
        },
    )
    record_audit(
        db,
        action=AuditAction.PROMO_ISSUED,
        actor_id=employee_id,
        company_id=company_id,
        entity_type="PromoCode",
        entity_id=promo.id,
        meta={"benefit_id": str(benefit_id)},
    )
    await db.flush()

    return redemption, promo
