"""Application entry point: creates and configures FastAPI app.

Собирает роутеры, middleware, lifespan, exception handlers.
Не содержит бизнес-логику — только сборка.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import configure_logging

__all__ = ["create_app"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifespan context: setup при старте, cleanup при остановке."""
    # Startup
    configure_logging()
    app.state.request_count = 0

    # Инициализируем Redis для rate limiting
    from redis.asyncio import Redis
    app.state.redis = Redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )

    yield

    # Shutdown
    await app.state.redis.aclose()


def create_app() -> FastAPI:
    """Создаёт и настраивает FastAPI-приложение."""
    app = FastAPI(
        title=settings.project_name,
        version="1.0.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limiting (добавляется после lifespan, используем lazy loading)
    from app.core.rate_limit import RateLimitMiddleware
    @app.middleware("http")
    async def rate_limit_wrapper(request: Request, call_next):
        from app.core.rate_limit import RateLimitMiddleware
        middleware = RateLimitMiddleware(
            app,
            redis=app.state.redis,
            max_requests=settings.rate_limit_max_requests,
            window_seconds=settings.rate_limit_window_seconds,
        )
        return await middleware.dispatch(request, call_next)

    # Exception handlers
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    # Роутеры
    app.include_router(api_v1_router, prefix="/api/v1")

    return app


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Обработчик кастомных AppError: возвращает стандартный формат ошибки."""
    return JSONResponse(
        status_code=exc.http_status,
        content=exc.to_payload(),
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Обработчик FastAPI валидационных ошибок: переоформляем в стандартный формат."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": exc.errors(),
            }
        },
    )


app = create_app()
