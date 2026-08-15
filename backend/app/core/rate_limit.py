"""Ограничение частоты запросов (ТЗ §23, §46).

Два уровня:

* ``RateLimitMiddleware`` — грубый лимит на IP для всего API. Отсекает флуд до
  того, как запрос дойдёт до БД.
* ``rate_limit(bucket, limit)`` — зависимость на конкретный эндпоинт. Считает по
  пользователю, если он аутентифицирован, иначе по IP: иначе один сотрудник за
  корпоративным NAT расходовал бы лимит на всю компанию.

Счётчик — фиксированное окно на Redis (``INCR`` + ``EXPIRE``). Скользящее окно
здесь не нужно: худший случай на границе окна — вдвое больше запросов за короткий
интервал, а не обход лимита.

Недоступность Redis не блокирует API (fail-open): лимит защищает от перегрузки,
а не управляет доступом, и падение кэша не должно останавливать выдачу льгот.
Событие пишется в лог.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import jwt
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware
from structlog import get_logger

from app.core.errors import RateLimited
from app.core.redis import RedisClient, get_redis

__all__ = ["RateLimitMiddleware", "rate_limit"]

logger = get_logger(__name__)

#: Пути вне лимитов: проверки живости и документация. Healthcheck Docker'а
#: обращается к /health каждые 10 секунд, и попадание под лимит выглядело бы
#: как падение сервиса.
_EXEMPT_PATHS = frozenset(
    {
        "/api/v1/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/favicon.ico",
    }
)


def _client_ip(request: Request) -> str:
    """IP клиента с учётом обратного прокси.

    Приложение работает за nginx, поэтому ``request.client.host`` — адрес прокси,
    одинаковый для всех клиентов. Берём первый адрес из X-Forwarded-For; заголовок
    подделывается клиентом, но nginx его перезаписывает.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _hit(redis: RedisClient, key: str, limit: int, window: int) -> int | None:
    """Учесть запрос.

    Returns:
        Секунды до сброса, если лимит превышен; None, если запрос разрешён.
    """
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.ttl(key)
    count, ttl = await pipe.execute()

    if count == 1 or ttl < 0:
        # Начало окна — или ключ остался без TTL после сбоя: срок надо выставить,
        # иначе счётчик не сбросится никогда.
        await redis.expire(key, window)
        ttl = window

    if count > limit:
        return max(int(ttl), 1)
    return None


def _too_many(retry_after: int) -> JSONResponse:
    """Ответ 429 в общем формате ошибок (§44).

    Собирается вручную: исключение, выброшенное из middleware, до обработчиков
    приложения не доходит.
    """
    error = RateLimited(retry_after=retry_after)
    return JSONResponse(
        status_code=error.http_status,
        content=error.to_payload(),
        headers={"Retry-After": str(retry_after)},
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Грубый лимит на IP для всего API."""

    def __init__(
        self,
        app: Any,
        *,
        max_requests: int = 100,
        window_seconds: int = 60,
        enabled: bool = True,
    ) -> None:
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if not self.enabled or request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        key = f"ratelimit:ip:{_client_ip(request)}"

        try:
            redis = await get_redis()
            retry_after = await _hit(redis, key, self.max_requests, self.window_seconds)
        except (RedisError, OSError) as e:
            logger.warning("rate_limit_unavailable", scope="global", error=str(e))
            return await call_next(request)

        if retry_after is not None:
            logger.info("rate_limited", scope="global", path=request.url.path)
            return _too_many(retry_after)

        return await call_next(request)


def rate_limit(bucket: str, limit: int, window_seconds: int = 60) -> Callable[[Request], Awaitable[None]]:
    """Зависимость с лимитом на конкретный эндпоинт::

        @router.post("/login", dependencies=[Depends(rate_limit("login", 10))])

    Raises:
        RateLimited: лимит исчерпан; ``retry_after`` — секунды до сброса.
    """

    async def _check(request: Request) -> None:
        identity = _identity(request)
        key = f"ratelimit:{bucket}:{identity}"

        try:
            redis = await get_redis()
            retry_after = await _hit(redis, key, limit, window_seconds)
        except (RedisError, OSError) as e:
            logger.warning("rate_limit_unavailable", scope=bucket, error=str(e))
            return

        if retry_after is not None:
            logger.info("rate_limited", scope=bucket, identity=identity)
            raise RateLimited(retry_after=retry_after)

    return _check


def _identity(request: Request) -> str:
    """Ключ счётчика: пользователь, если токен предъявлен, иначе IP.

    Из токена берётся только ``sub``, без проверки подписи: это ключ счётчика, а
    не решение о доступе. Подделав его, клиент получит свой отдельный счётчик
    того же размера — неподписанный токен всё равно не пройдёт аутентификацию.
    """
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        try:
            claims = jwt.decode(
                authorization[len("Bearer ") :],
                options={"verify_signature": False, "verify_exp": False},
            )
        except jwt.InvalidTokenError:
            pass
        else:
            subject = claims.get("sub")
            if subject:
                return f"user:{subject}"

    return f"ip:{_client_ip(request)}"
