"""Pydantic-схемы каталога льгот (NEXUS30 §7, §10, §28)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import BenefitCategory, UserPlan

__all__ = [
    "BenefitCreateRequest",
    "BenefitUpdateRequest",
    "BenefitListItem",
    "BenefitDetailResponse",
    "MerchantBenefitResponse",
    "PlanOfferInput",
    "PlanOfferResponse",
]


class PlanOfferInput(BaseModel):
    """Условия льготы для одного плана (NEXUS30 §7)."""

    plan: UserPlan
    discount_percent: Decimal = Field(ge=0, le=100, decimal_places=2)
    is_available: bool = True


class PlanOfferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan: UserPlan
    discount_percent: Decimal
    is_available: bool


class BenefitCreateRequest(BaseModel):
    """Создание льготы мерчантом (NEXUS30 §30)."""

    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=10)
    category: BenefitCategory
    destination_url: str | None = Field(default=None, max_length=2048)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    usage_limit: int | None = Field(default=None, ge=1)
    max_redemptions_per_employee: int = Field(default=1, ge=1)
    promo_valid_days: int = Field(default=30, ge=1, le=365)

    # Скидки по планам: хотя бы один оффер обязателен.
    plan_offers: list[PlanOfferInput] = Field(min_length=1, max_length=3)

    # Обязательно для PLATFORM_ADMIN, игнорируется для MERCHANT (берётся из JWT).
    merchant_id: UUID | None = None
    # NULL = платформенная льгота для всех компаний.
    company_id: UUID | None = None

    @field_validator("plan_offers")
    @classmethod
    def _unique_plans(cls, offers: list[PlanOfferInput]) -> list[PlanOfferInput]:
        plans = [offer.plan for offer in offers]
        if len(plans) != len(set(plans)):
            raise ValueError("Duplicate plan in plan_offers")
        return offers

    @field_validator("valid_until")
    @classmethod
    def _validity_order(cls, until: datetime | None, info: object) -> datetime | None:
        data = getattr(info, "data", {})
        start = data.get("valid_from")
        if until is not None and start is not None and until <= start:
            raise ValueError("valid_until must be after valid_from")
        return until


class BenefitUpdateRequest(BaseModel):
    """Частичное обновление льготы. plan_offers заменяются целиком, если переданы."""

    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = Field(default=None, min_length=10)
    category: BenefitCategory | None = None
    destination_url: str | None = Field(default=None, max_length=2048)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    usage_limit: int | None = Field(default=None, ge=1)
    max_redemptions_per_employee: int | None = Field(default=None, ge=1)
    promo_valid_days: int | None = Field(default=None, ge=1, le=365)
    is_active: bool | None = None
    plan_offers: list[PlanOfferInput] | None = Field(default=None, min_length=1, max_length=3)

    @field_validator("plan_offers")
    @classmethod
    def _unique_plans(
        cls, offers: list[PlanOfferInput] | None
    ) -> list[PlanOfferInput] | None:
        if offers is None:
            return None
        plans = [offer.plan for offer in offers]
        if len(plans) != len(set(plans)):
            raise ValueError("Duplicate plan in plan_offers")
        return offers


class BenefitListItem(BaseModel):
    """Карточка каталога для сотрудника (NEXUS30 §28).

    your_discount_percent — скидка по плану текущего пользователя.
    plan_offers содержит только доступные пользователю уровни.
    """

    id: UUID
    title: str
    description: str
    category: BenefitCategory
    merchant_id: UUID
    merchant_name: str
    destination_url: str | None
    valid_until: datetime | None
    your_discount_percent: Decimal
    plan_offers: list[PlanOfferResponse]
    already_redeemed: bool = False


class BenefitDetailResponse(BenefitListItem):
    max_redemptions_per_employee: int
    promo_valid_days: int
    redemptions_left: int


class MerchantBenefitResponse(BaseModel):
    """Полное представление льготы для владельца-мерчанта и админа."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str
    category: BenefitCategory
    is_active: bool
    destination_url: str | None
    valid_from: datetime | None
    valid_until: datetime | None
    usage_limit: int | None
    max_redemptions_per_employee: int
    promo_valid_days: int
    merchant_id: UUID
    company_id: UUID | None
    created_at: datetime
    updated_at: datetime
    plan_offers: list[PlanOfferResponse]
