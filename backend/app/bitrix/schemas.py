"""Bitrix24 integration schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, HttpUrl


class BitrixSyncRequest(BaseModel):
    webhook_url: HttpUrl


class BitrixSyncResponse(BaseModel):
    company_id: UUID
    webhook_url: str
    total_fetched: int
    created: int
    updated: int
