"""Сервис управления invite tokens (NEXUS30 §6).

Генерация, валидация, one-time use.
Токен хранится как SHA-256 хеш; plaintext отдаётся создателю один раз.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import InviteTokenStatus, UserPlan
from app.core.errors import BadRequest, NotFound
from app.invites.models import InviteToken

__all__ = [
    "create_invite_token",
    "validate_and_consume_token",
    "expire_old_tokens",
]


def _hash_token(token: str) -> str:
    """SHA-256 хеш токена для хранения в БД."""
    return hashlib.sha256(token.encode()).hexdigest()


def _generate_token() -> str:
    """Сгенерировать cryptographically secure token (32 байта = 64 hex chars)."""
    return secrets.token_hex(32)


async def create_invite_token(
    db: AsyncSession,
    company_id: UUID,
    plan: UserPlan,
    created_by_id: UUID | None,
    email: str | None = None,
    expires_in_days: int = 7,
) -> tuple[InviteToken, str]:
    """Создать invite token.

    Returns:
        (InviteToken, plaintext_token): plaintext нужно показать создателю один раз.
    """
    plaintext = _generate_token()
    token_hash = _hash_token(plaintext)

    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

    invite = InviteToken(
        token_hash=token_hash,
        company_id=company_id,
        plan=plan,
        email=email,
        status=InviteTokenStatus.ACTIVE,
        expires_at=expires_at,
        created_by_id=created_by_id,
    )
    db.add(invite)
    await db.flush()

    return invite, plaintext


async def validate_and_consume_token(
    db: AsyncSession,
    plaintext_token: str,
    email: str,
    used_by_id: UUID,
) -> InviteToken:
    """Валидировать токен и пометить как использованный (one-time).

    Raises:
        NotFound: токен не найден
        BadRequest: токен истёк / уже использован / email не совпадает
    """
    token_hash = _hash_token(plaintext_token)
    now = datetime.now(timezone.utc)

    stmt = select(InviteToken).where(InviteToken.token_hash == token_hash)
    invite = await db.scalar(stmt)

    if not invite:
        raise NotFound(message="Invalid invite token")

    # Проверка статуса
    if invite.status != InviteTokenStatus.ACTIVE:
        raise BadRequest(message=f"Invite token is {invite.status.value.lower()}")

    # Проверка expiration
    if invite.is_expired(now):
        invite.status = InviteTokenStatus.EXPIRED
        await db.flush()
        raise BadRequest(message="Invite token has expired")

    # Проверка email (если задан)
    if invite.email and invite.email.lower() != email.lower():
        raise BadRequest(
            message="This invite token is for a different email address",
            details={"expected": invite.email},
        )

    # Пометить как использованный (one-time use)
    invite.status = InviteTokenStatus.USED
    invite.used_at = now
    invite.used_by_id = used_by_id
    await db.flush()

    return invite


async def expire_old_tokens(db: AsyncSession) -> int:
    """Пометить просроченные токены как EXPIRED (background job).

    Returns:
        Количество обновлённых записей.
    """
    now = datetime.now(timezone.utc)

    stmt = (
        select(InviteToken)
        .where(
            InviteToken.status == InviteTokenStatus.ACTIVE,
            InviteToken.expires_at <= now,
        )
    )
    expired = (await db.scalars(stmt)).all()

    for invite in expired:
        invite.status = InviteTokenStatus.EXPIRED

    await db.flush()
    return len(expired)
