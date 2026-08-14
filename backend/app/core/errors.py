"""Единый формат ошибок API (ТЗ §44).

Наружу всегда уходит одна и та же форма::

    {"error": {"code": "APPLICATION_ALREADY_PAID", "message": "..."}}

Traceback пользователю не отдаётся никогда: непойманное исключение превращается
в INTERNAL_ERROR, а детали остаются в структурном логе.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Базовая ошибка домена. Подклассы задают code и http_status."""

    code: str = "INTERNAL_ERROR"
    http_status: int = 500
    message: str = "Внутренняя ошибка сервера"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.details = details
        super().__init__(self.message)

    def to_payload(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            error["details"] = self.details
        return {"error": error}


# --- 400 ---------------------------------------------------------------------
class ValidationFailed(AppError):
    code = "VALIDATION_ERROR"
    http_status = 400
    message = "Переданные данные не прошли валидацию"


class BadRequest(AppError):
    code = "BAD_REQUEST"
    http_status = 400
    message = "Некорректный запрос"


# --- 401 ---------------------------------------------------------------------
class Unauthenticated(AppError):
    code = "UNAUTHENTICATED"
    http_status = 401
    message = "Требуется авторизация"


class InvalidCredentials(AppError):
    code = "INVALID_CREDENTIALS"
    http_status = 401
    message = "Неверный email или пароль"


class InvalidToken(AppError):
    code = "INVALID_TOKEN"
    http_status = 401
    message = "Токен недействителен или истёк"


# --- 403 ---------------------------------------------------------------------
class Forbidden(AppError):
    code = "FORBIDDEN"
    http_status = 403
    message = "Недостаточно прав для выполнения операции"


class AccountBlocked(AppError):
    code = "ACCOUNT_BLOCKED"
    http_status = 403
    message = "Учётная запись заблокирована"


# --- 404 ---------------------------------------------------------------------
class NotFound(AppError):
    code = "NOT_FOUND"
    http_status = 404
    message = "Объект не найден"


# --- 409 ---------------------------------------------------------------------
class Conflict(AppError):
    code = "CONFLICT"
    http_status = 409
    message = "Конфликт состояния"


class AlreadyExists(AppError):
    code = "ALREADY_EXISTS"
    http_status = 409
    message = "Объект уже существует"


class InvalidTransition(Conflict):
    code = "INVALID_STATE_TRANSITION"
    message = "Такой переход статуса не разрешён"


class DuplicateRedemption(Conflict):
    code = "DUPLICATE_REDEMPTION"
    message = "Эта льгота уже получена и не допускает повторного получения"


class NoSeatsAvailable(Conflict):
    code = "NO_SEATS_AVAILABLE"
    message = "Нет свободных мест этого тарифа"


class UsageLimitExceeded(Conflict):
    code = "USAGE_LIMIT_EXCEEDED"
    message = "Достигнут лимит выдач по этой льготе"


class PromoCodeUnusable(Conflict):
    code = "PROMO_CODE_UNUSABLE"
    message = "Промокод недействителен"


class InviteTokenInvalid(Conflict):
    code = "INVITE_TOKEN_INVALID"
    message = "Приглашение недействительно"


class PlanNotEligible(Forbidden):
    code = "PLAN_NOT_ELIGIBLE"
    message = "Льгота недоступна вашему тарифу"


# --- 429 ---------------------------------------------------------------------
class RateLimited(AppError):
    code = "RATE_LIMITED"
    http_status = 429
    message = "Слишком много запросов, попробуйте позже"

    def __init__(self, retry_after: int, message: str | None = None) -> None:
        super().__init__(message, details={"retry_after": retry_after})
        self.retry_after = retry_after


# --- 503 ---------------------------------------------------------------------
class AIUnavailable(AppError):
    code = "AI_UNAVAILABLE"
    http_status = 503
    message = "AI-сервис временно недоступен. Остальные функции платформы работают"


__all__ = [
    "AIUnavailable",
    "AccountBlocked",
    "AlreadyExists",
    "AppError",
    "BadRequest",
    "Conflict",
    "DuplicateRedemption",
    "Forbidden",
    "InvalidCredentials",
    "InvalidToken",
    "InvalidTransition",
    "InviteTokenInvalid",
    "NoSeatsAvailable",
    "NotFound",
    "PlanNotEligible",
    "PromoCodeUnusable",
    "RateLimited",
    "Unauthenticated",
    "UsageLimitExceeded",
    "ValidationFailed",
]
