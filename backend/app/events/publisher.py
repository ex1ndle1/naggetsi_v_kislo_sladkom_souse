"""Публикация событий в Redis pub/sub (NEXUS30 §21).

Каналы персональные: ``user:{id}:events``. Широковещательных каналов нет — иначе
подписчик получал бы события чужой компании.

Публикация вызывается только после коммита. Redis здесь — доставка уведомлений, а не
хранилище: его недоступность логируется и не влияет на уже сохранённые данные, иначе
падение кэша откатывало бы выданный промокод.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from redis.exceptions import RedisError

from app.core.enums import UserPlan
from app.core.logging import get_logger
from app.core.redis import get_redis

__all__ = [
    "EventType",
    "publish_benefit_updated",
    "publish_event",
    "publish_plan_changed",
    "publish_promo_issued",
    "publish_promo_redeemed",
]

logger = get_logger(__name__)


class EventType:
    """Имена событий NEXUS30. Фронтенд подписывается на них по строке."""

    PROMO_ISSUED = "promo.issued"
    PROMO_REDEEMED = "promo.redeemed"
    PLAN_CHANGED = "plan.changed"
    BENEFIT_UPDATED = "benefit.updated"


def channel_for(user_id: UUID) -> str:
    return f"user:{user_id}:events"


async def publish_event(user_id: UUID, event_type: str, data: dict[str, Any]) -> bool:
    """Отправить событие в персональный канал пользователя.

    Возвращает False, если Redis недоступен: вызывающему это может быть интересно
    для метрик, но обрабатывать отказ он не обязан.
    """
    payload = json.dumps({"event": event_type, "data": data})
    try:
        redis = await get_redis()
        await redis.publish(channel_for(user_id), payload)
        return True
    except (RedisError, OSError) as exc:
        # Ключ event_type, а не event: первый позиционный аргумент structlog уже
        # называется event, и передача одноимённого kwarg — конфликт аргументов.
        logger.warning("event_publish_failed", event_type=event_type, error=str(exc))
        return False


async def publish_promo_issued(
    *,
    user_id: UUID,
    promo_code: str,
    benefit_id: UUID,
    expires_at: datetime,
) -> bool:
    """Промокод выдан сотруднику.

    Код входит в полезную нагрузку: канал персональный, а сотрудник и так видит
    его в ответе на запрос выдачи.
    """
    return await publish_event(
        user_id,
        EventType.PROMO_ISSUED,
        {
            "promo_code": promo_code,
            "benefit_id": str(benefit_id),
            "expires_at": expires_at.isoformat(),
        },
    )


async def publish_promo_redeemed(
    *,
    user_id: UUID,
    promo_code: str,
    benefit_id: UUID,
    redeemed_at: datetime,
) -> bool:
    """Мерчант подтвердил использование кода — уведомляем владельца кода."""
    return await publish_event(
        user_id,
        EventType.PROMO_REDEEMED,
        {
            "promo_code": promo_code,
            "benefit_id": str(benefit_id),
            "redeemed_at": redeemed_at.isoformat(),
        },
    )


async def publish_plan_changed(
    *,
    user_id: UUID,
    old_plan: UserPlan | None,
    new_plan: UserPlan,
) -> bool:
    """Тариф сотрудника изменён администратором компании.

    Сотруднику это важно немедленно: каталог и скидки меняются, а access-токен с
    прежним тарифом живёт до 15 минут.
    """
    return await publish_event(
        user_id,
        EventType.PLAN_CHANGED,
        {
            "old_plan": old_plan.value if old_plan else None,
            "new_plan": new_plan.value,
        },
    )


async def publish_benefit_updated(*, user_id: UUID, benefit_id: UUID, action: str) -> bool:
    """Льгота создана, изменена или деактивирована."""
    return await publish_event(
        user_id,
        EventType.BENEFIT_UPDATED,
        {"benefit_id": str(benefit_id), "action": action},
    )
