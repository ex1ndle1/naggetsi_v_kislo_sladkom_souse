"""CRUD льгот в кабинете мерчанта (NEXUS30 §30).

Маршруты намеренно вынесены из employee-каталога: фиксированный префикс
``/merchant`` не пересекается с ``/benefits/{benefit_id}``, а merchant_id всегда
берётся из JWT либо явно указывается platform admin.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select

from app.analytics.service import merchant_analytics
from app.audit.service import record_audit
from app.benefits.models import Benefit
from app.benefits.plan_offers import BenefitPlanOffer
from app.benefits.schemas import (
    BenefitCreateRequest,
    BenefitUpdateRequest,
    MerchantBenefitResponse,
)
from app.core.deps import AuthUser, DbSession, require_roles
from app.core.enums import AuditAction, UserRole
from app.core.errors import BadRequest, NotFound
from app.merchants.models import Merchant

router = APIRouter(prefix="/merchant", tags=["merchant benefits"])

__all__ = ["router"]

MerchantUser = Annotated[
    AuthUser,
    Depends(require_roles(UserRole.MERCHANT, UserRole.PLATFORM_ADMIN)),
]


def _target_merchant_id(user: AuthUser, requested_merchant_id: UUID | None) -> UUID:
    """Resolve the managed merchant without allowing tenant spoofing."""
    if user.role == UserRole.MERCHANT:
        if user.merchant_id is None:
            raise BadRequest(message="Merchant account has no merchant context")
        return user.merchant_id
    if requested_merchant_id is None:
        raise BadRequest(message="merchant_id is required for platform administrator")
    return requested_merchant_id


async def _require_merchant(db: DbSession, merchant_id: UUID) -> Merchant:
    merchant = await db.get(Merchant, merchant_id)
    if merchant is None:
        raise NotFound(message="Merchant not found")
    return merchant


async def _owned_benefit(db: DbSession, merchant_id: UUID, benefit_id: UUID) -> Benefit:
    benefit = await db.scalar(select(Benefit).where(Benefit.id == benefit_id, Benefit.merchant_id == merchant_id))
    if benefit is None:
        # Do not reveal whether another merchant owns the supplied identifier.
        raise NotFound(message="Benefit not found")
    return benefit


def _assert_validity(valid_from: datetime | None, valid_until: datetime | None) -> None:
    if valid_from is not None and valid_until is not None and valid_until <= valid_from:
        raise BadRequest(message="valid_until must be after valid_from")


def _replace_plan_offers(benefit: Benefit, payload: BenefitCreateRequest | BenefitUpdateRequest) -> None:
    """Replace all plan offers as a single ORM unit-of-work operation."""
    offers = payload.plan_offers
    if offers is None:
        return
    benefit.plan_offers.clear()
    benefit.plan_offers.extend(
        BenefitPlanOffer(
            plan=offer.plan,
            discount_percent=offer.discount_percent,
            is_available=offer.is_available,
        )
        for offer in offers
    )


@router.get("/analytics")
async def get_merchant_analytics(
    db: DbSession,
    user: MerchantUser,
    merchant_id: Annotated[UUID | None, Query()] = None,
) -> dict[str, object]:
    """Return redemption aggregates scoped to the merchant tenant."""
    target_merchant_id = _target_merchant_id(user, merchant_id)
    await _require_merchant(db, target_merchant_id)
    return (await merchant_analytics(db, target_merchant_id)).to_dict()


@router.get("/benefits", response_model=list[MerchantBenefitResponse])
async def list_benefits(
    db: DbSession,
    user: MerchantUser,
    merchant_id: Annotated[UUID | None, Query()] = None,
) -> list[Benefit]:
    """List benefits owned by the merchant in the authenticated JWT.

    A platform admin must name the target merchant explicitly; a merchant can
    neither select nor infer another tenant through the query string.
    """
    target_merchant_id = _target_merchant_id(user, merchant_id)
    await _require_merchant(db, target_merchant_id)
    return list(
        (
            await db.scalars(
                select(Benefit).where(Benefit.merchant_id == target_merchant_id).order_by(Benefit.created_at.desc())
            )
        ).all()
    )


@router.post("/benefits", response_model=MerchantBenefitResponse, status_code=status.HTTP_201_CREATED)
async def create_benefit(
    payload: BenefitCreateRequest,
    db: DbSession,
    user: MerchantUser,
) -> Benefit:
    """Create a benefit and all of its tariff offers atomically."""
    merchant_id = _target_merchant_id(user, payload.merchant_id)
    await _require_merchant(db, merchant_id)
    _assert_validity(payload.valid_from, payload.valid_until)

    benefit = Benefit(
        title=payload.title,
        description=payload.description,
        category=payload.category,
        destination_url=payload.destination_url,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        usage_limit=payload.usage_limit,
        max_redemptions_per_employee=payload.max_redemptions_per_employee,
        promo_valid_days=payload.promo_valid_days,
        merchant_id=merchant_id,
        company_id=payload.company_id,
    )
    db.add(benefit)
    _replace_plan_offers(benefit, payload)
    await db.flush()
    record_audit(
        db,
        action=AuditAction.BENEFIT_CREATED,
        actor_id=user.user_id,
        company_id=payload.company_id,
        entity_type="benefit",
        entity_id=benefit.id,
        meta={"merchant_id": str(merchant_id), "plans": [offer.plan.value for offer in payload.plan_offers]},
    )
    await db.commit()
    await db.refresh(benefit, attribute_names=["plan_offers"])
    return benefit


@router.get("/benefits/{benefit_id}", response_model=MerchantBenefitResponse)
async def get_benefit(
    benefit_id: UUID,
    db: DbSession,
    user: MerchantUser,
    merchant_id: Annotated[UUID | None, Query()] = None,
) -> Benefit:
    """Return one benefit without leaking another merchant's data."""
    target_merchant_id = _target_merchant_id(user, merchant_id)
    return await _owned_benefit(db, target_merchant_id, benefit_id)


@router.patch("/benefits/{benefit_id}", response_model=MerchantBenefitResponse)
async def update_benefit(
    benefit_id: UUID,
    payload: BenefitUpdateRequest,
    db: DbSession,
    user: MerchantUser,
    merchant_id: Annotated[UUID | None, Query()] = None,
) -> Benefit:
    """Update benefit fields; supplied plan offers replace the previous set."""
    target_merchant_id = _target_merchant_id(user, merchant_id)
    benefit = await _owned_benefit(db, target_merchant_id, benefit_id)

    values = payload.model_dump(exclude_unset=True, exclude={"plan_offers"})
    proposed_from = values.get("valid_from", benefit.valid_from)
    proposed_until = values.get("valid_until", benefit.valid_until)
    _assert_validity(proposed_from, proposed_until)
    for field, value in values.items():
        setattr(benefit, field, value)
    _replace_plan_offers(benefit, payload)

    action = AuditAction.BENEFIT_DEACTIVATED if payload.is_active is False else AuditAction.BENEFIT_UPDATED
    record_audit(
        db,
        action=action,
        actor_id=user.user_id,
        company_id=benefit.company_id,
        entity_type="benefit",
        entity_id=benefit.id,
        meta={"merchant_id": str(target_merchant_id), "updated_fields": sorted(values)},
    )
    await db.commit()
    await db.refresh(benefit, attribute_names=["plan_offers"])
    return benefit


@router.delete("/benefits/{benefit_id}", response_model=MerchantBenefitResponse)
async def deactivate_benefit(
    benefit_id: UUID,
    db: DbSession,
    user: MerchantUser,
    merchant_id: Annotated[UUID | None, Query()] = None,
) -> Benefit:
    """Soft-deactivate a benefit to retain promo and redemption history."""
    target_merchant_id = _target_merchant_id(user, merchant_id)
    benefit = await _owned_benefit(db, target_merchant_id, benefit_id)
    benefit.is_active = False
    record_audit(
        db,
        action=AuditAction.BENEFIT_DEACTIVATED,
        actor_id=user.user_id,
        company_id=benefit.company_id,
        entity_type="benefit",
        entity_id=benefit.id,
        meta={"merchant_id": str(target_merchant_id)},
    )
    await db.commit()
    await db.refresh(benefit, attribute_names=["plan_offers"])
    return benefit
