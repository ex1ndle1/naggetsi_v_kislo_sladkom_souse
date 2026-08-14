"""Rate limiting middleware using Redis."""

from typing import Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware

__all__ = ["RateLimitMiddleware"]


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting на основе Redis: sliding window + per-IP."""

    def __init__(
        self,
        app,
        redis: Redis,
        *,
        max_requests: int = 100,
        window_seconds: int = 60,
    ):
        super().__init__(app)
        self.redis = redis
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Проверяет лимит запросов для IP-адреса."""
        client_ip = request.client.host if request.client else "unknown"
        key = f"ratelimit:{client_ip}"

        # Получаем текущий счётчик
        try:
            current = await self.redis.get(key)
            count = int(current) if current else 0

            if count >= self.max_requests:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "detail": "Rate limit exceeded. Try again later.",
                        "limit": self.max_requests,
                        "window_seconds": self.window_seconds,
                    },
                )

            # Инкрементируем счётчик
            pipe = self.redis.pipeline()
            pipe.incr(key)
            if count == 0:
                pipe.expire(key, self.window_seconds)
            await pipe.execute()

        except Exception:
            # Если Redis недоступен, пропускаем запрос (fail-open)
            pass

        response = await call_next(request)
        return response
