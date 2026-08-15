"""Companies router: управление компаниями (только PLATFORM_ADMIN)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from app.companies.models import Company
from app.companies.schemas import (
    CompanyCreateRequest,
    CompanyListResponse,
    CompanyResponse,
    CompanyUpdateRequest,
)
from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.enums import UserRole
from app.core.errors import Forbidden, NotFound

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=CompanyListResponse)
async def list_companies(
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require_roles(UserRole.PLATFORM_ADMIN, UserRole.COMPANY_ADMIN))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> CompanyListResponse:
    """Список компаний (PLATFORM_ADMIN видит все, COMPANY_ADMIN — только свою)."""
    stmt = select(Company)

    # Tenant isolation для COMPANY_ADMIN
    if user.role == UserRole.COMPANY_ADMIN and user.company_id:
        stmt = stmt.where(Company.id == user.company_id)

    # Подсчёт total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt) or 0

    # Пагинация
    stmt = stmt.offset((page - 1) * page_size).limit(page_size).order_by(Company.created_at.desc())
    result = await db.scalars(stmt)
    items = [CompanyResponse.model_validate(company) for company in result.all()]

    return CompanyListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: UUID,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require_roles(UserRole.PLATFORM_ADMIN, UserRole.COMPANY_ADMIN))],
) -> Company:
    """Получить детали компании."""
    stmt = select(Company).where(Company.id == company_id)
    company = await db.scalar(stmt)

    if not company:
        raise NotFound(message="Company not found")

    # Tenant isolation
    if user.role == UserRole.COMPANY_ADMIN and company.id != user.company_id:
        raise Forbidden(message="Access denied")

    return company


@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    payload: CompanyCreateRequest,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require_roles(UserRole.PLATFORM_ADMIN))],
) -> Company:
    """Создать новую компанию (только PLATFORM_ADMIN)."""
    from app.core.enums import CompanyStatus

    company = Company(
        name=payload.name,
        status=CompanyStatus.ACTIVE,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


@router.patch("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: UUID,
    payload: CompanyUpdateRequest,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require_roles(UserRole.PLATFORM_ADMIN))],
) -> Company:
    """Обновить компанию (только PLATFORM_ADMIN)."""
    stmt = select(Company).where(Company.id == company_id)
    company = await db.scalar(stmt)

    if not company:
        raise NotFound(message="Company not found")

    if payload.name is not None:
        company.name = payload.name
    if payload.status is not None:
        company.status = payload.status

    await db.commit()
    await db.refresh(company)
    return company


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    company_id: UUID,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require_roles(UserRole.PLATFORM_ADMIN))],
) -> None:
    """Удалить компанию (только PLATFORM_ADMIN, каскадно удаляет связанные данные)."""
    stmt = select(Company).where(Company.id == company_id)
    company = await db.scalar(stmt)

    if not company:
        raise NotFound(message="Company not found")

    await db.delete(company)
    await db.commit()
