"""Event publisher: отправка событий в Redis pub/sub."""

import json
from typing import Any
from uuid import UUID

from redis.asyncio import Redis

__all__ = ["publish_event", "EventType"]


class EventType:
    """Типы событий для real-time обновлений."""

    APPLICATION_STATUS_CHANGED = "application.status_changed"
    PAYMENT_COMPLETED = "payment.completed"
    BENEFIT_UPDATED = "benefit.updated"
    BUDGET_UPDATED = "budget.updated"


async def publish_event(
    redis: Redis,
    user_id: UUID,
    event_type: str,
    data: dict[str, Any],
) -> None:
    """Публикует событие в Redis channel пользователя.

    Args:
        redis: Redis connection
        user_id: ID пользователя-получателя
        event_type: Тип события (см. EventType)
        data: Данные события
    """
    channel = f"user:{user_id}:events"
    payload = json.dumps({"event": event_type, "data": data})

    try:
        await redis.publish(channel, payload)
    except Exception as e:
        # Graceful degradation: логируем ошибку, но не падаем
        print(f"[Events] Failed to publish event: {e}")


async def publish_application_status_change(
    redis: Redis,
    user_id: UUID,
    application_id: UUID,
    old_status: str,
    new_status: str,
) -> None:
    """Публикует событие изменения статуса заявки."""
    await publish_event(
        redis,
        user_id,
        EventType.APPLICATION_STATUS_CHANGED,
        {
            "application_id": str(application_id),
            "old_status": old_status,
            "new_status": new_status,
        },
    )


async def publish_payment_completed(
    redis: Redis,
    user_id: UUID,
    payment_id: UUID,
    application_id: UUID,
    amount: float,
) -> None:
    """Публикует событие завершения платежа."""
    await publish_event(
        redis,
        user_id,
        EventType.PAYMENT_COMPLETED,
        {
            "payment_id": str(payment_id),
            "application_id": str(application_id),
            "amount": amount,
        },
    )
