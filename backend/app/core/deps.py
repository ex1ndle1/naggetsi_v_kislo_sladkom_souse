"""FastAPI dependencies: auth, tenant context, RBAC.

CurrentUser — JWT-токен, не из тела запроса.
TenantContext — серверный контекст (company_id/merchant_id только из JWT).
require_roles(*roles) — RBAC-зависимость на роутер/эндпоинт.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.enums import UserPlan, UserRole
from app.core.errors import Forbidden, Unauthenticated
from app.core.security import decode_token

__all__ = [
    "AuthUser",
    "CurrentUser",
    "DbSession",
    "TenantContext",
    "get_current_user",
    "get_tenant_context",
    "require_roles",
]

DbSession = Annotated[AsyncSession, Depends(get_session)]


@dataclass(frozen=True)
class AuthUser:
    """Авторизованный пользователь из JWT-токена."""

    user_id: UUID
    role: UserRole
    company_id: UUID | None
    merchant_id: UUID | None
    # Тариф сотрудника. None у мерчантов и админов — у них нет каталога.
    plan: UserPlan | None = None


@dataclass(frozen=True)
class TenantContext:
    """Серверный tenant-контекст для фильтрации данных."""

    company_id: UUID | None
    merchant_id: UUID | None
    is_platform_admin: bool


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> AuthUser:
    """Извлекает и валидирует JWT access-токен из заголовка Authorization.

    Денилист здесь не проверяется: отзываются refresh-токены (``app/users/service.py``),
    а access живёт 15 минут — обращение в Redis на каждый запрос API стоило бы
    дороже, чем даёт сокращение этого окна.

    Raises:
        Unauthenticated: если токен отсутствует, невалиден или просрочен.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise Unauthenticated(message="Missing or invalid Authorization header")

    token = authorization[len("Bearer ") :]

    try:
        payload = decode_token(token)
    except jwt.InvalidTokenError as e:
        raise Unauthenticated(message="Invalid or expired token") from e

    # Проверяем тип токена
    if payload.get("type") != "access":
        raise Unauthenticated(message="Invalid token type")

    user_id_str = payload.get("sub")
    role_str = payload.get("role")

    if not user_id_str or not role_str:
        raise Unauthenticated(message="Token missing required claims")

    try:
        user_id = UUID(user_id_str)
        role = UserRole(role_str)
    except (ValueError, KeyError) as e:
        raise Unauthenticated(message="Invalid token claims") from e

    # Извлекаем опциональные tenant-поля
    try:
        company_id = UUID(payload["company_id"]) if payload.get("company_id") else None
        merchant_id = UUID(payload["merchant_id"]) if payload.get("merchant_id") else None
        plan = UserPlan(payload["plan"]) if payload.get("plan") else None
    except ValueError as e:
        raise Unauthenticated(message="Invalid token claims") from e

    return AuthUser(
        user_id=user_id,
        role=role,
        company_id=company_id,
        merchant_id=merchant_id,
        plan=plan,
    )


CurrentUser = Annotated[AuthUser, Depends(get_current_user)]


def get_tenant_context(user: CurrentUser) -> TenantContext:
    """Создаёт TenantContext из авторизованного пользователя.

    company_id и merchant_id берутся ТОЛЬКО из JWT, никогда из тела/query.
    """
    return TenantContext(
        company_id=user.company_id,
        merchant_id=user.merchant_id,
        is_platform_admin=user.role == UserRole.PLATFORM_ADMIN,
    )


def require_roles(
    *roles: UserRole | Sequence[UserRole],
) -> Callable[[AuthUser], AuthUser]:
    """Создаёт RBAC-зависимость: проверяет, что роль пользователя в разрешённом списке.

    Принимает и varargs, и один список — оба варианта встречаются в роутерах::

        require_roles(UserRole.PLATFORM_ADMIN)
        require_roles(UserRole.MERCHANT, UserRole.PLATFORM_ADMIN)

    Возвращает сам AuthUser, поэтому зависимость работает и как значение
    параметра, и как чистая проверка в ``dependencies=[...]``::

        user: Annotated[AuthUser, Depends(require_roles(UserRole.EMPLOYEE))]
        @router.get(..., dependencies=[Depends(require_roles(UserRole.PLATFORM_ADMIN))])
    """
    allowed: set[UserRole] = set()
    for role in roles:
        if isinstance(role, UserRole):
            allowed.add(role)
        else:
            allowed.update(role)

    def _check_role(user: CurrentUser) -> AuthUser:
        if user.role not in allowed:
            raise Forbidden(message=f"Access denied: requires one of {sorted(r.value for r in allowed)}")
        return user

    return _check_role
