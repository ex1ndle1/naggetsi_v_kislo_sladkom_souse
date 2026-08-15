"""Фильтрация каталога по плану пользователя (NEXUS30 §8).

Это не косметика для UI: если льгота доступна только PRO, пользователь STANDARD
не должен получить её ни через список, ни через detail-эндпоинт, ни через AI.
Поэтому фильтр живёт в SQL, а не в сериализаторе.

Правила:
  * benefit виден, если существует BenefitPlanOffer(plan=user.plan, is_available=true);
  * benefit активен и находится внутри valid_from..valid_until;
  * merchant активен;
  * company_id benefit'а либо NULL (платформенная льгота), либо равен компании пользователя.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import selectinload

from app.benefits.models import Benefit
from app.benefits.plan_offers import BenefitPlanOffer
from app.core.enums import MerchantStatus, UserPlan
from app.merchants.models import Merchant

__all__ = ["visible_benefits_query", "discount_for_plan"]


def visible_benefits_query(
    plan: UserPlan,
    company_id: UUID,
    now: datetime | None = None,
) -> Select[tuple[Benefit]]:
    """Запрос каталога, отфильтрованный по плану и tenant'у.

    Возвращает Select, чтобы вызывающий код мог добавить свои условия
    (категорию, поиск, пагинацию) до выполнения.
    """
    moment = now or datetime.now(UTC)

    return (
        select(Benefit)
        .join(Merchant, Merchant.id == Benefit.merchant_id)
        .join(
            BenefitPlanOffer,
            (BenefitPlanOffer.benefit_id == Benefit.id) & (BenefitPlanOffer.plan == plan),
        )
        .where(
            Benefit.is_active.is_(True),
            BenefitPlanOffer.is_available.is_(True),
            Merchant.status == MerchantStatus.ACTIVE,
            or_(Benefit.valid_from.is_(None), Benefit.valid_from <= moment),
            or_(Benefit.valid_until.is_(None), Benefit.valid_until > moment),
            or_(Benefit.company_id.is_(None), Benefit.company_id == company_id),
        )
        .options(selectinload(Benefit.plan_offers), selectinload(Benefit.merchant))
    )


def discount_for_plan(benefit: Benefit, plan: UserPlan) -> BenefitPlanOffer | None:
    """Найти оффер для плана среди уже загруженных plan_offers.

    Benefit.plan_offers загружается через lazy="selectin", поэтому обращение
    не порождает ленивый запрос в async-сессии.
    """
    for offer in benefit.plan_offers:
        if offer.plan == plan and offer.is_available:
            return offer
    return None
