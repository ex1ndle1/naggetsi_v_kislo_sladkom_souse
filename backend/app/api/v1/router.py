"""API v1 router aggregator."""

from fastapi import APIRouter

from app.admin_routes import router as admin_router
from app.ai.routes import router as ai_router
from app.benefits.routes import router as benefits_router
from app.bot.routes import router as bot_router
from app.companies.admin_routes import router as company_admin_router
from app.companies.routes import router as companies_router
from app.events.routes import router as events_router
from app.merchants.benefit_routes import router as merchant_benefit_router
from app.merchants.routes import router as merchants_router
from app.promo_codes.routes import router as promo_codes_router
from app.users.me_routes import router as me_router
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

# Личный кабинет: профиль и история
api_v1_router.include_router(me_router)

# Benefits catalog
api_v1_router.include_router(benefits_router)

# Кабинет администратора компании: места, сотрудники, приглашения.
# Подключается до /companies, чтобы префикс /company не перехватывался.
api_v1_router.include_router(company_admin_router)

# Companies management
api_v1_router.include_router(companies_router)

# Merchant cabinet benefit lifecycle
api_v1_router.include_router(merchant_benefit_router)

# Merchant promo-code lookup and redemption
api_v1_router.include_router(promo_codes_router, prefix="/merchant")

# Merchants management
api_v1_router.include_router(merchants_router)

# Platform administrator read and account-management APIs
api_v1_router.include_router(admin_router)

# AI recommendations and analytics
api_v1_router.include_router(ai_router)

# Real-time events (SSE)
api_v1_router.include_router(events_router)

# Проверка промокодов Telegram-ботом: аутентификация по общему ключу, не по JWT
api_v1_router.include_router(bot_router)
