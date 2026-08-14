"""Сервис управления seat allocation (NEXUS30 §4).

Проверяет наличие свободных мест перед назначением плана сотруднику,
атомарно увеличивает/уменьшает счётчики assigned.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserPlan
from app.core.errors import Conflict, NotFound
from app.plans.models import PlanAllocation

__all__ = ["check_seat_available", "assign_seat", "unassign_seat", "get_allocation"]


async def get_allocation(
    db: AsyncSession, company_id: UUID, plan: UserPlan
) -> PlanAllocation:
    """Получить allocation или создать с нулевыми значениями."""
    stmt = select(PlanAllocation).where(
        PlanAllocation.company_id == company_id,
        PlanAllocation.plan == plan,
    )
    allocation = await db.scalar(stmt)

    if not allocation:
        allocation = PlanAllocation(
            company_id=company_id,
            plan=plan,
            allocated=0,
            assigned=0,
        )
        db.add(allocation)
        await db.flush()

    return allocation


async def check_seat_available(
    db: AsyncSession, company_id: UUID, plan: UserPlan
) -> bool:
    """Проверить, есть ли свободное место данного плана."""
    allocation = await get_allocation(db, company_id, plan)
    return allocation.available > 0


async def assign_seat(db: AsyncSession, company_id: UUID, plan: UserPlan) -> None:
    """Назначить место (атомарно увеличить assigned).

    Raises:
        Conflict: нет свободных мест
    """
    allocation = await get_allocation(db, company_id, plan)

    if allocation.available <= 0:
        raise Conflict(
            message=f"No available {plan.value} seats for company {company_id}",
            details={"allocated": allocation.allocated, "assigned": allocation.assigned},
        )

    allocation.assigned += 1
    await db.flush()


async def unassign_seat(db: AsyncSession, company_id: UUID, plan: UserPlan) -> None:
    """Освободить место (атомарно уменьшить assigned)."""
    allocation = await get_allocation(db, company_id, plan)

    if allocation.assigned > 0:
        allocation.assigned -= 1
        await db.flush()
