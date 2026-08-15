"""Redis: общий пул соединений и зависимость для роутеров.

Один пул на процесс. Создавать пул на каждый запрос нельзя: каждое соединение —
отдельный сокет, и под нагрузкой Redis упирается в лимит дескрипторов.
"""

from __future__ import annotations

from typing import Annotated, Any  # noqa: F401

from fastapi import Depends
from redis.asyncio import ConnectionPool
from redis.asyncio import Redis as AsyncRedis

from app.core.config import settings

__all__ = ["RedisClient", "RedisDep", "close_redis", "get_pool", "get_redis"]

#: Клиент Redis. Без параметра типа умышленно: в redis-py 8 класс generic только
#: для проверки типов, а ``Redis[Any]`` в аннотации, которую FastAPI вычисляет на
#: импорте, падает с TypeError.
RedisClient = AsyncRedis

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


async def get_redis() -> RedisClient:
    """Зависимость FastAPI: клиент поверх общего пула.

    Сам клиент не закрывается — закрытие лишь вернуло бы соединение в пул, а пул
    живёт до остановки приложения (``close_redis``).
    """
    client: AsyncRedis = AsyncRedis(connection_pool=get_pool())
    return client


async def close_redis() -> None:
    """Закрыть пул при остановке приложения."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


#: Готовая зависимость для роутеров: ``redis: RedisDep``.
RedisDep = Annotated[RedisClient, Depends(get_redis)]
