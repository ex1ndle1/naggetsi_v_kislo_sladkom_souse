"""Точка входа: сборка FastAPI-приложения.

Бизнес-логики здесь нет — только роутеры, middleware, lifespan и обработчики
ошибок. Наружу всегда уходит единый формат ошибки (§44): traceback не попадает
в ответ ни при какой ветке.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.database import dispose_engine
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger
from app.core.rate_limit import RateLimitMiddleware
from app.core.redis import close_redis

__all__ = ["app", "create_app"]

logger = get_logger(__name__)

#: Заголовок сквозного идентификатора запроса. Клиент может передать свой —
#: тогда его значение попадёт во все записи лога этого запроса.
_REQUEST_ID_HEADER = "X-Request-ID"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Настройка логов при старте, закрытие пулов при остановке.

    Пулы Redis и БД закрываются явно: иначе при перезапуске контейнера остаются
    висящие соединения, и PostgreSQL упирается в ``max_connections``.
    """
    configure_logging()
    logger.info(
        "app_startup",
        env=settings.app_env,
        ai_enabled=settings.ai_enabled,
        ollama_model=settings.ollama_model,
    )

    yield

    await close_redis()
    await dispose_engine()
    logger.info("app_shutdown")


def create_app() -> FastAPI:
    """Собрать приложение.

    Документация открыта только при ``debug``: в production схема API — лишняя
    подсказка о внутреннем устройстве.
    """
    app = FastAPI(
        title=settings.project_name,
        version="1.0.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[_REQUEST_ID_HEADER, "Retry-After"],
    )

    # Лимит частоты — один экземпляр на приложение. Redis берётся из общего пула
    # внутри middleware, поэтому зависимости от порядка с lifespan нет.
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=settings.rate_limit_max_requests,
        window_seconds=settings.rate_limit_window_seconds,
        enabled=settings.rate_limit_enabled,
    )

    app.middleware("http")(request_context_middleware)

    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)

    app.include_router(api_v1_router, prefix="/api/v1")

    return app


async def request_context_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Привязать request_id, метод и путь ко всем записям лога этого запроса.

    Без этого записи разных одновременных запросов невозможно разделить: в async
    -приложении они перемешаны в одном потоке вывода.
    """
    request_id = request.headers.get(_REQUEST_ID_HEADER) or str(uuid.uuid4())

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
    )

    response = await call_next(request)
    response.headers[_REQUEST_ID_HEADER] = request_id
    return response


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    """Ошибки домена: код и сообщение заданы самим исключением."""
    headers = {}
    retry_after = getattr(exc, "retry_after", None)
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)

    logger.info("app_error", code=exc.code, status=exc.http_status)
    return JSONResponse(status_code=exc.http_status, content=exc.to_payload(), headers=headers)


async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """Ошибки валидации FastAPI — в тот же формат, что и остальные."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                # jsonable_encoder не нужен: errors() уже сериализуем, кроме
                # ctx с исключениями — их FastAPI приводит к строкам сам.
                "details": {"errors": exc.errors()},
            }
        },
    )


async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Непойманное исключение: 500 без подробностей.

    Traceback уходит в лог, наружу — только INTERNAL_ERROR: сообщение об ошибке
    БД или отсутствующем атрибуте описывает внутреннее устройство приложения.
    """
    logger.exception("unhandled_exception", error_type=type(exc).__name__)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Внутренняя ошибка сервера",
            }
        },
    )


app = create_app()
