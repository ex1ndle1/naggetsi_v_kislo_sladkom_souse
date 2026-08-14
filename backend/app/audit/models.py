"""Модель AuditLog — журнал критических действий (ТЗ §12).

Колонка metadata конфликтует с Base.metadata — маппится как `meta` с именем в БД `metadata`.
Audit log нельзя удалять обычным пользователям (только PLATFORM_ADMIN через специальный эндпоинт,
если потребуется GDPR-compliant удаление).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import Enum as SAEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.enums import AuditAction

if TYPE_CHECKING:
    from app.companies.models import Company
    from app.users.models import User


class AuditLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"

    actor_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor: Mapped[User | None] = relationship()

    company_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    company: Mapped[Company | None] = relationship()

    action: Mapped[AuditAction] = mapped_column(
        SAEnum(AuditAction, name="audit_action"), nullable=False, index=True
    )
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    entity_id: Mapped[UUID | None] = mapped_column(String(255), nullable=True, index=True)

    # Конфликт с Base.metadata → маппим как meta, имя колонки остаётся metadata.
    meta: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<AuditLog action={self.action} actor={self.actor_id} entity={self.entity_type}:{self.entity_id}>"


__all__ = ["AuditLog"]
