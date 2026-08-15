"""Invite tokens — единственный путь появления employee-аккаунта (NEXUS30 §5, §6).

В БД лежит только SHA-256 хеш: plaintext отдаётся создателю один раз и больше
нигде не восстанавливается. Токен одноразовый, привязан к компании и тарифу,
опционально — к email.

Все отказы (нет такого токена, использован, истёк, чужой email) возвращают один
и тот же код INVITE_TOKEN_INVALID: разные коды позволили бы перебором отличить
существующий токен от несуществующего. Причина остаётся в audit-логе и в
структурном логе, наружу не уходит.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import InviteTokenStatus, UserPlan
from app.core.errors import InviteTokenInvalid
from app.invites.models import InviteToken

__all__ = [
    "InviteRejection",
    "consume_token",
    "create_invite_token",
    "expire_old_tokens",
    "list_invites",
    "lock_and_validate_token",
    "revoke_invite_token",
]

#: Токен: 32 байта энтропии в hex. Перебор по индексу token_hash невозможен.
_TOKEN_BYTES = 32


class InviteRejection(InviteTokenInvalid):
    """Отказ по инвайту. `reason` — для audit-лога, наружу не сериализуется."""

    def __init__(self, reason: str) -> None:
        super().__init__()
        self.reason = reason


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _generate_token() -> str:
    return secrets.token_hex(_TOKEN_BYTES)


async def create_invite_token(
    db: AsyncSession,
    company_id: UUID,
    plan: UserPlan,
    created_by_id: UUID | None,
    email: str | None = None,
    expires_in_days: int = 7,
) -> tuple[InviteToken, str]:
    """Создать приглашение.

    Returns:
        (запись, plaintext). Plaintext показывается создателю один раз.
    """
    plaintext = _generate_token()
    expires_at = datetime.now(UTC) + timedelta(days=expires_in_days)

    invite = InviteToken(
        token_hash=_hash_token(plaintext),
        company_id=company_id,
        plan=plan,
        email=email.lower() if email else None,
        status=InviteTokenStatus.ACTIVE,
        expires_at=expires_at,
        created_by_id=created_by_id,
    )
    db.add(invite)
    await db.flush()

    return invite, plaintext


async def lock_and_validate_token(db: AsyncSession, plaintext_token: str, email: str) -> InviteToken:
    """Заблокировать строку приглашения и проверить пригодность.

    Строка читается под ``FOR UPDATE`` и держится до конца транзакции: два
    одновременных запроса с одним токеном иначе оба прочитали бы ACTIVE и создали
    бы два аккаунта на одно место. Второй дождётся коммита первого и увидит USED.

    Просроченный токен переводится в EXPIRED здесь же — чтобы отметка сохранилась,
    вызывающий должен закоммитить транзакцию, отказ он получает исключением.

    Raises:
        InviteRejection: любой отказ; `reason` содержит причину для журнала.
    """
    stmt = (
        select(InviteToken)
        .where(InviteToken.token_hash == _hash_token(plaintext_token))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    invite = await db.scalar(stmt)

    if invite is None:
        raise InviteRejection("unknown_token")

    if invite.status != InviteTokenStatus.ACTIVE:
        raise InviteRejection(f"status_{invite.status.value.lower()}")

    if invite.is_expired(datetime.now(UTC)):
        invite.status = InviteTokenStatus.EXPIRED
        await db.flush()
        raise InviteRejection("expired")

    if invite.email and invite.email.lower() != email.lower():
        raise InviteRejection("email_mismatch")

    return invite


async def consume_token(db: AsyncSession, invite: InviteToken, used_by_id: UUID) -> InviteToken:
    """Погасить приглашение, ранее заблокированное `lock_and_validate_token`.

    Отдельный шаг, потому что `used_by_id` появляется только после вставки
    пользователя, а проверять приглашение нужно до неё: иначе отказ откатывал бы
    уже созданную учётную запись.
    """
    invite.status = InviteTokenStatus.USED
    invite.used_at = datetime.now(UTC)
    invite.used_by_id = used_by_id
    await db.flush()
    return invite


async def list_invites(
    db: AsyncSession,
    company_id: UUID,
    *,
    status: InviteTokenStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[InviteToken], int]:
    """Приглашения компании, новые первыми. Хеши наружу не отдаются.

    Returns:
        (страница, всего).
    """
    conditions = [InviteToken.company_id == company_id]
    if status is not None:
        conditions.append(InviteToken.status == status)

    total = await db.scalar(select(func.count()).select_from(InviteToken).where(*conditions))

    stmt = select(InviteToken).where(*conditions).order_by(InviteToken.created_at.desc()).limit(limit).offset(offset)
    return list((await db.scalars(stmt)).all()), total or 0


async def revoke_invite_token(db: AsyncSession, invite_id: UUID, company_id: UUID) -> InviteToken:
    """Отозвать неиспользованное приглашение своей компании.

    company_id приходит из JWT и участвует в WHERE: администратор одной компании
    не может отозвать приглашение другой.

    Raises:
        InviteRejection: приглашение не найдено в этой компании либо уже погашено.
    """
    stmt = (
        select(InviteToken)
        .where(InviteToken.id == invite_id, InviteToken.company_id == company_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    invite = await db.scalar(stmt)

    if invite is None:
        raise InviteRejection("unknown_token")

    if invite.status != InviteTokenStatus.ACTIVE:
        raise InviteRejection(f"status_{invite.status.value.lower()}")

    invite.status = InviteTokenStatus.REVOKED
    await db.flush()
    return invite


async def expire_old_tokens(db: AsyncSession) -> int:
    """Перевести просроченные приглашения в EXPIRED.

    Одним UPDATE, без выгрузки строк в память: количество просроченных
    приглашений не ограничено сверху.

    Returns:
        Число обновлённых строк.
    """
    stmt = (
        update(InviteToken)
        .where(
            InviteToken.status == InviteTokenStatus.ACTIVE,
            InviteToken.expires_at <= datetime.now(UTC),
        )
        .values(status=InviteTokenStatus.EXPIRED)
        .execution_options(synchronize_session=False)
    )
    # rowcount объявлен на CursorResult, а не на Result: аннотация execute() шире
    # фактического типа для UPDATE, поэтому приводим явно.
    result: CursorResult[Any] = await db.execute(stmt)  # type: ignore[assignment]
    return result.rowcount or 0
