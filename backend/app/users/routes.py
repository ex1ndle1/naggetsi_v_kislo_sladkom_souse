"""Аутентификация: регистрация по приглашению, вход, ротация токенов, выход.

Регистрация публична по URL, но не по существу: без действующего приглашения
аккаунт не создаётся, а компания и тариф берутся из приглашения (NEXUS30 §5).
"""

from typing import Any
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, status
from structlog import get_logger

from app.audit.service import record_audit
from app.core.config import settings
from app.core.deps import CurrentUser, DbSession
from app.core.enums import AuditAction
from app.core.errors import InvalidToken
from app.core.rate_limit import rate_limit
from app.core.redis import RedisDep
from app.core.security import decode_token
from app.invites.service import InviteRejection
from app.users.models import User
from app.users.schemas import (
    LogoutRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.users.service import (
    authenticate,
    get_user_by_id,
    is_refresh_revoked,
    issue_token_pair,
    register_by_invite,
    revoke_refresh_jti,
)

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация сотрудника по приглашению",
    dependencies=[Depends(rate_limit("register", settings.rate_limit_register))],
)
async def register(payload: UserRegisterRequest, db: DbSession) -> User:
    """Создать сотрудника по одноразовому приглашению.

    Возвращает 409 при занятом email, недействительном приглашении или отсутствии
    свободных мест. Причина отказа по приглашению не детализируется: иначе перебором
    можно было бы отличить существующий токен от несуществующего.
    """
    try:
        user = await register_by_invite(
            db,
            email=payload.email,
            password=payload.password,
            first_name=payload.first_name,
            last_name=payload.last_name,
            invite_token=payload.invite_token,
        )
    except InviteRejection as e:
        # Коммит сохраняет перевод просроченного токена в EXPIRED, сделанный при
        # проверке. Пользователь на этот момент ещё не создан.
        await db.commit()
        logger.info("invite_rejected", reason=e.reason)
        raise

    await db.commit()
    await db.refresh(user)
    return user


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Вход",
    # Лимит по адресу и логину: без него перебор пароля ограничен только сетью.
    dependencies=[Depends(rate_limit("login", settings.rate_limit_login))],
)
async def login(payload: UserLoginRequest, db: DbSession) -> TokenResponse:
    """Выдать пару токенов по email и паролю.

    Попытка входа (успешная и неуспешная) фиксируется в журнале, поэтому коммит
    выполняется и на пути отказа.
    """
    try:
        user = await authenticate(db, email=payload.email, password=payload.password)
    except Exception:
        await db.commit()
        raise

    access, refresh, _jti = issue_token_pair(user)
    await db.commit()

    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse, summary="Обновление токенов")
async def refresh_tokens(payload: RefreshTokenRequest, db: DbSession, redis: RedisDep) -> TokenResponse:
    """Обменять refresh-токен на новую пару с ротацией.

    Предъявленный токен сразу попадает в денилист: повторное использование того же
    refresh-токена (признак утечки) отклоняется.
    """
    claims = _decode_refresh(payload.refresh_token)
    jti = claims["jti"]

    if await is_refresh_revoked(redis, jti):
        logger.warning("refresh_token_reuse", jti=jti, sub=claims.get("sub"))
        raise InvalidToken(message="Refresh token has been revoked")

    user = await get_user_by_id(db, claims["user_id"])
    if user is None or not user.is_active:
        raise InvalidToken(message="User not found or inactive")

    access, new_refresh, _new_jti = issue_token_pair(user)
    await revoke_refresh_jti(redis, jti, claims.get("exp"))

    return TokenResponse(access_token=access, refresh_token=new_refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Выход")
async def logout(payload: LogoutRequest, user: CurrentUser, db: DbSession, redis: RedisDep) -> None:
    """Отозвать предъявленный refresh-токен.

    Access-токен продолжает действовать до истечения (не более 15 минут): проверка
    денилиста на каждом запросе стоила бы обращения в Redis ради этого окна.

    Чужой или испорченный токен не считается ошибкой выхода — сессия всё равно
    завершается на клиенте, поэтому ответ одинаков.
    """
    try:
        claims = _decode_refresh(payload.refresh_token)
    except InvalidToken:
        logger.info("logout_with_invalid_token", user_id=str(user.user_id))
    else:
        if claims["user_id"] == user.user_id:
            await revoke_refresh_jti(redis, claims["jti"], claims.get("exp"))
        else:
            logger.warning(
                "logout_token_owner_mismatch",
                user_id=str(user.user_id),
                token_sub=str(claims["user_id"]),
            )

    record_audit(
        db,
        action=AuditAction.USER_LOGOUT,
        actor_id=user.user_id,
        company_id=user.company_id,
        entity_type="user",
        entity_id=str(user.user_id),
    )
    await db.commit()


def _decode_refresh(token: str) -> dict[str, Any]:
    """Разобрать refresh-токен и проверить обязательные claims.

    Returns:
        Клеймы с добавленным `user_id: UUID`.

    Raises:
        InvalidToken: подпись, срок, тип или состав claims не подходят.
    """
    try:
        claims = decode_token(token)
    except jwt.InvalidTokenError as e:
        raise InvalidToken(message="Invalid or expired refresh token") from e

    if claims.get("type") != "refresh":
        raise InvalidToken(message="Expected a refresh token")

    subject, jti = claims.get("sub"), claims.get("jti")
    if not subject or not jti:
        raise InvalidToken(message="Refresh token missing required claims")

    try:
        claims["user_id"] = UUID(subject)
    except ValueError as e:
        raise InvalidToken(message="Refresh token has malformed subject") from e

    return claims
