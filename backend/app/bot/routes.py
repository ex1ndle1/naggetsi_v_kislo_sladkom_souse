"""Проверка промокода Telegram-ботом (NEXUS30 §41).

Отдельный эндпоинт, а не переиспользование мерчантского ``/merchant/promo-codes/{code}``:
у бота нет пользователя в системе, значит нет ни JWT, ни ``merchant_id``, по которому
проверяется владение кодом. Аутентификация — общий ключ в заголовке.

Бот отвечает на вопрос «код настоящий и его можно погасить?». Погашение остаётся
за мерчантом: подтверждение через бота нельзя привязать к конкретной точке продаж.
"""

from __future__ import annotations

import hmac
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.benefits.visibility import discount_for_plan
from app.core.config import settings
from app.core.deps import DbSession
from app.core.enums import PromoCodeStatus
from app.core.errors import BadRequest, Forbidden, NotFound
from app.promo_codes.models import PromoCode
from app.redemptions.models import BenefitRedemption
from app.redemptions.schemas import PromoCodeLookupResponse

router = APIRouter(prefix="/bot", tags=["bot"])

__all__ = ["router"]


async def require_bot_key(
    x_bot_api_key: Annotated[str | None, Header(alias="X-Bot-Api-Key")] = None,
) -> None:
    """Сверяет ключ бота с настройкой.

    Сравнение через ``compare_digest``: длина совпадающего префикса не должна
    утекать через время ответа. Пустой ключ в настройках означает, что бот не
    настроен, и эндпоинт закрыт для всех.
    """
    expected = settings.bot_api_key.get_secret_value()
    if not expected:
        raise Forbidden(message="Bot API is not configured")
    if not x_bot_api_key or not hmac.compare_digest(x_bot_api_key, expected):
        raise Forbidden(message="Invalid bot API key")


@router.get(
    "/promo/{code}",
    response_model=PromoCodeLookupResponse,
    dependencies=[Depends(require_bot_key)],
)
async def check_promo_code(code: str, db: DbSession) -> PromoCodeLookupResponse:
    """Возвращает статус промокода без его погашения.

    Скидка берётся из ``plan_offers`` льготы по тарифу сотрудника, но сам сотрудник
    в ответе не появляется: боту незачем знать, кто предъявил код.
    """
    promo = await db.scalar(
        select(PromoCode)
        .where(PromoCode.code == code.upper().strip())
        .options(
            selectinload(PromoCode.benefit),
            selectinload(PromoCode.redemption).selectinload(BenefitRedemption.employee),
        )
    )
    if promo is None:
        raise NotFound(message="Promo code not found")

    benefit = promo.benefit
    redemption = promo.redemption
    employee_plan = redemption.employee.plan if redemption and redemption.employee else None
    offer = discount_for_plan(benefit, employee_plan) if employee_plan else None

    return PromoCodeLookupResponse(
        code=promo.code,
        status=promo.status,
        is_redeemable=promo.can_be_redeemed(datetime.now(UTC)),
        expires_at=promo.expires_at,
        redeemed_at=promo.redeemed_at,
        benefit_id=benefit.id,
        benefit_title=benefit.title,
        discount_percent=offer.discount_percent if offer else None,
        employee_plan_discount_note=(
            f"{employee_plan.value}: {offer.discount_percent}%" if employee_plan and offer else None
        ),
    )


@router.post("/promo/{code}/redeem", dependencies=[Depends(require_bot_key)])
async def redeem_promo_code(code: str, db: DbSession) -> dict[str, str]:
    """Погасить промокод через бота. Без привязки к конкретному мерчанту.

    Упрощённая версия активации: меняет статус на REDEEMED без указания,
    кто именно погасил код. Для полноценной активации с привязкой к merchant
    используйте эндпоинт `/merchant/promo-codes/{code}/redeem`.
    """
    promo = await db.scalar(
        select(PromoCode)
        .where(PromoCode.code == code.upper().strip())
        .options(selectinload(PromoCode.benefit), selectinload(PromoCode.redemption))
    )
    if promo is None:
        raise NotFound(message="Promo code not found")

    if not promo.can_be_redeemed(datetime.now(UTC)):
        raise BadRequest(message="Promo code cannot be redeemed (expired, already used, or revoked)")

    promo.status = PromoCodeStatus.REDEEMED
    promo.redeemed_at = datetime.now(UTC)
    await db.commit()

    return {"message": f"Promo code {promo.code} redeemed successfully"}
