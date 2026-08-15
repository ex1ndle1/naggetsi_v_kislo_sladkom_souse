"""AI router: консьерж сотрудника, ассистент мерчанта, отчёт компании (NEXUS30 §17-§19).

Общее для всех трёх: выборка данных делается SQL-слоем под правами вызывающего, и
только результат этой выборки уходит в модель. AI не расширяет доступ и не влияет на
решения о выдаче льгот — при его недоступности эндпоинты отвечают деградированно,
но не ошибкой.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.ai.service import (
    ConciergeResult,
    MerchantDraft,
    company_insights,
    generate_offer_draft,
    rank_benefits_for_employee,
)
from app.analytics.service import company_analytics
from app.audit.service import record_audit
from app.benefits.visibility import discount_for_plan, visible_benefits_query
from app.core.config import settings
from app.core.deps import AuthUser, DbSession, require_roles
from app.core.enums import AuditAction, UserRole
from app.core.errors import BadRequest
from app.core.rate_limit import rate_limit
from app.merchants.models import Merchant

router = APIRouter(prefix="/ai", tags=["ai"])

# Сколько льгот отдаём модели. Ограничение не косметическое: длинный контекст режет
# качество ранжирования и упирается в таймаут.
_CONCIERGE_CATALOG_LIMIT = 40


class ConciergeRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)


class ConciergeBenefit(BaseModel):
    """Льгота в ответе консьержа — с процентом скидки для тарифа сотрудника."""

    id: UUID
    title: str
    category: str
    merchant_name: str
    your_discount_percent: float


class ConciergeResponse(BaseModel):
    benefits: list[ConciergeBenefit]
    reasoning: str | None = None
    ai_used: bool


class OfferDraftRequest(BaseModel):
    hint: str = Field(min_length=5, max_length=2000, description="Описание льготы словами мерчанта")


class OfferDraftResponse(BaseModel):
    draft: MerchantDraft | None
    ai_used: bool
    message: str | None = None


class CompanyReportResponse(BaseModel):
    metrics: dict[str, object]
    insights: str | None
    ai_used: bool


@router.post(
    "/concierge",
    response_model=ConciergeResponse,
    dependencies=[Depends(rate_limit("ai", settings.rate_limit_ai))],
)
async def concierge(
    payload: ConciergeRequest,
    db: DbSession,
    user: Annotated[AuthUser, Depends(require_roles(UserRole.EMPLOYEE))],
) -> ConciergeResponse:
    """Сценарий 1: подбор льгот под запрос сотрудника.

    Каталог берётся тем же ``visible_benefits_query``, что и обычный список, поэтому
    консьерж физически не может предложить льготу вне тарифа или чужой компании.
    """
    if not user.company_id or not user.plan:
        raise BadRequest(message="Employee must have a company and a plan")

    stmt = visible_benefits_query(user.plan, user.company_id).limit(_CONCIERGE_CATALOG_LIMIT)
    benefits = list((await db.scalars(stmt)).unique().all())

    catalog: list[dict[str, object]] = []
    by_id = {}
    for benefit in benefits:
        offer = discount_for_plan(benefit, user.plan)
        if offer is None:
            continue
        by_id[benefit.id] = (benefit, offer)
        catalog.append(
            {
                "id": str(benefit.id),
                "title": benefit.title,
                "category": benefit.category.value,
                "description": benefit.description[:300],
                "discount_percent": float(offer.discount_percent),
                "merchant": benefit.merchant.name,
            }
        )

    result: ConciergeResult = await rank_benefits_for_employee(
        query=payload.query,
        eligible=catalog,
        employee_context={"plan": user.plan.value},
    )

    record_audit(
        db,
        action=AuditAction.AI_REQUEST if result.ai_used else AuditAction.AI_ERROR,
        actor_id=user.user_id,
        company_id=user.company_id,
        entity_type="ai_concierge",
        meta={"catalog_size": len(catalog), "ai_used": result.ai_used},
    )
    await db.commit()

    ordered: list[ConciergeBenefit] = []
    for benefit_id in result.benefit_ids:
        entry = by_id.get(benefit_id)
        if entry is None:
            continue
        benefit, offer = entry
        ordered.append(
            ConciergeBenefit(
                id=benefit.id,
                title=benefit.title,
                category=benefit.category.value,
                merchant_name=benefit.merchant.name,
                your_discount_percent=float(offer.discount_percent),
            )
        )

    return ConciergeResponse(
        benefits=ordered,
        reasoning=result.reasoning,
        ai_used=result.ai_used,
    )


@router.post(
    "/merchant/generate-offer",
    response_model=OfferDraftResponse,
    dependencies=[Depends(rate_limit("ai", settings.rate_limit_ai))],
)
async def generate_offer(
    payload: OfferDraftRequest,
    db: DbSession,
    user: Annotated[AuthUser, Depends(require_roles(UserRole.MERCHANT, UserRole.PLATFORM_ADMIN))],
) -> OfferDraftResponse:
    """Сценарий 2: черновик описания льготы.

    Черновик ничего не публикует. Мерчант правит текст и создаёт льготу обычным
    ``POST /merchant/benefits`` — скидки и сроки задаёт человек, а не модель.
    """
    merchant_name = "Merchant"
    if user.merchant_id:
        merchant = await db.get(Merchant, user.merchant_id)
        if merchant is not None:
            merchant_name = merchant.name

    result = await generate_offer_draft(merchant_name=merchant_name, hint=payload.hint)

    record_audit(
        db,
        action=AuditAction.AI_REQUEST if result else AuditAction.AI_ERROR,
        actor_id=user.user_id,
        entity_type="ai_offer_draft",
        entity_id=user.merchant_id,
        meta={"ai_used": result is not None},
    )
    await db.commit()

    if result is None:
        return OfferDraftResponse(
            draft=None,
            ai_used=False,
            message="AI unavailable — fill the offer manually",
        )
    return OfferDraftResponse(draft=result.draft, ai_used=True)


@router.get(
    "/company-report",
    response_model=CompanyReportResponse,
    dependencies=[Depends(rate_limit("ai", settings.rate_limit_ai))],
)
async def get_company_report(
    db: DbSession,
    user: Annotated[AuthUser, Depends(require_roles(UserRole.COMPANY_ADMIN, UserRole.PLATFORM_ADMIN))],
    company_id: UUID | None = None,
) -> CompanyReportResponse:
    """Сценарий 3: рекомендации по метрикам компании.

    Числовая часть отчёта считается в SQL и возвращается всегда; текст модели —
    дополнение. COMPANY_ADMIN видит только свою компанию, платформенный админ может
    указать любую параметром.
    """
    if user.role == UserRole.COMPANY_ADMIN:
        if not user.company_id:
            raise BadRequest(message="COMPANY_ADMIN must be associated with a company")
        target_company = user.company_id
    else:
        if company_id is None:
            raise BadRequest(message="company_id is required for platform admin")
        target_company = company_id

    analytics = await company_analytics(db, target_company)
    metrics = analytics.to_prompt_payload()
    insights = await company_insights(metrics=metrics)

    record_audit(
        db,
        action=AuditAction.AI_REQUEST if insights else AuditAction.AI_ERROR,
        actor_id=user.user_id,
        company_id=target_company,
        entity_type="ai_company_report",
        entity_id=target_company,
        meta={"ai_used": insights is not None},
    )
    await db.commit()

    return CompanyReportResponse(
        metrics=metrics,
        insights=insights,
        ai_used=insights is not None,
    )
