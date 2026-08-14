"""Auth router: регистрация, логин, refresh токена."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import DbSession
from app.core.enums import UserRole
from app.core.errors import InvalidCredentials
from app.core.security import create_access_token, create_refresh_token, hash_password, verify_password
from app.users.models import User
from app.users.schemas import (
    RefreshTokenRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserRegisterRequest,
    db: DbSession,
) -> User:
    """Регистрация нового пользователя.

    Для EMPLOYEE требуется invite_token от COMPANY_ADMIN.
    Для MERCHANT требуется invite_token от PLATFORM_ADMIN.
    В demo-режиме создаём без проверки токена.
    """
    from app.core.errors import AlreadyExists

    # Проверка существования email
    stmt = select(User).where(User.email == payload.email)
    existing = await db.scalar(stmt)
    if existing:
        raise AlreadyExists(message="User with this email already exists")

    # TODO: валидация invite_token и извлечение company_id/merchant_id
    # Пока что создаём простого пользователя без привязки (для демо)
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        role=UserRole.EMPLOYEE,  # по умолчанию
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: UserLoginRequest,
    db: DbSession,
) -> TokenResponse:
    """Вход в систему: email + password → JWT токены."""
    stmt = select(User).where(User.email == payload.email)
    user = await db.scalar(stmt)

    if not user or not verify_password(payload.password, user.password_hash):
        raise InvalidCredentials()

    if not user.is_active:
        from app.core.errors import AccountBlocked

        raise AccountBlocked()

    access_token = create_access_token(
        user_id=user.id,
        role=user.role,
        company_id=user.company_id,
        merchant_id=user.merchant_id,
    )
    refresh_token, _jti = create_refresh_token(user_id=user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshTokenRequest,
    db: DbSession,
) -> TokenResponse:
    """Обновление access-токена через refresh-токен."""
    from app.core.errors import InvalidToken
    from app.core.security import decode_token

    try:
        token_data = decode_token(payload.refresh_token)
        user_id = token_data.get("sub")
        if not user_id or token_data.get("type") != "refresh":
            raise InvalidToken()
    except Exception:
        raise InvalidToken(message="Invalid or expired refresh token")

    # Проверяем, что пользователь существует и активен
    stmt = select(User).where(User.id == user_id)
    user = await db.scalar(stmt)
    if not user or not user.is_active:
        raise InvalidToken(message="User not found or inactive")

    access_token = create_access_token(
        user_id=user.id,
        role=user.role,
        company_id=user.company_id,
        merchant_id=user.merchant_id,
    )
    new_refresh_token, _jti = create_refresh_token(user_id=user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
    )
