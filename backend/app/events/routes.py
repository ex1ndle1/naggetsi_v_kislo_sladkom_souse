"""SSE-поток на одноразовых тикетах (NEXUS30 §21).

Браузерный ``EventSource`` не умеет отправлять заголовки, поэтому Bearer-токен до
потока не доходит. Класть access-токен в query-строку тоже нельзя: URL попадает в
логи nginx, в history браузера и в Referer.

Решение: клиент обменивает Bearer на непрозрачный тикет (TTL 60 с, одноразовый) и
подключается с ним. Тикет удаляется в момент использования, поэтому перехваченный
URL уже бесполезен.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel
from redis.exceptions import RedisError
from sse_starlette.sse import EventSourceResponse

from app.core.config import settings
from app.core.deps import CurrentUser
from app.core.errors import Unauthenticated
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.events.publisher import channel_for

router = APIRouter(prefix="/events", tags=["events"])

__all__ = ["router"]

logger = get_logger(__name__)

_TICKET_PREFIX = "sse:ticket:"
# Интервал heartbeat. Нужен, чтобы прокси не закрыл простаивающее соединение и
# чтобы клиент замечал разрыв, а не висел в мнимо живом потоке.
_HEARTBEAT_SECONDS = 25


class TicketResponse(BaseModel):
    ticket: str
    expires_in_seconds: int


@router.post("/ticket", response_model=TicketResponse)
async def issue_ticket(user: CurrentUser) -> TicketResponse:
    """Выдать одноразовый тикет для подключения к потоку."""
    ticket = secrets.token_urlsafe(32)
    redis = await get_redis()
    await redis.set(
        f"{_TICKET_PREFIX}{ticket}",
        str(user.user_id),
        ex=settings.sse_ticket_ttl_seconds,
    )
    return TicketResponse(
        ticket=ticket,
        expires_in_seconds=settings.sse_ticket_ttl_seconds,
    )


async def _consume_ticket(ticket: str) -> UUID:
    """Обменять тикет на идентификатор пользователя, удалив его.

    ``GETDEL`` атомарен, поэтому два одновременных подключения с одним тикетом не
    могут оба оказаться успешными.
    """
    redis = await get_redis()
    raw = await redis.getdel(f"{_TICKET_PREFIX}{ticket}")
    if not raw:
        raise Unauthenticated(message="Invalid or expired SSE ticket")
    try:
        return UUID(raw if isinstance(raw, str) else raw.decode())
    except (ValueError, AttributeError) as exc:
        raise Unauthenticated(message="Malformed SSE ticket") from exc


async def _event_stream(request: Request, user_id: UUID) -> AsyncIterator[dict[str, Any]]:
    """Транслировать события персонального канала пользователя."""
    redis = await get_redis()
    channel = channel_for(user_id)
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)

    try:
        while True:
            if await request.is_disconnected():
                break

            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True),
                    timeout=_HEARTBEAT_SECONDS,
                )
            except TimeoutError:
                yield {"event": "ping", "data": "keepalive"}
                continue
            except (RedisError, OSError) as exc:
                logger.warning("sse_stream_error", error=str(exc))
                break

            if not message or message.get("type") != "message":
                continue

            raw = message["data"]
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")

            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("sse_malformed_payload", channel=channel)
                continue

            yield {
                "event": parsed.get("event", "message"),
                "data": json.dumps(parsed.get("data", {})),
            }
    finally:
        # Отписка обязательна: иначе соединение к Redis остаётся занятым после
        # ухода клиента и пул исчерпывается.
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()  # type: ignore[no-untyped-call]


@router.get("/stream")
async def sse_stream(
    request: Request,
    ticket: str = Query(min_length=16, max_length=128),
) -> EventSourceResponse:
    """Подключиться к потоку событий по тикету.

    Bearer-заголовок здесь не проверяется: аутентификацию несёт сам тикет,
    полученный аутентифицированным вызовом ``POST /events/ticket``.
    """
    user_id = await _consume_ticket(ticket)
    return EventSourceResponse(
        _event_stream(request, user_id),
        media_type="text/event-stream",
        ping=_HEARTBEAT_SECONDS,
    )
