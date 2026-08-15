"""Каталог льгот для сотрудника (NEXUS30 §28, §35).

Видимость определяет ``visible_benefits_query`` — один запрос и для списка, и для
детали, и для выдачи кода. Если бы detail-эндпоинт фильтровал иначе, сотрудник
STANDARD добрался бы до PRO-льготы по прямой ссылке.

CRUD мерчанта живёт в ``app/merchants/benefit_routes.py`` под собственным префиксом:
внутри этого роутера любой фиксированный путь после ``/{benefit_id}`` трактовался бы
как UUID и был бы недостижим.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.benefits.models import Benefit
from app.benefits.schemas import (
    BenefitDetailResponse,
    BenefitListItem,
    PlanOfferResponse,
    RedeemResponse,
)
from app.benefits.visibility import discount_for_plan, visible_benefits_query
from app.core.config import settings
from app.core.deps import AuthUser, DbSession, require_roles
from app.core.enums import BenefitCategory, RedemptionStatus, UserPlan, UserRole
from app.core.errors import BadRequest, NotFound
from app.core.pagination import Page, PageParams, paginate
from app.core.rate_limit import rate_limit
from app.events.publisher import publish_promo_issued
from app.redemptions.models import BenefitRedemption
from app.redemptions.service import redeem_benefit

router = APIRouter(prefix="/benefits", tags=["benefits"])

__all__ = ["router"]

EmployeeUser = Annotated[AuthUser, Depends(require_roles(UserRole.EMPLOYEE))]

_COUNTED_STATUSES = (RedemptionStatus.ISSUED, RedemptionStatus.REDEEMED)


def _require_employee_scope(user: AuthUser) -> tuple[UUID, UserPlan]:
    """Убедиться, что у сотрудника есть компания и тариф.

    Сотрудник без тарифа — следствие незавершённой выдачи места; каталог для него
    не определён, поэтому это ошибка данных, а не пустой список.
    """
    if not user.company_id or not user.plan:
        raise BadRequest(message="Employee must be assigned to a company and a plan")
    return user.company_id, user.plan


@router.get(
    "",
    response_model=Page[BenefitListItem],
    dependencies=[Depends(rate_limit("benefits", settings.rate_limit_benefits))],
)
async def list_benefits(
    db: DbSession,
    user: EmployeeUser,
    pagination: Annotated[PageParams, Depends()],
    category: Annotated[BenefitCategory | None, Query()] = None,
) -> Page[BenefitListItem]:
    """Каталог, отфильтрованный по тарифу сотрудника (NEXUS30 §8, §28)."""
    company_id, plan = _require_employee_scope(user)

    stmt = visible_benefits_query(plan, company_id).order_by(Benefit.title)
    if category:
        stmt = stmt.where(Benefit.category == category)

    page = await paginate(db, stmt, pagination)

    benefit_ids = [benefit.id for benefit in page.items]
    redeemed_ids: set[UUID] = set()
    if benefit_ids:
        redeemed_ids = set(
            (
                await db.scalars(
                    select(BenefitRedemption.benefit_id).where(
                        BenefitRedemption.employee_id == user.user_id,
                        BenefitRedemption.benefit_id.in_(benefit_ids),
                        BenefitRedemption.status.in_(_COUNTED_STATUSES),
                    )
                )
            ).all()
        )

    items: list[BenefitListItem] = []
    for benefit in page.items:
        offer = discount_for_plan(benefit, plan)
        items.append(
            BenefitListItem(
                id=benefit.id,
                title=benefit.title,
                description=benefit.description,
                category=benefit.category,
                merchant_id=benefit.merchant_id,
                merchant_name=benefit.merchant.name,
                destination_url=benefit.destination_url,
                valid_until=benefit.valid_until,
                your_discount_percent=offer.discount_percent if offer else Decimal(0),
                # Только доступные сотруднику уровни: перечислять чужие тарифы
                # означало бы показывать, какая скидка есть у коллег.
                plan_offers=[
                    PlanOfferResponse.model_validate(o)
                    for o in benefit.plan_offers
                    if o.is_available and o.plan == plan
                ],
                already_redeemed=benefit.id in redeemed_ids,
            )
        )

    return Page(items=items, meta=page.meta)


@router.get("/{benefit_id}", response_model=BenefitDetailResponse)
async def get_benefit_detail(
    benefit_id: UUID,
    db: DbSession,
    user: EmployeeUser,
) -> BenefitDetailResponse:
    """Детали льготы. Недоступная тарифу льгота отвечает 404, а не 403."""
    company_id, plan = _require_employee_scope(user)

    benefit = await db.scalar(visible_benefits_query(plan, company_id).where(Benefit.id == benefit_id))
    if benefit is None:
        raise NotFound(message="Benefit not found")

    offer = discount_for_plan(benefit, plan)
    used = (
        await db.scalar(
            select(func.count(BenefitRedemption.id)).where(
                BenefitRedemption.employee_id == user.user_id,
                BenefitRedemption.benefit_id == benefit_id,
                BenefitRedemption.status.in_(_COUNTED_STATUSES),
            )
        )
    ) or 0

    return BenefitDetailResponse(
        id=benefit.id,
        title=benefit.title,
        description=benefit.description,
        category=benefit.category,
        merchant_id=benefit.merchant_id,
        merchant_name=benefit.merchant.name,
        destination_url=benefit.destination_url,
        valid_until=benefit.valid_until,
        your_discount_percent=offer.discount_percent if offer else Decimal(0),
        plan_offers=[
            PlanOfferResponse.model_validate(o) for o in benefit.plan_offers if o.is_available and o.plan == plan
        ],
        already_redeemed=used > 0,
        max_redemptions_per_employee=benefit.max_redemptions_per_employee,
        promo_valid_days=benefit.promo_valid_days,
        redemptions_left=max(0, benefit.max_redemptions_per_employee - used),
    )


@router.post(
    "/{benefit_id}/redeem",
    response_model=RedeemResponse,
    # Выдача кода — самая дорогая операция каталога и главная цель
    # злоупотреблений: лимит здесь строже, чем на чтение.
    dependencies=[Depends(rate_limit("redemptions", settings.rate_limit_redemptions))],
)
async def redeem(
    benefit_id: UUID,
    db: DbSession,
    user: EmployeeUser,
) -> RedeemResponse:
    """Получить промокод на льготу (NEXUS30 §11, §14).

    Все проверки §14 выполняет ``redeem_benefit``. Событие публикуется после коммита:
    иначе подписчик мог бы получить уведомление о коде, вставка которого откатилась.
    """
    company_id, plan = _require_employee_scope(user)

    redemption, promo = await redeem_benefit(
        db=db,
        benefit_id=benefit_id,
        employee_id=user.user_id,
        company_id=company_id,
        plan=plan,
    )
    await db.commit()

    await publish_promo_issued(
        user_id=user.user_id,
        promo_code=promo.code,
        benefit_id=benefit_id,
        expires_at=promo.expires_at,
    )

    return RedeemResponse(
        redemption_id=redemption.id,
        promo_code=promo.code,
        expires_at=promo.expires_at,
        status=redemption.status,
        message="Promo code issued. Use it on the merchant's website.",
    )
