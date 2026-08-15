"""Схемы аутентификации и профиля."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.enums import UserPlan, UserRole

__all__ = [
    "ChangePasswordRequest",
    "LogoutRequest",
    "RefreshTokenRequest",
    "TokenResponse",
    "UserLoginRequest",
    "UserRegisterRequest",
    "UserResponse",
    "UserUpdateRequest",
]


# ---------------------------------------------------------------------------
# Аутентификация
# ---------------------------------------------------------------------------
class UserRegisterRequest(BaseModel):
    """Регистрация сотрудника по приглашению (NEXUS30 §5).

    Ни company_id, ни plan, ни role здесь не принимаются: они определяются
    приглашением. Поле, которого нет в схеме, невозможно подделать.
    """

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=255)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    invite_token: str = Field(
        ...,
        min_length=32,
        max_length=128,
        description="Одноразовый токен приглашения от администратора компании",
    )


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=255)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    """Выход: отзывается конкретный refresh-токен, а не все сессии."""

    refresh_token: str


# ---------------------------------------------------------------------------
# Профиль
# ---------------------------------------------------------------------------
class UserResponse(BaseModel):
    """Публичное представление пользователя. Хеш пароля не сериализуется."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    first_name: str
    last_name: str
    role: UserRole
    plan: UserPlan | None
    is_active: bool
    company_id: UUID | None
    merchant_id: UUID | None
    created_at: datetime
    updated_at: datetime


class UserUpdateRequest(BaseModel):
    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, min_length=1, max_length=100)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=255)
    new_password: str = Field(..., min_length=8, max_length=255)
