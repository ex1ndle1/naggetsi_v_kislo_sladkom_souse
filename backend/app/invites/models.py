"""Invite token — единственный путь появления employee-аккаунта (NEXUS30 §5, §6).

Публичной регистрации нет: company_id и plan берутся из токена, а не из тела запроса,
поэтому пользователь не может выбрать себе чужой tenant или PRO-план.

Токен: одноразовый, с expiration, привязан к company_id + plan.
В БД хранится только SHA-256 хеш — plaintext отдаётся создателю один раз.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.enums import InviteTokenStatus, UserPlan

if TYPE_CHECKING:
    from app.companies.models import Company
    from app.users.models import User


class InviteToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "invite_tokens"

    # SHA-256 хеш токена: утечка БД не даёт возможности зарегистрироваться.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company: Mapped[Company] = relationship(back_populates="invite_tokens")

    plan: Mapped[UserPlan] = mapped_column(
        SAEnum(UserPlan, name="user_plan"), nullable=False
    )

    # Опционально фиксирует адрес: приглашение нельзя использовать с другим email.
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)

    status: Mapped[InviteTokenStatus] = mapped_column(
        SAEnum(InviteTokenStatus, name="invite_token_status"),
        nullable=False,
        default=InviteTokenStatus.ACTIVE,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_id])

    used_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    used_by: Mapped[User | None] = relationship(foreign_keys=[used_by_id])

    def is_expired(self, now: datetime) -> bool:
        return self.expires_at <= now

    def __repr__(self) -> str:
        return f"<InviteToken company={self.company_id} plan={self.plan} status={self.status}>"


__all__ = ["InviteToken"]
