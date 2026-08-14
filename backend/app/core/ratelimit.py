"""Rate limiting через Redis sliding window (ТЗ §11.6, §26).

Каждая защищённая группа эндпоинтов (login, register, payments, ai, applications)
получает свою квоту запросов за окно времени. Превышение → 429 с retry_after.
"""

from __future__ import annotations

import time

from redis.asyncio import Redis

from app.core.config import settings
from app.core.errors import RateLimited


async def check_rate_limit(
    redis: Redis,  # type: ignore[type-arg]
    identifier: str,
    max_requests: int,
    window_seconds: int,
) -> None:
    """Проверяет лимит методом sliding window: хранит timestamp каждого запроса.

    Args:
        redis: Redis-клиент.
        identifier: Уникальный ключ (например, "login:user_id").
        max_requests: Максимум запросов за окно.
        window_seconds: Длина окна в секундах.

    Raises:
        RateLimited: Если квота исчерпана.
    """
    now = time.time()
    window_start = now - window_seconds
    key = f"rate_limit:{identifier}"

    # Очищаем запросы за пределами окна.
    await redis.zremrangebyscore(key, "-inf", window_start)
    # Считаем оставшиеся.
    count = await redis.zcard(key)
    if count >= max_requests:
        # Находим самый старый запрос в окне, чтобы сказать retry_after.
        oldest_list = await redis.zrange(key, 0, 0, withscores=True)
        if oldest_list:
            oldest_ts = oldest_list[0][1]
            retry_after = int(oldest_ts + window_seconds - now) + 1
        else:
            retry_after = window_seconds
        raise RateLimited(retry_after=retry_after)

    # Добавляем текущий запрос в окно.
    await redis.zadd(key, {str(now): now})
    await redis.expire(key, window_seconds)


def make_rate_limit_key(category: str, user_id: str) -> str:
    """Формирует идентификатор для rate-limiting: category:user_id."""
    return f"{category}:{user_id}"


__all__ = ["check_rate_limit", "make_rate_limit_key"]
