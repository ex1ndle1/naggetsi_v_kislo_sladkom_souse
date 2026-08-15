"""Кабинет администратора компании (NEXUS30 §31, §37).

Все эндпоинты работают с компанией из JWT: `company_id` не принимается ни в
теле, ни в query. Приглашение — единственный способ появления сотрудника (§5),
поэтому создание аккаунта здесь отсутствует: администратор выдаёт токен, а
регистрацию завершает сам сотрудник.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.sql.elements import ColumnElement

from app.analytics.service import company_analytics
from app.audit.service import record_audit
from app.companies.admin_schemas import (
    CompanyOverviewResponse,
    EmployeeListItem,
    EmployeePlanChangeRequest,
    EmployeeResponse,
    InviteCreatedResponse,
    InviteCreateRequest,
    InviteListItem,
    SeatAllocationItem,
    SeatsResponse,
)
from app.companies.employee_service import (
    activate_employee,
    change_employee_plan,
    deactivate_employee,
    list_employees,
)
from app.companies.models import Company
from app.core.deps import AuthUser, DbSession, require_roles
from app.core.enums import AuditAction, InviteTokenStatus, UserPlan, UserRole
from app.core.errors import BadRequest, NotFound
from app.core.pagination import Page, PageParams, build_page
from app.invites.service import create_invite_token, list_invites, revoke_invite_token
from app.plans.service import list_allocations
from app.users.models import User

router = APIRouter(prefix="/company", tags=["company"])

__all__ = ["router"]

CompanyAdmin = Annotated[AuthUser, Depends(require_roles(UserRole.COMPANY_ADMIN))]


def _company_id(user: AuthUser) -> UUID:
    """Компания администратора из токена.

    COMPANY_ADMIN без company_id — испорченные данные, а не законное состояние:
    без компании его права ни к чему не применимы.
    """
    if user.company_id is None:
        raise BadRequest(message="COMPANY_ADMIN must be associated with a company")
    return user.company_id


async def _seats(db: DbSession, company_id: UUID) -> SeatsResponse:
    allocations = await list_allocations(db, company_id)
    return SeatsResponse(plans=[SeatAllocationItem.model_validate(row) for row in allocations])


@router.get("/analytics", summary="Аналитика компании")
async def get_company_analytics(db: DbSession, user: CompanyAdmin) -> dict[str, object]:
    """Плановая загрузка и использование льгот в рамках компании из JWT."""
    analytics = await company_analytics(db, _company_id(user))
    return analytics.to_prompt_payload()


def _active_employee_conditions(company_id: UUID) -> list[ColumnElement[bool]]:
    """Условия «активный сотрудник этой компании» — одни и те же в счётчике и списке."""
    return [
        User.company_id == company_id,
        User.role == UserRole.EMPLOYEE,
        User.is_active.is_(True),
    ]


@router.get("", response_model=CompanyOverviewResponse, summary="Карточка компании и места")
async def get_company_overview(db: DbSession, user: CompanyAdmin) -> CompanyOverviewResponse:
    """Сводка для дашборда: компания, места по тарифам, число активных сотрудников."""
    company_id = _company_id(user)
    company = await db.scalar(select(Company).where(Company.id == company_id))
    if company is None:
        raise NotFound(message="Company not found")

    active_employees = (
        await db.scalar(select(func.count(User.id)).where(*_active_employee_conditions(company_id)))
    ) or 0

    return CompanyOverviewResponse(
        id=company.id,
        name=company.name,
        status=company.status,
        seats=await _seats(db, company_id),
        active_employees=active_employees,
        created_at=company.created_at,
    )


@router.get("/seats", response_model=SeatsResponse, summary="Места по тарифам")
async def get_seats(db: DbSession, user: CompanyAdmin) -> SeatsResponse:
    """Купленные, занятые и свободные места (§4, §31)."""
    return await _seats(db, _company_id(user))


@router.get("/employees", response_model=Page[EmployeeListItem], summary="Сотрудники компании")
async def get_employees(
    db: DbSession,
    user: CompanyAdmin,
    pagination: Annotated[PageParams, Depends()],
    plan: Annotated[UserPlan | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> Page[EmployeeListItem]:
    """Список сотрудников с числом полученных льгот и датой последней активности."""
    rows, total = await list_employees(
        db,
        _company_id(user),
        plan=plan,
        is_active=is_active,
        limit=pagination.page_size,
        offset=(pagination.page - 1) * pagination.page_size,
    )
    items = [
        EmployeeListItem(
            id=row.user.id,
            email=row.user.email,
            first_name=row.user.first_name,
            last_name=row.user.last_name,
            plan=row.user.plan,
            is_active=row.user.is_active,
            redemptions=row.redemptions,
            last_activity=row.last_activity,
            created_at=row.user.created_at,
        )
        for row in rows
    ]
    return build_page(items, pagination, total)


@router.post(
    "/employees/{user_id}/plan",
    response_model=EmployeeResponse,
    summary="Сменить тариф сотрудника",
)
async def change_plan(
    user_id: UUID,
    payload: EmployeePlanChangeRequest,
    db: DbSession,
    user: CompanyAdmin,
) -> EmployeeResponse:
    """Перевести сотрудника на другой тариф.

    Отказывает, если свободных мест нового тарифа нет (§4): место занимается до
    освобождения старого, поэтому при отказе сотрудник остаётся на прежнем.
    """
    company_id = _company_id(user)
    employee = await change_employee_plan(
        db,
        company_id=company_id,
        user_id=user_id,
        new_plan=payload.plan,
        actor_id=user.user_id,
    )
    await db.commit()
    return EmployeeResponse.model_validate(employee)


@router.post(
    "/employees/{user_id}/deactivate",
    response_model=EmployeeResponse,
    summary="Деактивировать сотрудника",
)
async def deactivate(user_id: UUID, db: DbSession, user: CompanyAdmin) -> EmployeeResponse:
    """Отключить сотрудника и освободить его место. Учётная запись сохраняется."""
    employee = await deactivate_employee(
        db,
        company_id=_company_id(user),
        user_id=user_id,
        actor_id=user.user_id,
    )
    await db.commit()
    return EmployeeResponse.model_validate(employee)


@router.post(
    "/employees/{user_id}/activate",
    response_model=EmployeeResponse,
    summary="Вернуть сотрудника в работу",
)
async def activate(user_id: UUID, db: DbSession, user: CompanyAdmin) -> EmployeeResponse:
    """Снова занять место тарифа сотрудника и включить учётную запись."""
    employee = await activate_employee(
        db,
        company_id=_company_id(user),
        user_id=user_id,
        actor_id=user.user_id,
    )
    await db.commit()
    return EmployeeResponse.model_validate(employee)


@router.post(
    "/invites",
    response_model=InviteCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать приглашение",
)
async def create_invite(
    payload: InviteCreateRequest,
    db: DbSession,
    user: CompanyAdmin,
) -> InviteCreatedResponse:
    """Выдать одноразовый токен регистрации.

    Место не занимается здесь: приглашение может остаться неиспользованным, а
    занятое место всё это время было бы недоступно другому сотруднику. Счётчик
    растёт при регистрации, и тогда же проверяется наличие свободного места.
    """
    company_id = _company_id(user)
    invite, plaintext = await create_invite_token(
        db=db,
        company_id=company_id,
        plan=payload.plan,
        created_by_id=user.user_id,
        email=payload.email,
        expires_in_days=payload.expires_in_days,
    )

    record_audit(
        db,
        action=AuditAction.INVITE_CREATED,
        actor_id=user.user_id,
        company_id=company_id,
        entity_type="InviteToken",
        entity_id=invite.id,
        # Ни plaintext, ни хеш: журнал читают администраторы, а токен — секрет.
        meta={"plan": payload.plan.value, "email": payload.email},
    )
    await db.commit()

    return InviteCreatedResponse(
        id=invite.id,
        token=plaintext,
        plan=invite.plan,
        email=invite.email,
        expires_at=invite.expires_at,
    )


@router.get("/invites", response_model=Page[InviteListItem], summary="Приглашения компании")
async def get_invites(
    db: DbSession,
    user: CompanyAdmin,
    pagination: Annotated[PageParams, Depends()],
    invite_status: Annotated[InviteTokenStatus | None, Query(alias="status")] = None,
) -> Page[InviteListItem]:
    """Выданные приглашения. Ни хеш, ни plaintext наружу не отдаются."""
    rows, total = await list_invites(
        db,
        _company_id(user),
        status=invite_status,
        limit=pagination.page_size,
        offset=(pagination.page - 1) * pagination.page_size,
    )
    items = [InviteListItem.model_validate(row) for row in rows]
    return build_page(items, pagination, total)


@router.post(
    "/invites/{invite_id}/revoke",
    response_model=InviteListItem,
    summary="Отозвать приглашение",
)
async def revoke_invite(invite_id: UUID, db: DbSession, user: CompanyAdmin) -> InviteListItem:
    """Погасить неиспользованное приглашение.

    Отказ выглядит одинаково и для чужого приглашения, и для уже использованного:
    иначе перебором можно было бы узнать, какие идентификаторы существуют.
    """
    company_id = _company_id(user)
    invite = await revoke_invite_token(db, invite_id, company_id)
    record_audit(
        db,
        action=AuditAction.INVITE_EXPIRED,
        actor_id=user.user_id,
        company_id=company_id,
        entity_type="InviteToken",
        entity_id=invite.id,
        meta={"plan": invite.plan.value, "action": "revoked"},
    )
    await db.commit()
    return InviteListItem.model_validate(invite)
