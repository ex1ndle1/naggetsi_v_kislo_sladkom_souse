"""Учёт мест (seats) по тарифам — NEXUS30 §4.

`allocated` меняет только администратор (сколько мест куплено по контракту),
`assigned` — регистрация сотрудника и смена его тарифа.

Инвариант ``assigned <= allocated`` продублирован CheckConstraint'ом в БД:
сервис — первая линия защиты, ограничение — последняя. Поэтому все операции,
меняющие `assigned`, читают строку под ``FOR UPDATE``: без блокировки две
одновременные регистрации прочитали бы одно и то же available=1 и обе бы
инкрементировали счётчик.
"""

from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserPlan
from app.core.errors import Conflict, NoSeatsAvailable
from app.plans.models import PlanAllocation

__all__ = [
    "assign_seat",
    "check_seat_available",
    "get_allocation",
    "get_or_create_allocation",
    "list_allocations",
    "set_allocated",
    "unassign_seat",
]


async def get_allocation(
    db: AsyncSession,
    company_id: UUID,
    plan: UserPlan,
    *,
    for_update: bool = False,
) -> PlanAllocation | None:
    """Прочитать строку мест. Возвращает None, если тариф компании не продавался.

    Отсутствие строки — не ошибка чтения, а осмысленный ответ «мест этого
    тарифа у компании нет вовсе», поэтому строка не создаётся на лету.
    """
    stmt = select(PlanAllocation).where(
        PlanAllocation.company_id == company_id,
        PlanAllocation.plan == plan,
    )
    if for_update:
        # populate_existing обязателен: если объект уже в identity map, SELECT
        # возьмёт блокировку, но оставит в памяти прежние (устаревшие) значения
        # allocated/assigned, и проверка available выполнится по старым данным.
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return cast(PlanAllocation | None, await db.scalar(stmt))


async def list_allocations(db: AsyncSession, company_id: UUID) -> list[PlanAllocation]:
    """Все тарифные строки компании, в порядке возрастания тарифа."""
    stmt = select(PlanAllocation).where(PlanAllocation.company_id == company_id).order_by(PlanAllocation.plan)
    return list((await db.scalars(stmt)).all())


async def get_or_create_allocation(db: AsyncSession, company_id: UUID, plan: UserPlan) -> PlanAllocation:
    """Строка мест для административной записи; создаётся с нулями."""
    allocation = await get_allocation(db, company_id, plan)
    if allocation is None:
        allocation = PlanAllocation(company_id=company_id, plan=plan, allocated=0, assigned=0)
        db.add(allocation)
        await db.flush()
    return allocation


async def check_seat_available(db: AsyncSession, company_id: UUID, plan: UserPlan) -> bool:
    """Есть ли свободное место. Только для подсказок в UI.

    Между этой проверкой и `assign_seat` место может занять другой запрос,
    поэтому решение о выдаче принимает `assign_seat` под блокировкой.
    """
    allocation = await get_allocation(db, company_id, plan)
    return allocation is not None and allocation.available > 0


async def assign_seat(db: AsyncSession, company_id: UUID, plan: UserPlan) -> PlanAllocation:
    """Занять место. Строка блокируется до конца транзакции вызывающего.

    Raises:
        NoSeatsAvailable: тариф не продавался компании либо мест не осталось.
    """
    allocation = await get_allocation(db, company_id, plan, for_update=True)

    if allocation is None:
        raise NoSeatsAvailable(
            message=f"Company has no {plan.value} seats",
            details={"plan": plan.value, "allocated": 0, "assigned": 0},
        )

    if allocation.available <= 0:
        raise NoSeatsAvailable(
            message=f"No available {plan.value} seats",
            details={
                "plan": plan.value,
                "allocated": allocation.allocated,
                "assigned": allocation.assigned,
            },
        )

    allocation.assigned += 1
    await db.flush()
    return allocation


async def unassign_seat(db: AsyncSession, company_id: UUID, plan: UserPlan) -> None:
    """Освободить место (сотрудник деактивирован или сменил тариф).

    Отсутствие строки и нулевой assigned игнорируются: освобождение места,
    которого нет, — не ошибка состояния, а уже достигнутый результат.
    """
    allocation = await get_allocation(db, company_id, plan, for_update=True)

    if allocation is not None and allocation.assigned > 0:
        allocation.assigned -= 1
        await db.flush()


async def set_allocated(db: AsyncSession, company_id: UUID, plan: UserPlan, allocated: int) -> PlanAllocation:
    """Задать количество купленных мест.

    Raises:
        Conflict: новое значение меньше уже выданных мест.
    """
    if allocated < 0:
        raise Conflict(
            message="Allocated seats cannot be negative",
            details={"allocated": allocated},
        )

    allocation = await get_or_create_allocation(db, company_id, plan)
    # Перечитать под блокировкой: между созданием и записью значение assigned
    # могло вырасти за счёт параллельной регистрации.
    locked = await get_allocation(db, company_id, plan, for_update=True)
    allocation = locked if locked is not None else allocation

    if allocated < allocation.assigned:
        raise Conflict(
            message="Cannot allocate fewer seats than already assigned",
            details={"requested": allocated, "assigned": allocation.assigned},
        )

    allocation.allocated = allocated
    await db.flush()
    return allocation
