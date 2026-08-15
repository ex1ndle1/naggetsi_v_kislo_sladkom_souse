"""Аутентификация и регистрация по приглашению (NEXUS30 §5, §6, §15).

Публичной регистрации нет. `company_id` и `plan` берутся исключительно из
погашенного приглашения: тело запроса на них не влияет, иначе любой желающий
выписал бы себе PRO в чужой компании (§5).

Refresh-токены ротируются: при обновлении прежний jti попадает в денилист в
Redis с TTL до собственного истечения. Access-токены не проверяются по
денилисту — они живут 15 минут, и запрос в Redis на каждый вызов API стоил бы
дороже, чем даёт это окно.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.audit.service import record_audit
from app.core.enums import AuditAction, UserRole
from app.core.errors import (
    AccountBlocked,
    AlreadyExists,
    InvalidCredentials,
    InvalidToken,
)
from app.core.redis import RedisClient
from app.core.security import create_access_token, create_refresh_token, hash_password, verify_password
from app.invites.service import consume_token, lock_and_validate_token
from app.plans.service import assign_seat
from app.users.models import User

__all__ = [
    "authenticate",
    "get_user_by_id",
    "issue_token_pair",
    "is_refresh_revoked",
    "register_by_invite",
    "revoke_refresh_jti",
]

logger = get_logger(__name__)

_DENYLIST_PREFIX = "refresh:denylist:"


# ---------------------------------------------------------------------------
# Регистрация
# ---------------------------------------------------------------------------
async def register_by_invite(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    invite_token: str,
) -> User:
    """Создать сотрудника по приглашению. Транзакцию коммитит вызывающий.

    Приглашение погашается и место занимается в той же транзакции, что и вставка
    пользователя: аккаунт без занятого места (или наоборот) существовать не может.

    Raises:
        AlreadyExists: email занят.
        InviteRejection: приглашение недействительно.
        NoSeatsAvailable: мест этого тарифа не осталось.
    """
    normalized_email = email.strip().lower()

    # Приглашение проверяется до вставки пользователя: отказ не должен откатывать
    # уже созданную учётную запись, а отметка EXPIRED должна сохраниться.
    invite = await lock_and_validate_token(db, invite_token, email=normalized_email)

    if await db.scalar(select(User.id).where(User.email == normalized_email)):
        raise AlreadyExists(message="User with this email already exists")

    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        first_name=first_name,
        last_name=last_name,
        role=UserRole.EMPLOYEE,
        # Тариф и компания — только из приглашения; тело запроса на них не влияет.
        company_id=invite.company_id,
        plan=invite.plan,
        is_active=True,
    )
    db.add(user)

    try:
        # Флеш ради user.id: приглашение хранит, кем оно погашено.
        await db.flush()
    except IntegrityError as e:
        # Проверка выше не защищает от одновременной регистрации того же адреса;
        # окончательный арбитр — уникальный индекс.
        raise AlreadyExists(message="User with this email already exists") from e

    await consume_token(db, invite, used_by_id=user.id)
    await assign_seat(db, invite.company_id, invite.plan)

    record_audit(
        db,
        action=AuditAction.USER_CREATED,
        actor_id=user.id,
        company_id=invite.company_id,
        entity_type="user",
        entity_id=str(user.id),
        meta={"role": user.role.value, "via": "invite"},
    )
    record_audit(
        db,
        action=AuditAction.INVITE_USED,
        actor_id=user.id,
        company_id=invite.company_id,
        entity_type="invite_token",
        entity_id=str(invite.id),
        meta={"plan": invite.plan.value},
    )
    record_audit(
        db,
        action=AuditAction.PLAN_ASSIGNED,
        actor_id=user.id,
        company_id=invite.company_id,
        entity_type="user",
        entity_id=str(user.id),
        meta={"plan": invite.plan.value},
    )

    return user


# ---------------------------------------------------------------------------
# Вход
# ---------------------------------------------------------------------------
async def authenticate(db: AsyncSession, *, email: str, password: str) -> User:
    """Проверить пароль. Транзакцию (с audit-записью) коммитит вызывающий.

    Пароль сверяется даже при отсутствии пользователя — иначе разница во времени
    ответа выдавала бы, какие адреса зарегистрированы.

    Raises:
        InvalidCredentials: адрес не найден либо пароль неверен.
        AccountBlocked: учётная запись деактивирована.
    """
    normalized_email = email.strip().lower()
    user = await db.scalar(select(User).where(User.email == normalized_email))

    password_ok = verify_password(password, user.password_hash) if user else _dummy_verify(password)

    if user is None or not password_ok:
        record_audit(
            db,
            action=AuditAction.USER_LOGIN_FAILED,
            actor_id=user.id if user else None,
            company_id=user.company_id if user else None,
            entity_type="user",
            entity_id=str(user.id) if user else None,
            meta={"email": normalized_email, "reason": "bad_password" if user else "unknown_email"},
        )
        raise InvalidCredentials()

    if not user.is_active:
        record_audit(
            db,
            action=AuditAction.USER_LOGIN_FAILED,
            actor_id=user.id,
            company_id=user.company_id,
            entity_type="user",
            entity_id=str(user.id),
            meta={"reason": "inactive"},
        )
        raise AccountBlocked()

    record_audit(
        db,
        action=AuditAction.USER_LOGIN,
        actor_id=user.id,
        company_id=user.company_id,
        entity_type="user",
        entity_id=str(user.id),
        meta={"role": user.role.value},
    )
    return user


#: Хеш заведомо недостижимого пароля: сверка с ним выравнивает время ответа
#: для несуществующих адресов. Значение считается один раз при импорте.
_DUMMY_HASH = hash_password("password-that-nobody-uses-0000000000")


def _dummy_verify(password: str) -> bool:
    """Потратить столько же времени, сколько заняла бы настоящая проверка."""
    verify_password(password, _DUMMY_HASH)
    return False


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    return cast(User | None, await db.scalar(select(User).where(User.id == user_id)))


# ---------------------------------------------------------------------------
# Токены
# ---------------------------------------------------------------------------
def issue_token_pair(user: User) -> tuple[str, str, str]:
    """Выдать пару токенов.

    Returns:
        (access, refresh, jti нового refresh-токена).
    """
    access = create_access_token(
        user_id=user.id,
        role=user.role,
        company_id=user.company_id,
        merchant_id=user.merchant_id,
        plan=user.plan,
    )
    refresh, jti = create_refresh_token(user_id=user.id)
    return access, refresh, jti


async def revoke_refresh_jti(redis: RedisClient, jti: str, exp_timestamp: int | None) -> None:
    """Занести refresh-токен в денилист до его собственного истечения.

    TTL берётся из claim exp: держать запись дольше бессмысленно — токен и так
    не пройдёт проверку подписи по сроку.

    Недоступность Redis не превращается в 500: пользователь не должен получать
    ошибку при выходе из системы. Событие остаётся в логе.
    """
    ttl = 60
    if exp_timestamp:
        ttl = max(int(exp_timestamp - datetime.now(UTC).timestamp()), 1)

    try:
        await redis.setex(f"{_DENYLIST_PREFIX}{jti}", ttl, "1")
    except (RedisError, OSError) as e:
        logger.warning("refresh_denylist_write_failed", jti=jti, error=str(e))


async def is_refresh_revoked(redis: RedisClient, jti: str) -> bool:
    """Проверить денилист.

    При недоступности Redis отказываем: пропустить, возможно, отозванный токен
    хуже, чем заставить пользователя войти заново.
    """
    try:
        return await redis.exists(f"{_DENYLIST_PREFIX}{jti}") == 1
    except (RedisError, OSError) as e:
        logger.error("refresh_denylist_read_failed", jti=jti, error=str(e))
        raise InvalidToken(message="Token store unavailable, please sign in again") from e
