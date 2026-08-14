"""Роуты каталога льгот (NEXUS30 §35).

Employee: список отфильтрован по плану (visibility.py), redeem benefit.
Merchant: CRUD своих льгот.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.benefits.models import Benefit
from app.benefits.plan_offers import BenefitPlanOffer
from app.benefits.schemas import (
    BenefitCreateRequest,
    BenefitDetailResponse,
    BenefitListItem,
    BenefitUpdateRequest,
    MerchantBenefitResponse,
    PlanOfferInput,
    PlanOfferResponse,
)
from app.benefits.visibility import discount_for_plan, visible_benefits_query
from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.enums import BenefitCategory, RedemptionStatus, UserRole
from app.core.errors import Forbidden, NotFound
from app.core.pagination import Page, PageParams, paginate
from app.redemptions.models import BenefitRedemption
from app.redemptions.service import redeem_benefit

router = APIRouter(prefix="/benefits", tags=["benefits"])

__all__ = ["router"]


# === Employee endpoints ===


@router.get("", response_model=Page[BenefitListItem])
async def list_benefits(
    db: DbSession,
    user: CurrentUser,
    pagination: PageParams = Depends(),
    category: BenefitCategory | None = Query(default=None),
) -> Page[BenefitListItem]:
    """Каталог льгот, отфильтрованный по плану пользователя (NEXUS30 §8, §28)."""
    if not user.company_id or not user.plan:
        raise Forbidden(message="Only employees with a plan can browse benefits")

    stmt = visible_benefits_query(user.plan, user.company_id)
    if category:
        stmt = stmt.where(Benefit.category == category)

    page = await paginate(db, stmt, pagination)

    # Enrichment: подгрузка "already_redeemed" для каждой льготы.
    benefit_ids = [b.id for b in page.items]
    redeemed_stmt = select(BenefitRedemption.benefit_id).where(
        BenefitRedemption.employee_id == user.user_id,
        BenefitRedemption.benefit_id.in_(benefit_ids),
        BenefitRedemption.status.in_([RedemptionStatus.ISSUED, RedemptionStatus.REDEEMED]),
    )
    redeemed_ids = set((await db.scalars(redeemed_stmt)).all())

    items = []
    for benefit in page.items:
        offer = discount_for_plan(benefit, user.plan)
        items.append(
            BenefitListItem(
                id=benefit.id,
                title=benefit.title,
                description=benefit.description,
                category=benefit.category,
                merchant_id=benefit.merchant_id,
                merchant_name=benefit.merchant.name if benefit.merchant else "",
                destination_url=benefit.destination_url,
                valid_until=benefit.valid_until,
                your_discount_percent=offer.discount_percent if offer else 0,
                plan_offers=[
                    PlanOfferResponse.model_validate(o)
                    for o in benefit.plan_offers
                    if o.is_available
                ],
                already_redeemed=(benefit.id in redeemed_ids),
            )
        )

    return Page(items=items, meta=page.meta)


@router.get("/{benefit_id}", response_model=BenefitDetailResponse)
async def get_benefit_detail(
    benefit_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> BenefitDetailResponse:
    """Детали льготы (NEXUS30 §28)."""
    if not user.company_id or not user.plan:
        raise Forbidden(message="Only employees with a plan can view benefits")

    stmt = visible_benefits_query(user.plan, user.company_id).where(Benefit.id == benefit_id)
    benefit = await db.scalar(stmt)

    if not benefit:
        raise NotFound(message="Benefit not found or not available for your plan")

    offer = discount_for_plan(benefit, user.plan)
    count = await db.scalar(
        select(func.count(BenefitRedemption.id)).where(
            BenefitRedemption.employee_id == user.user_id,
            BenefitRedemption.benefit_id == benefit_id,
            BenefitRedemption.status.in_([RedemptionStatus.ISSUED, RedemptionStatus.REDEEMED]),
        )
    )
    already_redeemed = count > 0

    return BenefitDetailResponse(
        id=benefit.id,
        title=benefit.title,
        description=benefit.description,
        category=benefit.category,
        merchant_id=benefit.merchant_id,
        merchant_name=benefit.merchant.name if benefit.merchant else "",
        destination_url=benefit.destination_url,
        valid_until=benefit.valid_until,
        your_discount_percent=offer.discount_percent if offer else 0,
        plan_offers=[
            PlanOfferResponse.model_validate(o) for o in benefit.plan_offers if o.is_available
        ],
        already_redeemed=already_redeemed,
        max_redemptions_per_employee=benefit.max_redemptions_per_employee,
        promo_valid_days=benefit.promo_valid_days,
        redemptions_left=benefit.max_redemptions_per_employee - count,
    )


@router.post("/{benefit_id}/redeem", response_model=dict)
async def redeem_benefit_endpoint(
    benefit_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> dict:
    """Получить promo code для льготы (NEXUS30 §11, §14)."""
    if not user.company_id or not user.plan:
        raise Forbidden(message="Only employees with a plan can redeem benefits")

    redemption, promo_code = await redeem_benefit(
        db=db,
        benefit_id=benefit_id,
        employee_id=user.user_id,
        company_id=user.company_id,
        plan=user.plan,
    )
    await db.commit()

    return {
        "redemption_id": str(redemption.id),
        "promo_code": promo_code,
        "expires_at": redemption.promo_code[0].expires_at.isoformat()
        if redemption.promo_code
        else None,
        "message": "Promo code issued successfully. Use it at the merchant's website.",
    }


# === Merchant endpoints (placeholder) ===


@router.post("/merchant/benefits", response_model=MerchantBenefitResponse)
async def create_merchant_benefit(
    payload: BenefitCreateRequest,
    db: DbSession,
    user: CurrentUser = Depends(require_roles(UserRole.MERCHANT, UserRole.PLATFORM_ADMIN)),
) -> MerchantBenefitResponse:
    """Создать льготу (NEXUS30 §30). Stub для следующей стадии."""
    raise NotImplementedError("Merchant benefit creation will be implemented in next stage")
