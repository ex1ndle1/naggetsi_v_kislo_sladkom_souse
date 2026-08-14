"""Pydantic-схемы для работы с мерчантами."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.core.enums import MerchantStatus

__all__ = [
    "MerchantResponse",
    "MerchantCreateRequest",
    "MerchantUpdateRequest",
    "MerchantListResponse",
]


class MerchantResponse(BaseModel):
    """Публичное представление мерчанта."""

    id: UUID
    name: str
    email: str
    status: MerchantStatus
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MerchantCreateRequest(BaseModel):
    """Создание нового мерчанта (только PLATFORM_ADMIN)."""

    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    description: str | None = None


class MerchantUpdateRequest(BaseModel):
    """Обновление мерчанта."""

    name: str | None = Field(None, min_length=1, max_length=255)
    email: EmailStr | None = None
    status: MerchantStatus | None = None
    description: str | None = None


class MerchantListResponse(BaseModel):
    """Список мерчантов с пагинацией."""

    items: list[MerchantResponse]
    total: int
    page: int
    page_size: int
