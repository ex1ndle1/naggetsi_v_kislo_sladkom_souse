"""Структурное JSON-логирование (ТЗ §45).

Логируем: запросы, аутентификацию, платёжные события, отказы anti-fraud, ошибки AI и БД.
Не логируем: пароли, JWT-секреты, Click-секреты, персональные данные.
За это отвечает ``_redact_processor`` — он вычищает чувствительные ключи на выходе,
чтобы случайно переданное значение не попало в лог.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.core.config import settings

_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "current_password",
        "new_password",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "jwt_secret",
        "secret",
        "secret_key",
        "click_secret_key",
        "sign_string",
        "api_key",
        "ollama_api_key",
        "card_number",
    }
)

_REDACTED = "[redacted]"


def _redact_processor(
    _logger: Any, _method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Заменяет значения чувствительных ключей на маркер."""
    for key in list(event_dict):
        if key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = _REDACTED
    return event_dict


def configure_logging() -> None:
    """Настраивает stdlib logging и structlog на единый JSON-вывод."""
    level = getattr(logging, settings.log_level, logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
        force=True,
    )
    # uvicorn пишет свои логи через stdlib — приводим их к тому же уровню.
    for noisy in ("uvicorn.error", "uvicorn.access"):
        logging.getLogger(noisy).handlers = []
        logging.getLogger(noisy).propagate = True
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _redact_processor,
    ]
    if settings.app_env == "development":
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger


__all__ = ["configure_logging", "get_logger"]
