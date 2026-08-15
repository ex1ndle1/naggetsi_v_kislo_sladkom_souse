"""Platform administration read APIs (NEXUS30 §40).

The platform administrator may inspect cross-tenant operational data.  All
mutations remain explicit and auditable; ordinary company and merchant users are
not accepted by this router.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.audit.models import AuditLog
from app.audit.service import record_audit
from app.benefits.models import Benefit
from app.benefits.schemas import MerchantBenefitResponse
from app.core.deps import AuthUser, DbSession, require_roles
from app.core.enums import AuditAction, PromoCodeStatus, RedemptionStatus, UserRole
from app.core.errors import NotFound
from app.core.pagination import Page, PageParams, paginate
from app.promo_codes.models import PromoCode
from app.redemptions.models import BenefitRedemption
from app.users.models import User
from app.users.schemas import UserResponse

router = APIRouter(prefix="/admin", tags=["platform administration"])

__all__ = ["router"]

PlatformAdmin = Annotated[AuthUser, Depends(require_roles(UserRole.PLATFORM_ADMIN))]


class AdminPromoCodeItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    status: PromoCodeStatus
    benefit_id: UUID
    employee_id: UUID
    redemption_id: UUID | None
    issued_at: str
    expires_at: str
    redeemed_at: str | None


class AdminRedemptionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_id: UUID
    company_id: UUID
    benefit_id: UUID
    status: RedemptionStatus
    redeemed_at: str | None
    created_at: str


class AuditLogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_id: UUID | None
    company_id: UUID | None
    action: AuditAction
    entity_type: str | None
    entity_id: str | None
    meta: dict[str, object] | None
    created_at: str


@router.get("/users", response_model=Page[UserResponse])
async def list_users(
    db: DbSession,
    _user: PlatformAdmin,
    pagination: Annotated[PageParams, Depends()],
    role: Annotated[UserRole | None, Query()] = None,
    company_id: Annotated[UUID | None, Query()] = None,
    merchant_id: Annotated[UUID | None, Query()] = None,
) -> Page[UserResponse]:
    """List users with optional role and tenant filters for platform support."""
    stmt = select(User).order_by(User.created_at.desc())
    if role is not None:
        stmt = stmt.where(User.role == role)
    if company_id is not None:
        stmt = stmt.where(User.company_id == company_id)
    if merchant_id is not None:
        stmt = stmt.where(User.merchant_id == merchant_id)
    page = await paginate(db, stmt, pagination)
    return Page(items=[UserResponse.model_validate(item) for item in page.items], meta=page.meta)


async def _user_or_404(db: DbSession, user_id: UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFound(message="User not found")
    return user


@router.patch("/users/{user_id}/block", response_model=UserResponse)
async def block_user(user_id: UUID, db: DbSession, actor: PlatformAdmin) -> User:
    """Block account access while retaining all tenant history."""
    target = await _user_or_404(db, user_id)
    target.is_active = False
    record_audit(
        db,
        action=AuditAction.USER_BLOCKED,
        actor_id=actor.user_id,
        company_id=target.company_id,
        entity_type="user",
        entity_id=target.id,
    )
    await db.commit()
    return target


@router.patch("/users/{user_id}/unblock", response_model=UserResponse)
async def unblock_user(user_id: UUID, db: DbSession, actor: PlatformAdmin) -> User:
    """Restore access to a platform-blocked account."""
    target = await _user_or_404(db, user_id)
    target.is_active = True
    record_audit(
        db,
        action=AuditAction.USER_UNBLOCKED,
        actor_id=actor.user_id,
        company_id=target.company_id,
        entity_type="user",
        entity_id=target.id,
    )
    await db.commit()
    return target


@router.get("/benefits", response_model=Page[MerchantBenefitResponse])
async def list_benefits(
    db: DbSession,
    _user: PlatformAdmin,
    pagination: Annotated[PageParams, Depends()],
    merchant_id: Annotated[UUID | None, Query()] = None,
    company_id: Annotated[UUID | None, Query()] = None,
) -> Page[MerchantBenefitResponse]:
    """Inspect platform benefits across merchants and company scopes."""
    stmt = select(Benefit).order_by(Benefit.created_at.desc())
    if merchant_id is not None:
        stmt = stmt.where(Benefit.merchant_id == merchant_id)
    if company_id is not None:
        stmt = stmt.where(Benefit.company_id == company_id)
    page = await paginate(db, stmt, pagination)
    return Page(
        items=[MerchantBenefitResponse.model_validate(item) for item in page.items],
        meta=page.meta,
    )


@router.get("/promo-codes", response_model=Page[AdminPromoCodeItem])
async def list_promo_codes(
    db: DbSession,
    _user: PlatformAdmin,
    pagination: Annotated[PageParams, Depends()],
    promo_status: Annotated[PromoCodeStatus | None, Query(alias="status")] = None,
) -> Page[AdminPromoCodeItem]:
    """List promo-code lifecycle records, newest first."""
    stmt = select(PromoCode).order_by(PromoCode.issued_at.desc())
    if promo_status is not None:
        stmt = stmt.where(PromoCode.status == promo_status)
    page = await paginate(db, stmt, pagination)
    return Page(
        items=[
            AdminPromoCodeItem(
                id=item.id,
                code=item.code,
                status=item.status,
                benefit_id=item.benefit_id,
                employee_id=item.employee_id,
                redemption_id=item.redemption_id,
                issued_at=item.issued_at.isoformat(),
                expires_at=item.expires_at.isoformat(),
                redeemed_at=item.redeemed_at.isoformat() if item.redeemed_at else None,
            )
            for item in page.items
        ],
        meta=page.meta,
    )


@router.get("/redemptions", response_model=Page[AdminRedemptionItem])
async def list_redemptions(
    db: DbSession,
    _user: PlatformAdmin,
    pagination: Annotated[PageParams, Depends()],
    company_id: Annotated[UUID | None, Query()] = None,
) -> Page[AdminRedemptionItem]:
    """List redemptions for operational support without joining employee PII."""
    stmt = select(BenefitRedemption).order_by(BenefitRedemption.created_at.desc())
    if company_id is not None:
        stmt = stmt.where(BenefitRedemption.company_id == company_id)
    page = await paginate(db, stmt, pagination)
    return Page(
        items=[
            AdminRedemptionItem(
                id=item.id,
                employee_id=item.employee_id,
                company_id=item.company_id,
                benefit_id=item.benefit_id,
                status=item.status,
                redeemed_at=item.redeemed_at.isoformat() if item.redeemed_at else None,
                created_at=item.created_at.isoformat(),
            )
            for item in page.items
        ],
        meta=page.meta,
    )


@router.get("/audit-logs", response_model=Page[AuditLogItem])
async def list_audit_logs(
    db: DbSession,
    _user: PlatformAdmin,
    pagination: Annotated[PageParams, Depends()],
    company_id: Annotated[UUID | None, Query()] = None,
    action: Annotated[AuditAction | None, Query()] = None,
) -> Page[AuditLogItem]:
    """Read immutable audit entries; no delete endpoint exists."""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if company_id is not None:
        stmt = stmt.where(AuditLog.company_id == company_id)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    page = await paginate(db, stmt, pagination)
    return Page(
        items=[
            AuditLogItem(
                id=item.id,
                actor_id=item.actor_id,
                company_id=item.company_id,
                action=item.action,
                entity_type=item.entity_type,
                entity_id=item.entity_id,
                meta=item.meta,
                created_at=item.created_at.isoformat(),
            )
            for item in page.items
        ],
        meta=page.meta,
    )
