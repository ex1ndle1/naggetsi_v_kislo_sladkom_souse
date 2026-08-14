"""Сервис promo code lifecycle (NEXUS30 §12, §14).

Выдача кодов, валидация, redemption (merchant/admin подтверждает использование).
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequest, Conflict, NotFound
from app.core.enums import PromoCodeStatus
from app.promo_codes.generator import generate_promo_code
from app.promo_codes.models import PromoCode

__all__ = ["issue_promo_code", "redeem_promo_code", "expire_old_codes"]


async def issue_promo_code(
    db: AsyncSession,
    benefit_id: UUID,
    employee_id: UUID,
    redemption_id: UUID,
    merchant_name: str,
    promo_valid_days: int,
    max_attempts: int = 5,
) -> PromoCode:
    """Выдать promo code сотруднику (NEXUS30 §14).

    Генерирует уникальный код; повторяет до max_attempts при коллизии.

    Args:
        benefit_id: льгота
        employee_id: сотрудник
        redemption_id: привязка к BenefitRedemption
        merchant_name: для формирования префикса
        promo_valid_days: срок жизни кода (из Benefit.promo_valid_days)
        max_attempts: сколько попыток генерации при коллизии

    Returns:
        PromoCode

    Raises:
        Conflict: не удалось сгенерировать уникальный код за max_attempts попыток
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=promo_valid_days)

    for attempt in range(max_attempts):
        code = generate_promo_code(merchant_name)

        promo = PromoCode(
            code=code,
            benefit_id=benefit_id,
            employee_id=employee_id,
            redemption_id=redemption_id,
            status=PromoCodeStatus.ISSUED,
            issued_at=now,
            expires_at=expires_at,
        )
        db.add(promo)

        try:
            await db.flush()
            return promo
        except IntegrityError:
            await db.rollback()
            # Коллизия по unique constraint — повторяем генерацию.
            if attempt == max_attempts - 1:
                raise Conflict(message="Failed to generate unique promo code")
            continue

    raise Conflict(message="Failed to generate unique promo code")


async def redeem_promo_code(
    db: AsyncSession,
    code: str,
    redeemed_by_id: UUID,
) -> PromoCode:
    """Подтвердить использование promo code (merchant или admin вводит код).

    Raises:
        NotFound: код не найден
        BadRequest: код уже использован / истёк / отозван
    """
    now = datetime.now(timezone.utc)

    stmt = select(PromoCode).where(PromoCode.code == code.upper().strip())
    promo = await db.scalar(stmt)

    if not promo:
        raise NotFound(message="Promo code not found")

    if promo.status != PromoCodeStatus.ISSUED:
        raise BadRequest(message=f"Promo code is {promo.status.value.lower()}")

    if promo.is_expired(now):
        promo.status = PromoCodeStatus.EXPIRED
        await db.flush()
        raise BadRequest(message="Promo code has expired")

    promo.status = PromoCodeStatus.REDEEMED
    promo.redeemed_at = now
    promo.redeemed_by_id = redeemed_by_id
    await db.flush()

    return promo


async def expire_old_codes(db: AsyncSession) -> int:
    """Пометить просроченные коды как EXPIRED (background job).

    Returns:
        Количество обновлённых записей.
    """
    now = datetime.now(timezone.utc)

    stmt = select(PromoCode).where(
        PromoCode.status == PromoCodeStatus.ISSUED,
        PromoCode.expires_at <= now,
    )
    expired = (await db.scalars(stmt)).all()

    for promo in expired:
        promo.status = PromoCodeStatus.EXPIRED

    await db.flush()
    return len(expired)
