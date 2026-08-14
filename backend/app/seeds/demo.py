"""Demo seeds для NEXUS30 (§49).

Company Alpha: 300 STANDARD, 150 PLUS, 50 PRO seats.
Company Beta: меньше сотрудников.

Employees:
  alice@alphacorp.uz — STANDARD
  bob@alphacorp.uz — PLUS
  charlie@alphacorp.uz — PRO
  admin@alphacorp.uz — COMPANY_ADMIN

Merchants: Fitness, Language School, Restaurant, Online Education, Cinema.

Benefits: tiered discounts (5%/15%/45%) + PRO-only offers.
PromoCode examples + BenefitRedemption examples.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.benefits.models import Benefit
from app.benefits.plan_offers import BenefitPlanOffer
from app.companies.models import Company
from app.core.config import settings
from app.core.database import async_session_maker
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
from app.invites.models import InviteToken
from app.invites.service import create_invite_token
from app.merchants.models import Merchant
from app.plans.models import PlanAllocation
from app.promo_codes.models import PromoCode
from app.promo_codes.service import issue_promo_code
from app.redemptions.models import BenefitRedemption
from app.users.models import User


async def seed_demo() -> None:
    """Заполнить БД демо-данными (NEXUS30 §49)."""
    async with async_session_maker() as session:
        # Проверка: если уже есть данные, пропускаем seed.
        existing_count = await session.scalar(select(Company).limit(1))
        if existing_count:
            print("Demo data already exists, skipping seed.")
            return

        await _seed_all(session)
        await session.commit()
        print("✓ Demo data seeded successfully.")


async def _seed_all(session: AsyncSession) -> None:
    demo_password = os.getenv("DEMO_PASSWORD", "Demo1234!")
    password_hash = hash_password(demo_password)
    now = datetime.now(timezone.utc)

    # === Companies ===
    company_alpha = Company(name="AlphaCorp", status=CompanyStatus.ACTIVE)
    company_beta = Company(name="Beta Industries", status=CompanyStatus.ACTIVE)
    session.add_all([company_alpha, company_beta])
    await session.flush()

    # === Plan Allocations (NEXUS30 §4) ===
    alloc_alpha_std = PlanAllocation(
        company_id=company_alpha.id, plan=UserPlan.STANDARD, allocated=300, assigned=1
    )
    alloc_alpha_plus = PlanAllocation(
        company_id=company_alpha.id, plan=UserPlan.PLUS, allocated=150, assigned=1
    )
    alloc_alpha_pro = PlanAllocation(
        company_id=company_alpha.id, plan=UserPlan.PRO, allocated=50, assigned=1
    )
    alloc_beta_std = PlanAllocation(
        company_id=company_beta.id, plan=UserPlan.STANDARD, allocated=100, assigned=1
    )
    session.add_all([alloc_alpha_std, alloc_alpha_plus, alloc_alpha_pro, alloc_beta_std])

    # === Users ===
    alice = User(
        email="alice@alphacorp.uz",
        password_hash=password_hash,
        first_name="Alice",
        last_name="Smith",
        role=UserRole.EMPLOYEE,
        plan=UserPlan.STANDARD,
        is_active=True,
        company_id=company_alpha.id,
    )
    bob = User(
        email="bob@alphacorp.uz",
        password_hash=password_hash,
        first_name="Bob",
        last_name="Johnson",
        role=UserRole.EMPLOYEE,
        plan=UserPlan.PLUS,
        is_active=True,
        company_id=company_alpha.id,
    )
    charlie = User(
        email="charlie@alphacorp.uz",
        password_hash=password_hash,
        first_name="Charlie",
        last_name="Brown",
        role=UserRole.EMPLOYEE,
        plan=UserPlan.PRO,
        is_active=True,
        company_id=company_alpha.id,
    )
    admin_alpha = User(
        email="admin@alphacorp.uz",
        password_hash=password_hash,
        first_name="Admin",
        last_name="Alpha",
        role=UserRole.COMPANY_ADMIN,
        is_active=True,
        company_id=company_alpha.id,
    )
    eve = User(
        email="eve@betaindustries.uz",
        password_hash=password_hash,
        first_name="Eve",
        last_name="Davis",
        role=UserRole.EMPLOYEE,
        plan=UserPlan.STANDARD,
        is_active=True,
        company_id=company_beta.id,
    )
    platform_admin = User(
        email="platform@admin.uz",
        password_hash=password_hash,
        first_name="Platform",
        last_name="Admin",
        role=UserRole.PLATFORM_ADMIN,
        is_active=True,
    )
    session.add_all([alice, bob, charlie, admin_alpha, eve, platform_admin])
    await session.flush()

    # === Merchants ===
    merchant_fitness = Merchant(
        name="FitZone Gym",
        email="merchant@fitzone.uz",
        status=MerchantStatus.ACTIVE,
        description="Premium fitness club with modern equipment",
    )
    merchant_language = Merchant(
        name="IT Academy",
        email="merchant@itacademy.uz",
        status=MerchantStatus.ACTIVE,
        description="Online courses for IT professionals",
    )
    merchant_restaurant = Merchant(
        name="Food Hub",
        email="merchant@foodhub.uz",
        status=MerchantStatus.ACTIVE,
        description="Healthy food delivery",
    )
    merchant_cinema = Merchant(
        name="Cinema Plus",
        email="merchant@cinemaplus.uz",
        status=MerchantStatus.ACTIVE,
        description="Movie theater chain",
    )
    session.add_all([merchant_fitness, merchant_language, merchant_restaurant, merchant_cinema])
    await session.flush()

    # Merchant users
    user_merchant_fitness = User(
        email="merchant.user@fitzone.uz",
        password_hash=password_hash,
        first_name="Merchant",
        last_name="FitZone",
        role=UserRole.MERCHANT,
        is_active=True,
        merchant_id=merchant_fitness.id,
    )
    session.add(user_merchant_fitness)
    await session.flush()

    # === Benefits with tiered plan offers (NEXUS30 §7) ===
    benefit_gym = Benefit(
        title="Annual Gym Membership",
        description="Full access to all gym facilities, group classes, and personal trainer consultations",
        category=BenefitCategory.SPORT,
        merchant_id=merchant_fitness.id,
        is_active=True,
        destination_url="https://fitzone.uz/corporate",
        valid_from=now - timedelta(days=30),
        valid_until=now + timedelta(days=365),
        usage_limit=None,
        max_redemptions_per_employee=1,
        promo_valid_days=30,
    )
    session.add(benefit_gym)
    await session.flush()

    # STANDARD=5%, PLUS=15%, PRO=45%
    offer_gym_std = BenefitPlanOffer(
        benefit_id=benefit_gym.id,
        plan=UserPlan.STANDARD,
        discount_percent=Decimal("5.00"),
        is_available=True,
    )
    offer_gym_plus = BenefitPlanOffer(
        benefit_id=benefit_gym.id,
        plan=UserPlan.PLUS,
        discount_percent=Decimal("15.00"),
        is_available=True,
    )
    offer_gym_pro = BenefitPlanOffer(
        benefit_id=benefit_gym.id,
        plan=UserPlan.PRO,
        discount_percent=Decimal("45.00"),
        is_available=True,
    )
    session.add_all([offer_gym_std, offer_gym_plus, offer_gym_pro])

    benefit_course = Benefit(
        title="Online IT Course",
        description="Full access to Python, JavaScript, or DevOps courses",
        category=BenefitCategory.EDUCATION,
        merchant_id=merchant_language.id,
        is_active=True,
        destination_url="https://itacademy.uz/corporate",
        valid_from=now,
        valid_until=now + timedelta(days=180),
        usage_limit=None,
        max_redemptions_per_employee=2,
        promo_valid_days=60,
    )
    session.add(benefit_course)
    await session.flush()

    offer_course_std = BenefitPlanOffer(
        benefit_id=benefit_course.id,
        plan=UserPlan.STANDARD,
        discount_percent=Decimal("10.00"),
        is_available=True,
    )
    offer_course_plus = BenefitPlanOffer(
        benefit_id=benefit_course.id,
        plan=UserPlan.PLUS,
        discount_percent=Decimal("20.00"),
        is_available=True,
    )
    offer_course_pro = BenefitPlanOffer(
        benefit_id=benefit_course.id,
        plan=UserPlan.PRO,
        discount_percent=Decimal("50.00"),
        is_available=True,
    )
    session.add_all([offer_course_std, offer_course_plus, offer_course_pro])

    # PRO-only benefit (NEXUS30 §28: STANDARD/PLUS не видят этот benefit через API)
    benefit_cinema_vip = Benefit(
        title="VIP Cinema Package",
        description="Unlimited VIP cinema tickets + lounge access",
        category=BenefitCategory.ENTERTAINMENT,
        merchant_id=merchant_cinema.id,
        is_active=True,
        destination_url="https://cinemaplus.uz/vip",
        valid_from=now,
        valid_until=now + timedelta(days=365),
        usage_limit=50,
        max_redemptions_per_employee=1,
        promo_valid_days=90,
    )
    session.add(benefit_cinema_vip)
    await session.flush()

    offer_cinema_pro_only = BenefitPlanOffer(
        benefit_id=benefit_cinema_vip.id,
        plan=UserPlan.PRO,
        discount_percent=Decimal("60.00"),
        is_available=True,
    )
    session.add(offer_cinema_pro_only)

    # === Redemption + PromoCode example ===
    redemption_alice = BenefitRedemption(
        employee_id=alice.id,
        company_id=company_alpha.id,
        benefit_id=benefit_gym.id,
        status=RedemptionStatus.ISSUED,
    )
    session.add(redemption_alice)
    await session.flush()

    promo_alice = await issue_promo_code(
        db=session,
        benefit_id=benefit_gym.id,
        employee_id=alice.id,
        redemption_id=redemption_alice.id,
        merchant_name=merchant_fitness.name,
        promo_valid_days=benefit_gym.promo_valid_days,
    )

    # Charlie (PRO) redeemed VIP cinema
    redemption_charlie = BenefitRedemption(
        employee_id=charlie.id,
        company_id=company_alpha.id,
        benefit_id=benefit_cinema_vip.id,
        status=RedemptionStatus.REDEEMED,
        redeemed_at=now - timedelta(days=2),
    )
    session.add(redemption_charlie)
    await session.flush()

    promo_charlie = await issue_promo_code(
        db=session,
        benefit_id=benefit_cinema_vip.id,
        employee_id=charlie.id,
        redemption_id=redemption_charlie.id,
        merchant_name=merchant_cinema.name,
        promo_valid_days=benefit_cinema_vip.promo_valid_days,
    )
    promo_charlie.status = PromoCodeStatus.REDEEMED
    promo_charlie.redeemed_at = now - timedelta(days=2)
    promo_charlie.redeemed_by_id = user_merchant_fitness.id

    # === Invite tokens ===
    invite_alpha_std, token_std = await create_invite_token(
        db=session,
        company_id=company_alpha.id,
        plan=UserPlan.STANDARD,
        created_by_id=admin_alpha.id,
        email=None,
        expires_in_days=7,
    )
    invite_alpha_pro, token_pro = await create_invite_token(
        db=session,
        company_id=company_alpha.id,
        plan=UserPlan.PRO,
        created_by_id=admin_alpha.id,
        email=None,
        expires_in_days=7,
    )

    print(f"Demo invite tokens (save these):")
    print(f"  STANDARD: {token_std}")
    print(f"  PRO: {token_pro}")

    # === Audit log examples ===
    audit_company = AuditLog(
        actor_id=platform_admin.id,
        action=AuditAction.COMPANY_CREATED,
        entity_type="Company",
        entity_id=str(company_alpha.id),
        company_id=company_alpha.id,
        metadata={"name": "AlphaCorp"},
    )
    audit_redemption = AuditLog(
        actor_id=alice.id,
        action=AuditAction.REDEMPTION_CREATED,
        entity_type="BenefitRedemption",
        entity_id=str(redemption_alice.id),
        company_id=company_alpha.id,
        metadata={"benefit_id": str(benefit_gym.id), "promo_code": promo_alice.code},
    )
    session.add_all([audit_company, audit_redemption])


def main() -> None:
    """Entry point для запуска через `python -m app.seeds.demo`."""
    if not os.getenv("SEED_DEMO_DATA"):
        print("SEED_DEMO_DATA not set, skipping demo seed.")
        return

    asyncio.run(seed_demo())


if __name__ == "__main__":
    main()
