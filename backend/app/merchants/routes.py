"""Merchants router: управление мерчантами (только PLATFORM_ADMIN)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.enums import UserRole
from app.core.errors import AlreadyExists, Forbidden, NotFound
from app.merchants.models import Merchant
from app.merchants.schemas import (
    MerchantCreateRequest,
    MerchantListResponse,
    MerchantResponse,
    MerchantUpdateRequest,
)

router = APIRouter(prefix="/merchants", tags=["merchants"])


@router.get("", response_model=MerchantListResponse)
async def list_merchants(
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require_roles(UserRole.PLATFORM_ADMIN, UserRole.MERCHANT))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> MerchantListResponse:
    """Список мерчантов (PLATFORM_ADMIN видит всех, MERCHANT — только себя)."""
    stmt = select(Merchant)

    # Tenant isolation для MERCHANT
    if user.role == UserRole.MERCHANT and user.merchant_id:
        stmt = stmt.where(Merchant.id == user.merchant_id)

    # Подсчёт total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt) or 0

    # Пагинация
    stmt = stmt.offset((page - 1) * page_size).limit(page_size).order_by(Merchant.created_at.desc())
    result = await db.scalars(stmt)
    items = [MerchantResponse.model_validate(merchant) for merchant in result.all()]

    return MerchantListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{merchant_id}", response_model=MerchantResponse)
async def get_merchant(
    merchant_id: UUID,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require_roles(UserRole.PLATFORM_ADMIN, UserRole.MERCHANT))],
) -> Merchant:
    """Получить детали мерчанта."""
    stmt = select(Merchant).where(Merchant.id == merchant_id)
    merchant = await db.scalar(stmt)

    if not merchant:
        raise NotFound(message="Merchant not found")

    # Tenant isolation
    if user.role == UserRole.MERCHANT and merchant.id != user.merchant_id:
        raise Forbidden(message="Access denied")

    return merchant


@router.post("", response_model=MerchantResponse, status_code=status.HTTP_201_CREATED)
async def create_merchant(
    payload: MerchantCreateRequest,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require_roles(UserRole.PLATFORM_ADMIN))],
) -> Merchant:
    """Создать нового мерчанта (только PLATFORM_ADMIN)."""
    from app.core.enums import MerchantStatus

    # Проверка уникальности email
    existing_stmt = select(Merchant).where(Merchant.email == payload.email)
    existing = await db.scalar(existing_stmt)
    if existing:
        raise AlreadyExists(message="Merchant with this email already exists")

    merchant = Merchant(
        name=payload.name,
        email=payload.email,
        status=MerchantStatus.ACTIVE,
        description=payload.description,
    )
    db.add(merchant)
    await db.commit()
    await db.refresh(merchant)
    return merchant


@router.patch("/{merchant_id}", response_model=MerchantResponse)
async def update_merchant(
    merchant_id: UUID,
    payload: MerchantUpdateRequest,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require_roles(UserRole.PLATFORM_ADMIN))],
) -> Merchant:
    """Обновить мерчанта (только PLATFORM_ADMIN)."""
    stmt = select(Merchant).where(Merchant.id == merchant_id)
    merchant = await db.scalar(stmt)

    if not merchant:
        raise NotFound(message="Merchant not found")

    if payload.name is not None:
        merchant.name = payload.name
    if payload.email is not None:
        # Проверка уникальности нового email
        existing_stmt = select(Merchant).where(
            Merchant.email == payload.email,
            Merchant.id != merchant_id,
        )
        existing = await db.scalar(existing_stmt)
        if existing:
            raise AlreadyExists(message="Email already in use")
        merchant.email = payload.email
    if payload.status is not None:
        merchant.status = payload.status
    if payload.description is not None:
        merchant.description = payload.description

    await db.commit()
    await db.refresh(merchant)
    return merchant


@router.delete("/{merchant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_merchant(
    merchant_id: UUID,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require_roles(UserRole.PLATFORM_ADMIN))],
) -> None:
    """Удалить мерчанта (только PLATFORM_ADMIN)."""
    stmt = select(Merchant).where(Merchant.id == merchant_id)
    merchant = await db.scalar(stmt)

    if not merchant:
        raise NotFound(message="Merchant not found")

    await db.delete(merchant)
    await db.commit()
