"""Схемы истории сотрудника (NEXUS30 §35).

Обе истории собираются вручную из связей, а не через ``from_attributes``: в ответ
идут название льготы и имя мерчанта, но не служебные поля вроде ``company_id``
или ``redeemed_by_id``.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.core.enums import BenefitCategory, PromoCodeStatus, RedemptionStatus

__all__ = ["MyPromoCodeItem", "MyRedemptionItem", "PromoCodeLookupResponse"]


class MyPromoCodeItem(BaseModel):
    """Промокод сотрудника с данными, нужными для его использования."""

    id: UUID
    code: str
    status: PromoCodeStatus
    issued_at: datetime
    expires_at: datetime
    redeemed_at: datetime | None
    benefit_id: UUID
    benefit_title: str
    merchant_name: str
    destination_url: str | None
    discount_percent: Decimal | None


class MyRedemptionItem(BaseModel):
    """Факт получения льготы."""

    id: UUID
    status: RedemptionStatus
    created_at: datetime
    redeemed_at: datetime | None
    benefit_id: UUID
    benefit_title: str
    benefit_category: BenefitCategory
    merchant_name: str
    promo_code: str | None
    promo_status: PromoCodeStatus | None
    promo_expires_at: datetime | None


class PromoCodeLookupResponse(BaseModel):
    """Что видит мерчант, проверяя предъявленный код (NEXUS30 §41).

    Сотрудник не идентифицируется: мерчанту достаточно знать, что код настоящий,
    к какой льготе относится и какую скидку даёт.
    """

    code: str
    status: PromoCodeStatus
    is_redeemable: bool
    expires_at: datetime
    redeemed_at: datetime | None
    benefit_id: UUID
    benefit_title: str
    discount_percent: Decimal | None
    employee_plan_discount_note: str | None = None
