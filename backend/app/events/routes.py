"""Real-time events: SSE endpoint + Redis pub/sub для обновлений статусов."""

import asyncio
import json

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.core.deps import CurrentUser

router = APIRouter(prefix="/events", tags=["events"])


async def event_stream(user_id: str, redis):
    """SSE stream для real-time обновлений статусов заявок.

    Подписывается на Redis channel для уведомлений конкретного пользователя.
    """
    channel_name = f"user:{user_id}:events"
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel_name)

    try:
        # Слушаем события из Redis
        while True:
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True),
                    timeout=30
                )

                if message and message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")

                    try:
                        event_data = json.loads(data)
                        yield {
                            "event": event_data.get("event", "update"),
                            "data": json.dumps(event_data.get("data", {})),
                        }
                    except json.JSONDecodeError:
                        # Если не JSON, отправляем как есть
                        yield {"event": "message", "data": data}

            except asyncio.TimeoutError:
                # Отправляем heartbeat каждые 30 секунд
                yield {"event": "ping", "data": "heartbeat"}

    except asyncio.CancelledError:
        await pubsub.unsubscribe(channel_name)
        await pubsub.close()
        raise


@router.get("/stream")
async def sse_stream(
    request: Request,
    user: CurrentUser,
) -> EventSourceResponse:
    """SSE endpoint для получения real-time обновлений.

    Клиент подключается к `/api/v1/events/stream` и получает события:
    - application.status_changed
    - payment.completed
    - benefit.updated
    """
    # Получаем Redis из app.state
    redis = request.app.state.redis

    return EventSourceResponse(
        event_stream(str(user.user_id), redis),
        media_type="text/event-stream",
    )
