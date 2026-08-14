"""Events system for real-time updates via SSE + Redis pub/sub."""

from typing import Any

from redis.asyncio import Redis

__all__ = ["publish_event"]


async def publish_event(
    redis: Redis,
    *,
    tenant_id: str,
    channel: str,
    event_type: str,
    data: dict[str, Any],
) -> None:
    """Публикует событие в Redis pub/sub для real-time обновлений.

    Args:
        redis: Redis-клиент
        tenant_id: company_id или merchant_id
        channel: канал событий (например, 'applications', 'payments')
        event_type: тип события (например, 'status_changed', 'created')
        data: полезная нагрузка события
    """
    import json

    topic = f"tenant:{tenant_id}:{channel}"
    payload = json.dumps({"type": event_type, "data": data})

    await redis.publish(topic, payload)
