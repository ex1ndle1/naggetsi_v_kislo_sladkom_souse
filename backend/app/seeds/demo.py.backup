"""Демо-данные NEXUS30 §49.

Company Alpha: 300 STANDARD, 150 PLUS, 50 PRO мест.
Company Beta: одна компания-сосед, нужна для проверки изоляции арендаторов.

Сотрудники Alpha: alice (STANDARD), bob (PLUS), charlie (PRO), admin (COMPANY_ADMIN).
Мерчанты: Fitness, Language School, Restaurant, Online Education, Cinema.
Льготы: ярусная скидка 5/15/45 и льгота только для PRO.
Плюс примеры промокода и погашения.

Счётчик assigned в аллокациях выводится из фактически созданных сотрудников, а не
задаётся константой: расхождение здесь сразу нарушило бы инвариант assigned <= allocated
и сломало выдачу мест на демо-стенде.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.benefits.models import Benefit
from app.benefits.plan_offers import BenefitPlanOffer
from app.companies.models import Company
from app.core.config import settings
from app.core.database import SessionFactory
from app.core.enums import (
    AuditAction,
    BenefitCategory,
    CompanyStatus,
    MerchantStatus,
    PromoCodeStatus,
    RedemptionStatus,
    UserPlan,
    UserRole,
)
from app.core.security import hash_password
from app.invites.service import create_invite_token
from app.merchants.models import Merchant
from app.plans.models import PlanAllocation
from app.promo_codes.service import issue_promo_code
from app.redemptions.models import BenefitRedemption
from app.users.models import User

ALPHA_SEATS = {UserPlan.STANDARD: 300, UserPlan.PLUS: 150, UserPlan.PRO: 50}
BETA_SEATS = {UserPlan.STANDARD: 100}


async def seed_demo() -> None:
    """Заполнить БД демо-данными. Повторный запуск — no-op."""
    async with SessionFactory() as session:
        existing = await session.scalar(select(Company.id).limit(1))
        if existing:
            print("Demo data already present — nothing to seed.")
            return

        await _seed_all(session)
        await session.commit()
        print("Demo data seeded.")


async def _seed_all(session: AsyncSession) -> None:
    password_hash = hash_password(settings.demo_password.get_secret_value())
    now = datetime.now(UTC)

    # --- Компании ---
    alpha = Company(name="AlphaCorp", status=CompanyStatus.ACTIVE)
    beta = Company(name="Beta Industries", status=CompanyStatus.ACTIVE)
    session.add_all([alpha, beta])
    await session.flush()

    # --- Сотрудники ---
    alice = User(
        email="alice@alphacorp.uz",
        password_hash=password_hash,
        first_name="Alice",
        last_name="Smith",
        role=UserRole.EMPLOYEE,
        plan=UserPlan.STANDARD,
        is_active=True,
        company_id=alpha.id,
    )
    bob = User(
        email="bob@alphacorp.uz",
        password_hash=password_hash,
        first_name="Bob",
        last_name="Johnson",
        role=UserRole.EMPLOYEE,
        plan=UserPlan.PLUS,
        is_active=True,
        company_id=alpha.id,
    )
    charlie = User(
        email="charlie@alphacorp.uz",
        password_hash=password_hash,
        first_name="Charlie",
        last_name="Brown",
        role=UserRole.EMPLOYEE,
        plan=UserPlan.PRO,
        is_active=True,
        company_id=alpha.id,
    )
    alpha_admin = User(
        email="admin@alphacorp.uz",
        password_hash=password_hash,
        first_name="Admin",
        last_name="Alpha",
        role=UserRole.COMPANY_ADMIN,
        is_active=True,
        company_id=alpha.id,
    )
    eve = User(
        email="eve@betaindustries.uz",
        password_hash=password_hash,
        first_name="Eve",
        last_name="Davis",
        role=UserRole.EMPLOYEE,
        plan=UserPlan.STANDARD,
        is_active=True,
        company_id=beta.id,
    )
    platform_admin = User(
        email="platform@admin.uz",
        password_hash=password_hash,
        first_name="Platform",
        last_name="Admin",
        role=UserRole.PLATFORM_ADMIN,
        is_active=True,
    )
    session.add_all([alice, bob, charlie, alpha_admin, eve, platform_admin])
    await session.flush()

    # --- Места ---
    # Считаем занятые места по фактическим сотрудникам с тарифом.
    alpha_assigned = Counter(user.plan for user in (alice, bob, charlie) if user.plan is not None)
    beta_assigned = Counter(user.plan for user in (eve,) if user.plan is not None)

    session.add_all(
        [
            PlanAllocation(
                company_id=alpha.id,
                plan=plan,
                allocated=allocated,
                assigned=alpha_assigned.get(plan, 0),
            )
            for plan, allocated in ALPHA_SEATS.items()
        ]
        + [
            PlanAllocation(
                company_id=beta.id,
                plan=plan,
                allocated=allocated,
                assigned=beta_assigned.get(plan, 0),
            )
            for plan, allocated in BETA_SEATS.items()
        ]
    )

    # --- Мерчанты (§49: пять штук) ---
    fitness = Merchant(
        name="FitZone Gym",
        email="merchant@fitzone.uz",
        status=MerchantStatus.ACTIVE,
        description="Premium fitness club with modern equipment",
    )
    language_school = Merchant(
        name="Lingua Center",
        email="merchant@lingua.uz",
        status=MerchantStatus.ACTIVE,
        description="English, German and Korean language courses",
    )
    restaurant = Merchant(
        name="Food Hub",
        email="merchant@foodhub.uz",
        status=MerchantStatus.ACTIVE,
        description="Healthy food delivery and canteen network",
    )
    online_education = Merchant(
        name="IT Academy",
        email="merchant@itacademy.uz",
        status=MerchantStatus.ACTIVE,
        description="Online courses for IT professionals",
    )
    cinema = Merchant(
        name="Cinema Plus",
        email="merchant@cinemaplus.uz",
        status=MerchantStatus.ACTIVE,
        description="Movie theater chain",
    )
    session.add_all([fitness, language_school, restaurant, online_education, cinema])
    await session.flush()

    fitness_user = User(
        email="merchant.user@fitzone.uz",
        password_hash=password_hash,
        first_name="Merchant",
        last_name="FitZone",
        role=UserRole.MERCHANT,
        is_active=True,
        merchant_id=fitness.id,
    )
    cinema_user = User(
        email="merchant.user@cinemaplus.uz",
        password_hash=password_hash,
        first_name="Merchant",
        last_name="CinemaPlus",
        role=UserRole.MERCHANT,
        is_active=True,
        merchant_id=cinema.id,
    )
    session.add_all([fitness_user, cinema_user])
    await session.flush()

    # --- Льготы ---
    gym = Benefit(
        title="Annual Gym Membership",
        description=("Full access to all gym facilities, group classes and personal trainer consultations"),
        category=BenefitCategory.SPORT,
        merchant_id=fitness.id,
        is_active=True,
        destination_url="https://fitzone.uz/corporate",
        valid_from=now - timedelta(days=30),
        valid_until=now + timedelta(days=365),
        usage_limit=None,
        max_redemptions_per_employee=1,
        promo_valid_days=30,
    )
    course = Benefit(
        title="Online IT Course",
        description="Full access to Python, JavaScript or DevOps learning tracks",
        category=BenefitCategory.EDUCATION,
        merchant_id=online_education.id,
        is_active=True,
        destination_url="https://itacademy.uz/corporate",
        valid_from=now,
        valid_until=now + timedelta(days=180),
        usage_limit=None,
        max_redemptions_per_employee=2,
        promo_valid_days=60,
    )
    language = Benefit(
        title="Language Course Package",
        description="Group lessons in English, German or Korean, three levels available",
        category=BenefitCategory.EDUCATION,
        merchant_id=language_school.id,
        is_active=True,
        destination_url="https://lingua.uz/corporate",
        valid_from=now,
        valid_until=now + timedelta(days=270),
        usage_limit=200,
        max_redemptions_per_employee=1,
        promo_valid_days=45,
    )
    lunch = Benefit(
        title="Business Lunch Subscription",
        description="Daily business lunch delivery to the office",
        category=BenefitCategory.FOOD,
        merchant_id=restaurant.id,
        is_active=True,
        destination_url="https://foodhub.uz/corporate",
        valid_from=now,
        valid_until=now + timedelta(days=120),
        usage_limit=None,
        max_redemptions_per_employee=3,
        promo_valid_days=14,
    )
    cinema_vip = Benefit(
        title="VIP Cinema Package",
        description="Unlimited VIP cinema tickets and lounge access",
        category=BenefitCategory.ENTERTAINMENT,
        merchant_id=cinema.id,
        is_active=True,
        destination_url="https://cinemaplus.uz/vip",
        valid_from=now,
        valid_until=now + timedelta(days=365),
        usage_limit=50,
        max_redemptions_per_employee=1,
        promo_valid_days=90,
    )
    session.add_all([gym, course, language, lunch, cinema_vip])
    await session.flush()

    # Ярусные скидки §49: 5 / 15 / 45 на льготу спортзала.
    tiered: dict[Benefit, dict[UserPlan, str]] = {
        gym: {UserPlan.STANDARD: "5.00", UserPlan.PLUS: "15.00", UserPlan.PRO: "45.00"},
        course: {UserPlan.STANDARD: "10.00", UserPlan.PLUS: "20.00", UserPlan.PRO: "50.00"},
        language: {UserPlan.STANDARD: "7.00", UserPlan.PLUS: "18.00", UserPlan.PRO: "35.00"},
        lunch: {UserPlan.STANDARD: "10.00", UserPlan.PLUS: "25.00", UserPlan.PRO: "40.00"},
        # Только PRO: STANDARD и PLUS не увидят эту льготу ни в списке, ни в детали.
        cinema_vip: {UserPlan.PRO: "60.00"},
    }
    session.add_all(
        [
            BenefitPlanOffer(
                benefit_id=benefit.id,
                plan=plan,
                discount_percent=Decimal(percent),
                is_available=True,
            )
            for benefit, offers in tiered.items()
            for plan, percent in offers.items()
        ]
    )

    # --- Примеры погашения ---
    # alice получила код и ещё не использовала его.
    alice_redemption = BenefitRedemption(
        employee_id=alice.id,
        company_id=alpha.id,
        benefit_id=gym.id,
        status=RedemptionStatus.ISSUED,
    )
    session.add(alice_redemption)
    await session.flush()

    alice_promo = await issue_promo_code(
        db=session,
        benefit_id=gym.id,
        employee_id=alice.id,
        redemption_id=alice_redemption.id,
        merchant_name=fitness.name,
        promo_valid_days=gym.promo_valid_days,
    )

    # charlie использовал PRO-льготу, мерчант подтвердил код.
    redeemed_at = now - timedelta(days=2)
    charlie_redemption = BenefitRedemption(
        employee_id=charlie.id,
        company_id=alpha.id,
        benefit_id=cinema_vip.id,
        status=RedemptionStatus.REDEEMED,
        redeemed_at=redeemed_at,
    )
    session.add(charlie_redemption)
    await session.flush()

    charlie_promo = await issue_promo_code(
        db=session,
        benefit_id=cinema_vip.id,
        employee_id=charlie.id,
        redemption_id=charlie_redemption.id,
        merchant_name=cinema.name,
        promo_valid_days=cinema_vip.promo_valid_days,
    )
    charlie_promo.status = PromoCodeStatus.REDEEMED
    charlie_promo.redeemed_at = redeemed_at
    # Подтверждает мерчант той льготы, а не первый попавшийся.
    charlie_promo.redeemed_by_id = cinema_user.id

    # --- Инвайты ---
    _, standard_token = await create_invite_token(
        db=session,
        company_id=alpha.id,
        plan=UserPlan.STANDARD,
        created_by_id=alpha_admin.id,
        expires_in_days=settings.invite_token_expire_days,
    )
    _, pro_token = await create_invite_token(
        db=session,
        company_id=alpha.id,
        plan=UserPlan.PRO,
        created_by_id=alpha_admin.id,
        expires_in_days=settings.invite_token_expire_days,
    )

    # Plaintext существует только здесь: в БД лежит SHA-256, восстановить нельзя.
    print("Demo invite tokens (shown once, not recoverable from the database):")
    print(f"  STANDARD: {standard_token}")
    print(f"  PRO:      {pro_token}")

    # --- Журнал ---
    session.add_all(
        [
            AuditLog(
                actor_id=platform_admin.id,
                action=AuditAction.COMPANY_CREATED,
                entity_type="Company",
                entity_id=str(alpha.id),
                company_id=alpha.id,
                meta={"name": alpha.name},
            ),
            AuditLog(
                actor_id=alice.id,
                action=AuditAction.REDEMPTION_CREATED,
                entity_type="BenefitRedemption",
                entity_id=str(alice_redemption.id),
                company_id=alpha.id,
                meta={"benefit_id": str(gym.id), "promo_code_id": str(alice_promo.id)},
            ),
            AuditLog(
                actor_id=cinema_user.id,
                action=AuditAction.PROMO_REDEEMED,
                entity_type="PromoCode",
                entity_id=str(charlie_promo.id),
                company_id=alpha.id,
                meta={"benefit_id": str(cinema_vip.id)},
            ),
        ]
    )


def main() -> None:
    """Точка входа для `python -m app.seeds.demo`."""
    if not settings.seed_demo_data:
        print("SEED_DEMO_DATA is disabled — skipping demo seed.")
        return

    asyncio.run(seed_demo())


if __name__ == "__main__":
    main()
