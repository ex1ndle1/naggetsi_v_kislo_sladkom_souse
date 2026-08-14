"""API v1 router aggregator."""

from fastapi import APIRouter

from app.ai.routes import router as ai_router
from app.benefits.routes import router as benefits_router
from app.companies.routes import router as companies_router
from app.events.routes import router as events_router
from app.merchants.routes import router as merchants_router
from app.users.routes import router as auth_router

__all__ = ["api_v1_router"]

api_v1_router = APIRouter()

# Health check
@api_v1_router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}

# Auth endpoints
api_v1_router.include_router(auth_router)

# Benefits catalog
api_v1_router.include_router(benefits_router)

# Companies management
api_v1_router.include_router(companies_router)

# Merchants management
api_v1_router.include_router(merchants_router)

# AI recommendations and analytics
api_v1_router.include_router(ai_router)

# Real-time events (SSE)
api_v1_router.include_router(events_router)
