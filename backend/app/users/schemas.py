"""Pydantic-схемы для аутентификации и работы с пользователями."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.core.enums import UserRole

__all__ = [
    "UserRegisterRequest",
    "UserLoginRequest",
    "TokenResponse",
    "RefreshTokenRequest",
    "UserResponse",
    "UserUpdateRequest",
    "ChangePasswordRequest",
]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class UserRegisterRequest(BaseModel):
    """Регистрация нового пользователя (только EMPLOYEE/MERCHANT через инвайт)."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=255)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    invite_token: str | None = Field(
        None, description="Токен приглашения для привязки к компании/мерчанту"
    )


class UserLoginRequest(BaseModel):
    """Вход в систему."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """JWT токены: access + refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    """Обновление access-токена через refresh."""

    refresh_token: str


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------
class UserResponse(BaseModel):
    """Публичное представление пользователя."""

    id: UUID
    email: str
    first_name: str
    last_name: str
    role: UserRole
    is_active: bool
    company_id: UUID | None
    merchant_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    """Обновление профиля пользователя."""

    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, min_length=1, max_length=100)


class ChangePasswordRequest(BaseModel):
    """Смена пароля."""

    old_password: str
    new_password: str = Field(..., min_length=8, max_length=255)
