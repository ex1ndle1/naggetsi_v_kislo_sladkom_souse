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


@router.post("/bitrix/sync")
async def sync_bitrix_employees(
    payload: "BitrixSyncRequest",
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require_roles(UserRole.COMPANY_ADMIN))],
) -> "BitrixSyncResponse":
    """Импортировать сотрудников из Bitrix24 для компании текущего админа."""
    from app.bitrix.schemas import BitrixSyncRequest, BitrixSyncResponse
    from app.bitrix.service import BitrixService
    from app.core.errors import BadRequest
    from app.core.security import hash_password
    from app.users.models import User

    if not user.company_id:
        raise BadRequest(message="User is not associated with a company")

    company = await db.get(Company, user.company_id)
    if company is None:
        raise NotFound(message="Company not found")

    # Обновить webhook URL
    company.bitrix_webhook_url = str(payload.webhook_url)
    company.bitrix_sync_enabled = True

    # Скачать сотрудников
    try:
        employees_data = await BitrixService.fetch_employees(str(payload.webhook_url))
    except ValueError as exc:
        raise BadRequest(message=str(exc))

    # Импортировать или обновить пользователей
    created_count = 0
    updated_count = 0

    for emp in employees_data:
        if not emp.get("email"):
            continue  # Пропускаем без email

        # Найти существующего по email или external_bitrix_id
        stmt = select(User).where(
            (User.email == emp["email"]) | (User.external_bitrix_id == emp["external_bitrix_id"])
        )
        existing = await db.scalar(stmt)

        if existing:
            # Обновить
            existing.external_bitrix_id = emp["external_bitrix_id"]
            existing.first_name = emp.get("first_name") or existing.first_name
            existing.last_name = emp.get("last_name") or existing.last_name
            updated_count += 1
        else:
            # Создать нового (без плана — назначит COMPANY_ADMIN позже)
            new_user = User(
                email=emp["email"],
                password_hash=hash_password("changeme"),  # Временный пароль
                first_name=emp.get("first_name", ""),
                last_name=emp.get("last_name", ""),
                role=UserRole.EMPLOYEE,
                company_id=user.company_id,
                external_bitrix_id=emp["external_bitrix_id"],
            )
            db.add(new_user)
            created_count += 1

    await db.commit()

    return BitrixSyncResponse(
        company_id=user.company_id,
        webhook_url=str(payload.webhook_url),
        total_fetched=len(employees_data),
        created=created_count,
        updated=updated_count,
    )
