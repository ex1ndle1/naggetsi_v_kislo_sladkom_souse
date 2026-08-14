"""Pydantic-схемы для работы с компаниями."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import CompanyStatus

__all__ = [
    "CompanyResponse",
    "CompanyCreateRequest",
    "CompanyUpdateRequest",
    "CompanyListResponse",
]


class CompanyResponse(BaseModel):
    """Публичное представление компании."""

    id: UUID
    name: str
    status: CompanyStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CompanyCreateRequest(BaseModel):
    """Создание новой компании (только PLATFORM_ADMIN)."""

    name: str = Field(..., min_length=1, max_length=255)


class CompanyUpdateRequest(BaseModel):
    """Обновление компании."""

    name: str | None = Field(None, min_length=1, max_length=255)
    status: CompanyStatus | None = None


class CompanyListResponse(BaseModel):
    """Список компаний с пагинацией."""

    items: list[CompanyResponse]
    total: int
    page: int
    page_size: int
