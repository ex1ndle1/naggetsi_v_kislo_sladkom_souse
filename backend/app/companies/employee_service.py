"""Управление сотрудниками компании (NEXUS30 §31, §37).

Смена тарифа и деактивация меняют счётчик занятых мест, поэтому обе операции
проходят через `app.plans.service` под блокировкой строки: администратор компании
и параллельная регистрация по приглашению конкурируют за одно и то же место.

Все выборки ограничены `company_id` из JWT. Он участвует в WHERE, а не
проверяется после чтения: запрос за чужим сотрудником должен возвращать «не
найдено», а не «найдено, но нельзя» — второе подтверждает существование строки.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_audit
from app.core.enums import AuditAction, UserPlan, UserRole
from app.core.errors import Conflict, NotFound
from app.plans.service import assign_seat, unassign_seat
from app.promo_codes.models import PromoCode
from app.redemptions.models import BenefitRedemption
from app.users.models import User

__all__ = [
    "EmployeeRow",
    "activate_employee",
    "change_employee_plan",
    "deactivate_employee",
    "list_employees",
]


@dataclass(frozen=True)
class EmployeeRow:
    """Строка списка сотрудников для дашборда компании (§31).

    `redemptions` и `last_activity` считаются агрегатами в SQL, а не обходом
    связей: список сотрудников — самый частый запрос кабинета, и N+1 здесь
    превращает его в десятки запросов на страницу.
    """

    user: User
    redemptions: int
    last_activity: datetime | None


async def list_employees(
    db: AsyncSession,
    company_id: UUID,
    *,
    plan: UserPlan | None = None,
    is_active: bool | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[EmployeeRow], int]:
    """Сотрудники компании с числом полученных льгот и датой последней активности.

    Returns:
        (страница, всего).
    """
    conditions = [User.company_id == company_id, User.role == UserRole.EMPLOYEE]
    if plan is not None:
        conditions.append(User.plan == plan)
    if is_active is not None:
        conditions.append(User.is_active.is_(is_active))

    total = await db.scalar(select(func.count(User.id)).where(*conditions)) or 0

    # LEFT JOIN + GROUP BY: сотрудник без ни одной льготы обязан попасть в список
    # с нулём, иначе новый сотрудник исчезает из кабинета до первой активности.
    stmt = (
        select(
            User,
            func.count(BenefitRedemption.id).label("redemptions"),
            func.max(BenefitRedemption.created_at).label("last_activity"),
        )
        .outerjoin(BenefitRedemption, BenefitRedemption.employee_id == User.id)
        .where(*conditions)
        .group_by(User.id)
        .order_by(User.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).all()
    items = [EmployeeRow(user=row[0], redemptions=row[1], last_activity=row[2]) for row in rows]
    return items, total


async def _get_employee_for_update(db: AsyncSession, company_id: UUID, user_id: UUID) -> User:
    """Сотрудник своей компании под блокировкой строки.

    Raises:
        NotFound: сотрудника нет либо он принадлежит другой компании.
    """
    stmt = (
        select(User)
        .where(
            User.id == user_id,
            User.company_id == company_id,
            User.role == UserRole.EMPLOYEE,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    employee = await db.scalar(stmt)
    if employee is None:
        raise NotFound(message="Employee not found")
    return employee


async def change_employee_plan(
    db: AsyncSession,
    *,
    company_id: UUID,
    user_id: UUID,
    new_plan: UserPlan,
    actor_id: UUID,
) -> User:
    """Перевести сотрудника на другой тариф.

    Порядок операций важен: место нового тарифа занимается до освобождения
    старого. При обратном порядке отказ из-за отсутствия свободных мест оставил
    бы сотрудника без места вообще, и инвариант пришлось бы восстанавливать
    вручную. `assign_seat` бросает NoSeatsAvailable — старое место не тронуто.

    Raises:
        Conflict: сотрудник уже на этом тарифе.
        NoSeatsAvailable: свободных мест нового тарифа нет (§4).
        NotFound: сотрудник не найден в этой компании.
    """
    employee = await _get_employee_for_update(db, company_id, user_id)
    old_plan = employee.plan

    if old_plan == new_plan:
        raise Conflict(
            message="Employee already has this plan",
            details={"plan": new_plan.value},
        )

    await assign_seat(db, company_id, new_plan)
    if old_plan is not None:
        await unassign_seat(db, company_id, old_plan)

    employee.plan = new_plan
    await db.flush()

    record_audit(
        db,
        action=AuditAction.PLAN_CHANGED,
        actor_id=actor_id,
        company_id=company_id,
        entity_type="User",
        entity_id=employee.id,
        meta={
            "old_plan": old_plan.value if old_plan else None,
            "new_plan": new_plan.value,
        },
    )
    return employee


async def deactivate_employee(
    db: AsyncSession,
    *,
    company_id: UUID,
    user_id: UUID,
    actor_id: UUID,
) -> User:
    """Деактивировать сотрудника и освободить его место.

    Учётная запись не удаляется: на ней висят выданные промокоды и история
    погашений, нужные мерчанту и аудиту. Тариф тоже сохраняется — он показывает,
    какое место сотрудник занимал, и нужен при повторной активации.

    Повторный вызов на уже отключённом сотруднике ничего не делает и не считается
    ошибкой: место освобождено, требуемое состояние достигнуто.
    """
    employee = await _get_employee_for_update(db, company_id, user_id)

    if not employee.is_active:
        return employee

    employee.is_active = False
    if employee.plan is not None:
        await unassign_seat(db, company_id, employee.plan)
    await db.flush()

    record_audit(
        db,
        action=AuditAction.USER_BLOCKED,
        actor_id=actor_id,
        company_id=company_id,
        entity_type="User",
        entity_id=employee.id,
        meta={"plan": employee.plan.value if employee.plan else None, "scope": "company_deactivate"},
    )
    return employee


async def activate_employee(
    db: AsyncSession,
    *,
    company_id: UUID,
    user_id: UUID,
    actor_id: UUID,
) -> User:
    """Вернуть сотрудника в работу, снова заняв место его тарифа.

    Место занимается до снятия флага: если мест не осталось, сотрудник остаётся
    отключённым, а не активным без места (§4).

    Raises:
        NoSeatsAvailable: свободных мест его тарифа нет.
        Conflict: у сотрудника нет тарифа — сначала нужно назначить его.
    """
    employee = await _get_employee_for_update(db, company_id, user_id)

    if employee.is_active:
        return employee

    if employee.plan is None:
        raise Conflict(message="Employee has no plan assigned")

    await assign_seat(db, company_id, employee.plan)
    employee.is_active = True
    await db.flush()

    record_audit(
        db,
        action=AuditAction.USER_UNBLOCKED,
        actor_id=actor_id,
        company_id=company_id,
        entity_type="User",
        entity_id=employee.id,
        meta={"plan": employee.plan.value, "scope": "company_activate"},
    )
    return employee


async def count_promo_codes(db: AsyncSession, company_id: UUID) -> int:
    """Сколько кодов выдано сотрудникам компании.

    Считается через redemption, а не по employee_id: связь с компанией
    зафиксирована в момент выдачи и не меняется, если сотрудник сменил компанию.
    """
    return (
        await db.scalar(
            select(func.count(PromoCode.id))
            .join(BenefitRedemption, BenefitRedemption.id == PromoCode.redemption_id)
            .where(BenefitRedemption.company_id == company_id)
        )
    ) or 0
