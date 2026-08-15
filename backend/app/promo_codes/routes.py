"""Merchant promo code redemption endpoint (NEXUS30 §41).

Merchant validates and confirms a promo code presented by an employee at their
service location or website. Platform administrators can also redeem or override
a code's status.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.audit.service import record_audit
from app.benefits.models import Benefit
from app.benefits.visibility import discount_for_plan
from app.core.deps import AuthUser, DbSession, require_roles
from app.core.enums import AuditAction, PromoCodeStatus, RedemptionStatus, UserRole
from app.core.errors import BadRequest, Forbidden, NotFound
from app.events.publisher import publish_promo_redeemed
from app.promo_codes.models import PromoCode
from app.promo_codes.service import redeem_promo_code
from app.redemptions.models import BenefitRedemption
from app.redemptions.schemas import PromoCodeLookupResponse

router = APIRouter(prefix="/promo-codes", tags=["promo codes"])

__all__ = ["router"]

MerchantOrAdmin = Annotated[
    AuthUser,
    Depends(require_roles(UserRole.MERCHANT, UserRole.PLATFORM_ADMIN)),
]


@router.get("/{code}", response_model=PromoCodeLookupResponse)
async def lookup_promo_code(
    code: str,
    db: DbSession,
    user: MerchantOrAdmin,
) -> PromoCodeLookupResponse:
    """Lookup promo code details without confirming redemption (NEXUS30 §41).

    Merchant and platform admin can verify a code presented by an employee.
    """
    promo = await db.scalar(
        select(PromoCode)
        .where(PromoCode.code == code.upper().strip())
        .options(
            selectinload(PromoCode.benefit).selectinload(Benefit.merchant),
            selectinload(PromoCode.redemption).selectinload(BenefitRedemption.employee),
        )
    )
    if promo is None:
        raise NotFound(message="Promo code not found")

    benefit = promo.benefit
    if user.role == UserRole.MERCHANT and benefit.merchant_id != user.merchant_id:
        raise Forbidden(message="This promo code belongs to a different merchant")

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


@router.post("/{code}/redeem", status_code=status.HTTP_200_OK)
async def confirm_redemption(
    code: str,
    db: DbSession,
    user: MerchantOrAdmin,
) -> dict[str, str]:
    """Confirm promo code redemption by merchant or platform admin (NEXUS30 §41).

    This transitions the promo code to REDEEMED and updates the linked redemption.
    """
    promo = await db.scalar(
        select(PromoCode)
        .where(PromoCode.code == code.upper().strip())
        .options(
            selectinload(PromoCode.benefit).selectinload(Benefit.merchant),
            selectinload(PromoCode.redemption).selectinload(BenefitRedemption.employee),
        )
    )
    if promo is None:
        raise NotFound(message="Promo code not found")

    benefit = promo.benefit
    if user.role == UserRole.MERCHANT and benefit.merchant_id != user.merchant_id:
        raise Forbidden(message="This promo code belongs to a different merchant")

    if promo.status == PromoCodeStatus.REDEEMED:
        raise BadRequest(message="Promo code has already been redeemed")

    promo = await redeem_promo_code(db, code, user.user_id)

    if promo.redemption:
        redemption = await db.get(BenefitRedemption, promo.redemption_id)
        if redemption and redemption.status == RedemptionStatus.ISSUED:
            redemption.status = RedemptionStatus.REDEEMED
            redemption.redeemed_at = promo.redeemed_at

    record_audit(
        db,
        action=AuditAction.PROMO_REDEEMED,
        actor_id=user.user_id,
        company_id=promo.redemption.company_id if promo.redemption else None,
        entity_type="promo_code",
        entity_id=promo.id,
        meta={
            "promo_code_id": str(promo.id),
            "benefit_id": str(benefit.id),
            "merchant_id": str(benefit.merchant_id),
            "redeemed_by_role": user.role.value,
        },
    )

    await db.commit()

    if promo.redemption and promo.redemption.employee and promo.redeemed_at is not None:
        await publish_promo_redeemed(
            user_id=promo.employee_id,
            promo_code=promo.code,
            benefit_id=benefit.id,
            redeemed_at=promo.redeemed_at,
        )

    return {"message": "Promo code redeemed successfully", "code": promo.code}
