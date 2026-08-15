"""Security: password hashing, JWT, RBAC matrix.

Пароли: argon2-cffi напрямую (без passlib).
JWT: access 15 мин / refresh 7 дней, refresh с ротацией и jti-denylist в Redis.
RBAC: матрица роль→эндпоинты, покрывается параметризованным тестом.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

from app.core.config import settings
from app.core.enums import UserPlan, UserRole

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
    plan: UserPlan | None = None,
) -> str:
    """Создаёт access-токен (15 минут).

    plan попадает в claims, потому что от него зависит видимость каталога (§8), и
    брать его из запроса нельзя. Токен короткий, поэтому смена тарифа отражается
    в правах в пределах 15 минут — сам расчёт скидки при выдаче кода всё равно
    сверяется с БД.
    """
    now = datetime.now(UTC)
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
    if plan:
        payload["plan"] = plan.value

    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(*, user_id: UUID) -> tuple[str, str]:
    """Создаёт refresh-токен (7 дней) с уникальным jti.

    Возвращает (token, jti) — jti нужно сохранить в Redis для отзыва.
    """
    now = datetime.now(UTC)
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

_ALL_ROLES = [
    UserRole.EMPLOYEE,
    UserRole.MERCHANT,
    UserRole.COMPANY_ADMIN,
    UserRole.PLATFORM_ADMIN,
]

RBAC_MATRIX: dict[str, list[UserRole]] = {
    # --- Служебное ---
    "GET /api/v1/health": _ALL_ROLES,
    # --- Аутентификация ---
    # Пустой список = публичный эндпоинт. Регистрация публична по URL, но требует
    # валидный invite token в теле: доступ контролируется токеном, не ролью.
    "POST /api/v1/auth/register": [],
    "POST /api/v1/auth/login": [],
    "POST /api/v1/auth/refresh": [],
    "POST /api/v1/auth/logout": _ALL_ROLES,
    # --- Личный кабинет ---
    # Профиль нужен всем ролям: фронтенд не разбирает JWT самостоятельно.
    "GET /api/v1/me": _ALL_ROLES,
    "GET /api/v1/me/redemptions": [UserRole.EMPLOYEE],
    "GET /api/v1/me/promo-codes": [UserRole.EMPLOYEE],
    # --- Каталог сотрудника ---
    "GET /api/v1/benefits": [UserRole.EMPLOYEE],
    "GET /api/v1/benefits/{benefit_id}": [UserRole.EMPLOYEE],
    "POST /api/v1/benefits/{benefit_id}/redeem": [UserRole.EMPLOYEE],
    # --- Льготы мерчанта ---
    "GET /api/v1/merchant/benefits": [UserRole.MERCHANT, UserRole.PLATFORM_ADMIN],
    "POST /api/v1/merchant/benefits": [UserRole.MERCHANT, UserRole.PLATFORM_ADMIN],
    "GET /api/v1/merchant/benefits/{benefit_id}": [UserRole.MERCHANT, UserRole.PLATFORM_ADMIN],
    "PATCH /api/v1/merchant/benefits/{benefit_id}": [UserRole.MERCHANT, UserRole.PLATFORM_ADMIN],
    "DELETE /api/v1/merchant/benefits/{benefit_id}": [UserRole.MERCHANT, UserRole.PLATFORM_ADMIN],
    "GET /api/v1/merchant/analytics": [UserRole.MERCHANT, UserRole.PLATFORM_ADMIN],
    # --- Подтверждение промокода ---
    "GET /api/v1/merchant/promo-codes/{code}": [UserRole.MERCHANT, UserRole.PLATFORM_ADMIN],
    "POST /api/v1/merchant/promo-codes/{code}/redeem": [
        UserRole.MERCHANT,
        UserRole.PLATFORM_ADMIN,
    ],
    # --- Управление компанией ---
    "GET /api/v1/company": [UserRole.COMPANY_ADMIN],
    "GET /api/v1/company/seats": [UserRole.COMPANY_ADMIN],
    "GET /api/v1/company/employees": [UserRole.COMPANY_ADMIN],
    "POST /api/v1/company/invites": [UserRole.COMPANY_ADMIN],
    "GET /api/v1/company/invites": [UserRole.COMPANY_ADMIN],
    "POST /api/v1/company/employees/{user_id}/plan": [UserRole.COMPANY_ADMIN],
    "POST /api/v1/company/employees/{user_id}/deactivate": [UserRole.COMPANY_ADMIN],
    "GET /api/v1/company/analytics": [UserRole.COMPANY_ADMIN],
    # --- Мерчанты (управление платформой) ---
    "GET /api/v1/merchants": [UserRole.PLATFORM_ADMIN],
    "GET /api/v1/merchants/{merchant_id}": [UserRole.MERCHANT, UserRole.PLATFORM_ADMIN],
    "POST /api/v1/merchants": [UserRole.PLATFORM_ADMIN],
    "PATCH /api/v1/merchants/{merchant_id}": [UserRole.MERCHANT, UserRole.PLATFORM_ADMIN],
    "POST /api/v1/merchants/{merchant_id}/block": [UserRole.PLATFORM_ADMIN],
    "POST /api/v1/merchants/{merchant_id}/unblock": [UserRole.PLATFORM_ADMIN],
    # --- Компании (управление платформой) ---
    "GET /api/v1/companies": [UserRole.PLATFORM_ADMIN],
    "POST /api/v1/companies": [UserRole.PLATFORM_ADMIN],
    "GET /api/v1/companies/{company_id}": [UserRole.COMPANY_ADMIN, UserRole.PLATFORM_ADMIN],
    "PATCH /api/v1/companies/{company_id}": [UserRole.PLATFORM_ADMIN],
    "PUT /api/v1/companies/{company_id}/allocations": [UserRole.PLATFORM_ADMIN],
    # --- Платформенный админ ---
    "GET /api/v1/admin/users": [UserRole.PLATFORM_ADMIN],
    "PATCH /api/v1/admin/users/{user_id}/block": [UserRole.PLATFORM_ADMIN],
    "PATCH /api/v1/admin/users/{user_id}/unblock": [UserRole.PLATFORM_ADMIN],
    "GET /api/v1/admin/promo-codes": [UserRole.PLATFORM_ADMIN],
    "POST /api/v1/admin/promo-codes/{code}/redeem": [UserRole.PLATFORM_ADMIN],
    "POST /api/v1/admin/promo-codes/{code}/revoke": [UserRole.PLATFORM_ADMIN],
    "GET /api/v1/admin/redemptions": [UserRole.PLATFORM_ADMIN],
    "GET /api/v1/admin/audit-logs": [UserRole.PLATFORM_ADMIN],
    # --- Realtime ---
    "POST /api/v1/events/ticket": _ALL_ROLES,
    # Поток аутентифицируется одноразовым тикетом из Redis, а не Bearer-заголовком:
    # EventSource в браузере заголовки отправлять не умеет.
    "GET /api/v1/events/stream": [],
    # --- AI ---
    "POST /api/v1/ai/concierge": [UserRole.EMPLOYEE],
    "POST /api/v1/ai/merchant/generate-offer": [UserRole.MERCHANT, UserRole.PLATFORM_ADMIN],
    "GET /api/v1/ai/company-report": [UserRole.COMPANY_ADMIN, UserRole.PLATFORM_ADMIN],
}
