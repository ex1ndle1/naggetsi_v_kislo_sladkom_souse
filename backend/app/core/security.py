"""Security: password hashing, JWT, RBAC matrix.

Пароли: argon2-cffi напрямую (без passlib).
JWT: access 15 мин / refresh 7 дней, refresh с ротацией и jti-denylist в Redis.
RBAC: матрица роль→эндпоинты, покрывается параметризованным тестом.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

from app.core.config import settings
from app.core.enums import UserRole

__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "RBAC_MATRIX",
]

# Argon2 hasher с рекомендованными параметрами OWASP.
_ph = PasswordHasher(
    time_cost=2,
    memory_cost=65536,  # 64 MiB
    parallelism=1,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    """Хеширует пароль через Argon2id."""
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Проверяет пароль. Возвращает True если совпадает, False иначе.

    Ловим весь Argon2Error, а не только VerifyMismatchError: повреждённый или
    нераспознанный хеш в БД должен давать «неверный пароль», а не 500.
    """
    try:
        _ph.verify(password_hash, password)
        # Проверка необходимости rehash (если параметры изменились).
        if _ph.check_needs_rehash(password_hash):
            # В production здесь можно логировать событие для фонового rehash.
            pass
        return True
    except Argon2Error:
        return False


def create_access_token(
    *,
    user_id: UUID,
    role: UserRole,
    company_id: UUID | None = None,
    merchant_id: UUID | None = None,
) -> str:
    """Создаёт access-токен (15 минут)."""
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.jwt_access_expire_minutes)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role.value,
        "type": "access",
        "iat": now,
        "exp": exp,
    }

    if company_id:
        payload["company_id"] = str(company_id)
    if merchant_id:
        payload["merchant_id"] = str(merchant_id)

    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(*, user_id: UUID) -> tuple[str, str]:
    """Создаёт refresh-токен (7 дней) с уникальным jti.

    Возвращает (token, jti) — jti нужно сохранить в Redis для отзыва.
    """
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=settings.jwt_refresh_expire_days)
    jti = str(uuid4())

    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": jti,
        "iat": now,
        "exp": exp,
    }

    token = jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    return token, jti


def decode_token(token: str) -> dict[str, Any]:
    """Декодирует и валидирует JWT-токен.

    Raises:
        jwt.InvalidTokenError: если токен невалиден/просрочен.
    """
    return jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
        options={"verify_exp": True},
    )


# ---------------------------------------------------------------------------
# RBAC Matrix (§14 ТЗ)
# ---------------------------------------------------------------------------
# Формат: {"METHOD /path/pattern": [allowed_roles]}
# Новый эндпоинт без политики → тест упадёт.

RBAC_MATRIX: dict[str, list[UserRole]] = {
    # Health & docs
    "GET /api/v1/health": [UserRole.EMPLOYEE, UserRole.MERCHANT, UserRole.COMPANY_ADMIN, UserRole.PLATFORM_ADMIN],

    # Auth (public)
    "POST /api/v1/auth/register": [],  # публичный
    "POST /api/v1/auth/login": [],
    "POST /api/v1/auth/refresh": [],
    "POST /api/v1/auth/logout": [UserRole.EMPLOYEE, UserRole.MERCHANT, UserRole.COMPANY_ADMIN, UserRole.PLATFORM_ADMIN],

    # Benefits
    "GET /api/v1/benefits": [UserRole.EMPLOYEE, UserRole.COMPANY_ADMIN],
    "GET /api/v1/benefits/{id}": [UserRole.EMPLOYEE, UserRole.COMPANY_ADMIN, UserRole.MERCHANT],
    "POST /api/v1/benefits": [UserRole.MERCHANT],
    "PATCH /api/v1/benefits/{id}": [UserRole.MERCHANT],
    "DELETE /api/v1/benefits/{id}": [UserRole.MERCHANT, UserRole.PLATFORM_ADMIN],

    # Applications
    "GET /api/v1/applications": [UserRole.EMPLOYEE, UserRole.COMPANY_ADMIN],
    "GET /api/v1/applications/{id}": [UserRole.EMPLOYEE, UserRole.COMPANY_ADMIN],
    "POST /api/v1/applications": [UserRole.EMPLOYEE],
    "DELETE /api/v1/applications/{id}": [UserRole.EMPLOYEE],
    "GET /api/v1/applications/events": [UserRole.EMPLOYEE, UserRole.COMPANY_ADMIN],  # SSE

    # Payments
    "GET /api/v1/payments": [UserRole.EMPLOYEE, UserRole.COMPANY_ADMIN, UserRole.PLATFORM_ADMIN],
    "GET /api/v1/payments/{id}": [UserRole.EMPLOYEE, UserRole.COMPANY_ADMIN, UserRole.PLATFORM_ADMIN],
    "POST /api/v1/payments": [UserRole.EMPLOYEE],
    "POST /api/v1/payments/click/prepare": [],  # webhook, публичный (проверка подписи внутри)
    "POST /api/v1/payments/click/complete": [],

    # Merchants
    "GET /api/v1/merchants": [UserRole.PLATFORM_ADMIN],
    "GET /api/v1/merchants/{id}": [UserRole.MERCHANT, UserRole.PLATFORM_ADMIN],
    "POST /api/v1/merchants": [UserRole.PLATFORM_ADMIN],
    "PATCH /api/v1/merchants/{id}": [UserRole.MERCHANT, UserRole.PLATFORM_ADMIN],
    "POST /api/v1/merchants/{id}/block": [UserRole.PLATFORM_ADMIN],
    "POST /api/v1/merchants/{id}/unblock": [UserRole.PLATFORM_ADMIN],

    # Company
    "GET /api/v1/companies/{id}": [UserRole.COMPANY_ADMIN, UserRole.PLATFORM_ADMIN],
    "GET /api/v1/companies/{id}/employees": [UserRole.COMPANY_ADMIN],
    "GET /api/v1/companies/{id}/budget": [UserRole.COMPANY_ADMIN],
    "PATCH /api/v1/companies/{id}/budget": [UserRole.COMPANY_ADMIN],
    "GET /api/v1/companies/{id}/analytics": [UserRole.COMPANY_ADMIN],

    # Admin
    "GET /api/v1/admin/users": [UserRole.PLATFORM_ADMIN],
    "PATCH /api/v1/admin/users/{id}/block": [UserRole.PLATFORM_ADMIN],
    "PATCH /api/v1/admin/users/{id}/unblock": [UserRole.PLATFORM_ADMIN],
    "GET /api/v1/admin/payments": [UserRole.PLATFORM_ADMIN],
    "GET /api/v1/admin/audit-logs": [UserRole.PLATFORM_ADMIN],

    # AI
    "POST /api/v1/ai/concierge": [UserRole.EMPLOYEE],
    "POST /api/v1/ai/merchant-assistant": [UserRole.MERCHANT],
    "POST /api/v1/ai/company-insights": [UserRole.COMPANY_ADMIN],
}
