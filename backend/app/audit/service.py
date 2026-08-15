"""Запись журнала аудита (NEXUS30 §16).

Одна точка входа вместо конструирования AuditLog по месту: иначе часть событий
неизбежно теряет actor'а или арендатора, и журнал перестаёт быть пригодным для
разбора инцидентов.

Запись не коммитится здесь — она добавляется в текущую транзакцию вызывающего.
Так факт действия и его след в журнале появляются вместе либо не появляются вовсе.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.core.enums import AuditAction

__all__ = ["record_audit"]

# Ключи, которые нельзя писать в журнал даже если вызывающий их передал.
_FORBIDDEN_META_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "invite_token",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "api_key",
        "ticket",
    }
)


def _sanitize(meta: dict[str, Any] | None) -> dict[str, Any] | None:
    """Убрать секреты из метаданных.

    Журнал хранится долго и читается широким кругом администраторов, поэтому
    plaintext-токен, попавший туда по невнимательности, живёт дольше самого токена.
    """
    if not meta:
        return None
    return {key: value for key, value in meta.items() if key.lower() not in _FORBIDDEN_META_KEYS}


def record_audit(
    db: AsyncSession,
    *,
    action: AuditAction,
    actor_id: UUID | None = None,
    company_id: UUID | None = None,
    entity_type: str | None = None,
    entity_id: str | UUID | None = None,
    meta: dict[str, Any] | None = None,
) -> AuditLog:
    """Добавить запись в журнал в рамках текущей транзакции.

    Возвращает несохранённый объект: коммит — ответственность вызывающего сервиса,
    который и решает границы транзакции.
    """
    entry = AuditLog(
        action=action,
        actor_id=actor_id,
        company_id=company_id,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        meta=_sanitize(meta),
    )
    db.add(entry)
    return entry
