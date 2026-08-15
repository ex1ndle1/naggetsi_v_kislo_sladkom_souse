"""Личный кабинет: профиль и история сотрудника (NEXUS30 §35).

``GET /me`` — канонический источник профиля для фронтенда. Разбирать JWT в
браузере нельзя: там нет ни актуального `is_active`, ни имени, а тариф в токене
отстаёт на время его жизни.

История ограничена ролью EMPLOYEE: у мерчанта и админа промокодов не бывает.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import AuthUser, CurrentUser, DbSession, require_roles
from app.core.enums import PromoCodeStatus, UserRole
from app.core.errors import BadRequest, NotFound
from app.core.pagination import Page, PageParams, build_page
from app.redemptions.history import list_my_promo_codes, list_my_redemptions
from app.redemptions.schemas import MyPromoCodeItem, MyRedemptionItem
from app.users.models import User
from app.users.schemas import UserResponse
from app.users.service import get_user_by_id

router = APIRouter(prefix="/me", tags=["me"])

__all__ = ["router"]

EmployeeUser = Annotated[AuthUser, Depends(require_roles(UserRole.EMPLOYEE))]


@router.get("", response_model=UserResponse, summary="Профиль текущего пользователя")
async def get_me(user: CurrentUser, db: DbSession) -> User:
    """Профиль из БД, а не из токена.

    Токен живёт 15 минут; за это время администратор мог сменить тариф или
    заблокировать учётную запись, и фронтенд должен видеть текущее состояние.
    """
    profile = await get_user_by_id(db, user.user_id)
    if profile is None:
        # Токен подписан нами, но пользователя больше нет: 404 честнее 401 —
        # токен действителен, отсутствует именно объект.
        raise NotFound(message="User not found")
    return profile


@router.get(
    "/promo-codes",
    response_model=Page[MyPromoCodeItem],
    summary="Промокоды сотрудника",
)
async def get_my_promo_codes(
    db: DbSession,
    user: EmployeeUser,
    pagination: Annotated[PageParams, Depends()],
    status: Annotated[PromoCodeStatus | None, Query()] = None,
) -> Page[MyPromoCodeItem]:
    """Выданные сотруднику промокоды, новые первыми."""
    if user.plan is None:
        raise BadRequest(message="Employee must be assigned to a plan")

    items, total = await list_my_promo_codes(
        db,
        employee_id=user.user_id,
        plan=user.plan,
        status=status,
        limit=pagination.page_size,
        offset=(pagination.page - 1) * pagination.page_size,
    )
    return build_page(items, pagination, total)


@router.get(
    "/redemptions",
    response_model=Page[MyRedemptionItem],
    summary="История получения льгот",
)
async def get_my_redemptions(
    db: DbSession,
    user: EmployeeUser,
    pagination: Annotated[PageParams, Depends()],
) -> Page[MyRedemptionItem]:
    """Факты получения льгот сотрудником, новые первыми."""
    items, total = await list_my_redemptions(
        db,
        employee_id=user.user_id,
        limit=pagination.page_size,
        offset=(pagination.page - 1) * pagination.page_size,
    )
    return build_page(items, pagination, total)
