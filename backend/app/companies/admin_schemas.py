"""Схемы кабинета администратора компании (NEXUS30 §31, §37).

`company_id` нет ни в одном запросе: он приходит из JWT. Поле, которого нет в
схеме, невозможно подделать — администратор одной компании не может адресовать
запрос к другой, даже подобрав идентификатор.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, computed_field

from app.core.enums import CompanyStatus, InviteTokenStatus, UserPlan

__all__ = [
    "CompanyOverviewResponse",
    "EmployeeListItem",
    "EmployeePlanChangeRequest",
    "EmployeeResponse",
    "InviteCreateRequest",
    "InviteCreatedResponse",
    "InviteListItem",
    "SeatAllocationItem",
    "SeatsResponse",
]


class SeatAllocationItem(BaseModel):
    """Места одного тарифа."""

    plan: UserPlan
    allocated: int
    assigned: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def available(self) -> int:
        return self.allocated - self.assigned

    @computed_field  # type: ignore[prop-decorator]
    @property
    def utilization_percent(self) -> float:
        if self.allocated == 0:
            return 0.0
        return round(self.assigned / self.allocated * 100, 1)

    model_config = {"from_attributes": True}


class SeatsResponse(BaseModel):
    """Сводка мест для дашборда (§31: Total / Assigned / Available)."""

    plans: list[SeatAllocationItem]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_allocated(self) -> int:
        return sum(item.allocated for item in self.plans)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_assigned(self) -> int:
        return sum(item.assigned for item in self.plans)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_available(self) -> int:
        return self.total_allocated - self.total_assigned


class CompanyOverviewResponse(BaseModel):
    """`GET /company`: карточка компании вместе с местами."""

    id: UUID
    name: str
    status: CompanyStatus
    seats: SeatsResponse
    active_employees: int
    created_at: datetime


class EmployeeListItem(BaseModel):
    """Строка списка сотрудников (§31: Employee / Plan / Status / Redemptions / Last activity)."""

    id: UUID
    email: EmailStr
    first_name: str
    last_name: str
    plan: UserPlan | None
    is_active: bool
    redemptions: int
    last_activity: datetime | None
    created_at: datetime


class EmployeeResponse(BaseModel):
    """Сотрудник после операции над ним (смена тарифа, включение, отключение).

    Без `redemptions` и `last_activity`: эти агрегаты стоят отдельного запроса и
    операция их не меняет, а отдать в ответе нули означало бы показать в UI
    цифры, не соответствующие действительности.
    """

    id: UUID
    email: EmailStr
    first_name: str
    last_name: str
    plan: UserPlan | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class EmployeePlanChangeRequest(BaseModel):
    """Смена тарифа сотрудника. Отказ при отсутствии свободных мест (§4)."""

    plan: UserPlan


class InviteCreateRequest(BaseModel):
    """Создание приглашения.

    `email` необязателен: приглашение без адреса подойдёт любому, кто получил
    ссылку, — так компания может выдать место сотруднику, чей адрес ещё не
    известен. С адресом токен привязан к нему и чужому не подойдёт.
    """

    plan: UserPlan
    email: EmailStr | None = None
    expires_in_days: int = Field(default=7, ge=1, le=90)


class InviteCreatedResponse(BaseModel):
    """Ответ на создание приглашения.

    `token` возвращается единственный раз: в БД лежит только SHA-256, и
    восстановить plaintext нельзя ни администратору, ни платформе.
    """

    id: UUID
    token: str
    plan: UserPlan
    email: EmailStr | None
    expires_at: datetime


class InviteListItem(BaseModel):
    """Строка списка приглашений. Без хеша и без plaintext."""

    id: UUID
    plan: UserPlan
    email: EmailStr | None
    status: InviteTokenStatus
    expires_at: datetime
    used_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
