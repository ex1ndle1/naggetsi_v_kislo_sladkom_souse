"""Redis: пул соединений и утилиты для работы с кэшем, rate limiting и pub/sub."""

from __future__ import annotations

from typing import Any

from redis.asyncio import ConnectionPool, Redis as AsyncRedis

from app.core.config import settings

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    """Единый пул соединений для всего приложения."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=50,
        )
    return _pool


async def get_redis() -> AsyncRedis[Any]:
    """FastAPI-зависимость: Redis-клиент из общего пула."""
    pool = get_pool()
    client: AsyncRedis[Any] = AsyncRedis(connection_pool=pool)
    return client


async def close_redis() -> None:
    """Закрывает пул при shutdown приложения."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


__all__ = ["close_redis", "get_pool", "get_redis"]
