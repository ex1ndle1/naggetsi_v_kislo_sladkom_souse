"""Демо-данные NEXUS30 §49.

Company Alpha: 300 STANDARD, 150 PLUS, 50 PRO мест (занято 170: 100 + 50 + 20).
Company Beta: 100 мест STANDARD (занято 50).

Расширенный seed для реалистичной статистики:
- 12-15 мерчантов
- 25-30 льгот
- 170 сотрудников AlphaCorp + 50 Beta Industries
- Промокоды с реалистичным распределением статусов: 40% REDEEMED, 30% ACTIVE, 15% EXPIRED, 10% REVOKED
- Погашения за последние 60 дней для графика redemption_trend

Счётчик assigned в аллокациях выводится из фактически созданных сотрудников, а не
задаётся константой: расхождение здесь сразу нарушило бы инвариант assigned <= allocated
и сломало выдачу мест на демо-стенде.
"""

from __future__ import annotations

import asyncio
import random
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

# Реалистичное распределение занятых мест
ALPHA_EMPLOYEES = {UserPlan.STANDARD: 100, UserPlan.PLUS: 50, UserPlan.PRO: 20}  # Итого 170 / 500 = 34%
BETA_EMPLOYEES = {UserPlan.STANDARD: 50}  # Итого 50 / 100 = 50%


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

    # --- Именованные сотрудники (для обратной совместимости) ---
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

    named_users = [alice, bob, charlie, alpha_admin, eve, platform_admin]
    session.add_all(named_users)

    # --- Массовая генерация сотрудников ---
    alpha_employees = []
    beta_employees = []

    first_names = ["John", "Emma", "Michael", "Sophia", "William", "Olivia", "James", "Ava",
                   "David", "Isabella", "Robert", "Mia", "Daniel", "Charlotte", "Joseph", "Amelia"]
    last_names = ["Anderson", "Martinez", "Garcia", "Rodriguez", "Wilson", "Moore", "Taylor",
                  "Thomas", "Jackson", "White", "Harris", "Martin", "Thompson", "Lee", "Clark"]

    counter = 1
    # AlphaCorp: 100 STANDARD (уже есть Alice=1), 50 PLUS (уже есть Bob=1), 20 PRO (уже есть Charlie=1)
    for plan, count in ALPHA_EMPLOYEES.items():
        actual_count = count - 1 if plan in {UserPlan.STANDARD, UserPlan.PLUS, UserPlan.PRO} else count
        for i in range(actual_count):
            user = User(
                email=f"employee_{counter:03d}@alphacorp.uz",
                password_hash=password_hash,
                first_name=random.choice(first_names),
                last_name=random.choice(last_names),
                role=UserRole.EMPLOYEE,
                plan=plan,
                is_active=random.random() > 0.05,  # 95% active
                company_id=alpha.id,
            )
            alpha_employees.append(user)
            counter += 1

    session.add_all(alpha_employees)

    # Beta Industries: 50 STANDARD (уже есть Eve=1)
    counter = 1
    for plan, count in BETA_EMPLOYEES.items():
        actual_count = count - 1 if plan == UserPlan.STANDARD else count
        for i in range(actual_count):
            user = User(
                email=f"employee_beta_{counter:03d}@betaindustries.uz",
                password_hash=password_hash,
                first_name=random.choice(first_names),
                last_name=random.choice(last_names),
                role=UserRole.EMPLOYEE,
                plan=plan,
                is_active=random.random() > 0.05,  # 95% active
                company_id=beta.id,
            )
            beta_employees.append(user)
            counter += 1

    session.add_all(beta_employees)
    await session.flush()

    # --- Места ---
    # Считаем занятые места по фактически созданным сотрудникам
    all_alpha_employees = [alice, bob, charlie] + alpha_employees
    all_beta_employees = [eve] + beta_employees
    alpha_assigned = Counter(u.plan for u in all_alpha_employees if u.plan is not None)
    beta_assigned = Counter(u.plan for u in all_beta_employees if u.plan is not None)

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

    # --- Мерчанты (расширено до 15) ---
    merchants_data = [
        ("FitZone Gym", "merchant@fitzone.uz", "Premium fitness club with modern equipment", BenefitCategory.SPORT),
        ("Yoga Studio Zen", "merchant@yog azenstudio.uz", "Yoga and meditation classes", BenefitCategory.SPORT),
        ("AquaSport Pool", "merchant@aquasport.uz", "Swimming pool and aqua fitness", BenefitCategory.SPORT),
        ("Lingua Center", "merchant@lingua.uz", "English, German and Korean language courses", BenefitCategory.EDUCATION),
        ("IT Academy", "merchant@itacademy.uz", "Online courses for IT professionals", BenefitCategory.EDUCATION),
        ("Business School Pro", "merchant@bizschool.uz", "MBA and executive education programs", BenefitCategory.EDUCATION),
        ("HealthCare Clinic", "merchant@healthcare.uz", "Dental care and general health checkups", BenefitCategory.HEALTH),
        ("Massage & SPA", "merchant@massage-spa.uz", "Therapeutic massage and spa treatments", BenefitCategory.HEALTH),
        ("LabAnalytics", "merchant@labanalytics.uz", "Medical laboratory tests and diagnostics", BenefitCategory.HEALTH),
        ("Food Hub", "merchant@foodhub.uz", "Healthy food delivery and canteen network", BenefitCategory.FOOD),
        ("Coffee & Co", "merchant@coffeeandco.uz", "Premium coffee shop chain", BenefitCategory.FOOD),
        ("CarShare Plus", "merchant@carshare.uz", "Car sharing and hourly rental service", BenefitCategory.TRANSPORT),
        ("Cinema Plus", "merchant@cinemaplus.uz", "Movie theater chain", BenefitCategory.ENTERTAINMENT),
        ("TechStore", "merchant@techstore.uz", "Electronics and gadgets retail", BenefitCategory.OTHER),
        ("CleanPro Laundry", "merchant@cleanpro.uz", "Dry cleaning and laundry services", BenefitCategory.OTHER),
    ]

    merchants = []
    for name, email, desc, cat in merchants_data:
        merchant = Merchant(
            name=name,
            email=email,
            status=MerchantStatus.ACTIVE,
            description=desc,
        )
        merchants.append(merchant)

    session.add_all(merchants)
    await session.flush()

    # Создать merchant-пользователей для первых 5 мерчантов
    merchant_users = []
    for i, merchant in enumerate(merchants[:5]):
        user = User(
            email=f"merchant.user{i+1}@{merchant.email.split('@')[1]}",
            password_hash=password_hash,
            first_name="Merchant",
            last_name=merchant.name.split()[0],
            role=UserRole.MERCHANT,
            is_active=True,
            merchant_id=merchant.id,
        )
        merchant_users.append(user)

    session.add_all(merchant_users)
    await session.flush()

    # --- Льготы (28 штук: по 2 на каждого мерчанта, кроме одного) ---
    benefits_data = [
        # SPORT (3 мерчанта × 2)
        ("Annual Gym Membership", "Full access to all gym facilities, group classes and personal trainer consultations",
         0, 365, 30, 1, {UserPlan.STANDARD: "5", UserPlan.PLUS: "15", UserPlan.PRO: "45"}),
        ("Personal Training Package", "10 sessions with certified personal trainer",
         0, 180, 60, 1, {UserPlan.STANDARD: "10", UserPlan.PLUS: "20", UserPlan.PRO: "50"}),

        ("Yoga Classes Subscription", "Unlimited monthly yoga and meditation classes",
         1, 270, 30, 2, {UserPlan.STANDARD: "7", UserPlan.PLUS: "18", UserPlan.PRO: "35"}),
        ("Yoga Retreat Weekend", "Weekend yoga retreat with accommodation",
         1, 120, 45, 1, {UserPlan.PLUS: "15", UserPlan.PRO: "40"}),

        ("Swimming Pool Membership", "Annual unlimited access to swimming pool and sauna",
         2, 365, 30, 1, {UserPlan.STANDARD: "8", UserPlan.PLUS: "20", UserPlan.PRO: "50"}),
        ("Aqua Fitness Classes", "Weekly aqua fitness group sessions",
         2, 180, 30, 2, {UserPlan.STANDARD: "5", UserPlan.PLUS: "12", UserPlan.PRO: "30"}),

        # EDUCATION (3 мерчанта × 2)
        ("Language Course Package", "Group lessons in English, German or Korean, three levels available",
         3, 270, 45, 1, {UserPlan.STANDARD: "10", UserPlan.PLUS: "25", UserPlan.PRO: "40"}),
        ("Individual Language Lessons", "10 private lessons with native speaker",
         3, 120, 60, 1, {UserPlan.PLUS: "20", UserPlan.PRO: "45"}),

        ("Online IT Course", "Full access to Python, JavaScript or DevOps learning tracks",
         4, 180, 60, 2, {UserPlan.STANDARD: "15", UserPlan.PLUS: "30", UserPlan.PRO: "60"}),
        ("IT Certification Prep", "Preparation course for AWS/Azure certification",
         4, 90, 30, 1, {UserPlan.PLUS: "25", UserPlan.PRO: "55"}),

        ("MBA Program Discount", "Discount on executive MBA program tuition",
         5, 365, 90, 1, {UserPlan.PRO: "70"}),
        ("Business Workshop Series", "4 business leadership workshops per quarter",
         5, 180, 60, 2, {UserPlan.PLUS: "20", UserPlan.PRO: "50"}),

        # HEALTH (3 мерчанта × 2)
        ("Dental Care Package", "Annual dental checkup and cleaning",
         6, 365, 60, 1, {UserPlan.STANDARD: "10", UserPlan.PLUS: "25", UserPlan.PRO: "50"}),
        ("Dental Treatment Discount", "Discount on all dental treatments",
         6, 365, 90, 3, {UserPlan.STANDARD: "5", UserPlan.PLUS: "15", UserPlan.PRO: "35"}),

        ("Massage Therapy Session", "60-minute therapeutic massage",
         7, 180, 30, 4, {UserPlan.STANDARD: "12", UserPlan.PLUS: "25", UserPlan.PRO: "40"}),
        ("SPA Day Package", "Full day spa with multiple treatments",
         7, 120, 45, 1, {UserPlan.PLUS: "20", UserPlan.PRO: "45"}),

        ("Health Screening Package", "Comprehensive medical checkup and lab tests",
         8, 365, 90, 1, {UserPlan.STANDARD: "15", UserPlan.PLUS: "30", UserPlan.PRO: "55"}),
        ("Lab Tests Discount", "20% off all laboratory diagnostic tests",
         8, 365, 60, 5, {UserPlan.STANDARD: "10", UserPlan.PLUS: "20", UserPlan.PRO: "35"}),

        # FOOD (2 мерчанта × 2)
        ("Business Lunch Subscription", "Daily business lunch delivery to the office",
         9, 120, 14, 3, {UserPlan.STANDARD: "10", UserPlan.PLUS: "25", UserPlan.PRO: "40"}),
        ("Catering Service Discount", "Discount on corporate event catering",
         9, 180, 30, 2, {UserPlan.STANDARD: "5", UserPlan.PLUS: "15", UserPlan.PRO: "30"}),

        ("Coffee Subscription", "Monthly coffee subscription with free delivery",
         10, 90, 30, 2, {UserPlan.STANDARD: "8", UserPlan.PLUS: "18", UserPlan.PRO: "35"}),
        ("Coffee Beans Package", "Premium coffee beans monthly delivery",
         10, 120, 30, 3, {UserPlan.STANDARD: "10", UserPlan.PLUS: "20", UserPlan.PRO: "40"}),

        # TRANSPORT
        ("CarShare Monthly Pass", "100 hours of car sharing per month",
         11, 365, 30, 1, {UserPlan.STANDARD: "12", UserPlan.PLUS: "25", UserPlan.PRO: "45"}),
        ("Weekend Car Rental", "Weekend car rental with insurance",
         11, 180, 30, 4, {UserPlan.STANDARD: "10", UserPlan.PLUS: "20", UserPlan.PRO: "40"}),

        # ENTERTAINMENT
        ("VIP Cinema Package", "Unlimited VIP cinema tickets and lounge access",
         12, 365, 90, 1, {UserPlan.PRO: "60"}),
        ("Movie Tickets Bundle", "10 standard movie tickets",
         12, 120, 30, 2, {UserPlan.STANDARD: "15", UserPlan.PLUS: "30", UserPlan.PRO: "50"}),

        # OTHER (2 мерчанта × 2)
        ("Gadgets Discount", "15% off all electronics and gadgets",
         13, 180, 60, 2, {UserPlan.STANDARD: "10", UserPlan.PLUS: "15", UserPlan.PRO: "25"}),
        ("Laptop Upgrade Program", "Discount on laptop purchase",
         13, 365, 90, 1, {UserPlan.PLUS: "20", UserPlan.PRO: "40"}),
    ]

    benefits = []
    for title, desc, merchant_idx, valid_days, promo_days, max_redemp, discounts in benefits_data:
        # Некоторые льготы истекли, другие долгосрочные
        is_expired = random.random() < 0.15  # 15% истекших
        if is_expired:
            valid_from = now - timedelta(days=90)
            valid_until = now - timedelta(days=random.randint(1, 30))
        else:
            valid_from = now - timedelta(days=random.randint(0, 30))
            valid_until = now + timedelta(days=valid_days)

        benefit = Benefit(
            title=title,
            description=desc,
            category=merchants_data[merchant_idx][3],  # category из merchants_data
            merchant_id=merchants[merchant_idx].id,
            is_active=not is_expired,
            destination_url=f"https://{merchants[merchant_idx].email.split('@')[1]}/corporate",
            valid_from=valid_from,
            valid_until=valid_until,
            usage_limit=None if random.random() > 0.2 else random.randint(50, 200),
            max_redemptions_per_employee=max_redemp,
            promo_valid_days=promo_days,
        )
        benefits.append((benefit, discounts))

    session.add_all([b for b, _ in benefits])
    await session.flush()

    # Создать BenefitPlanOffer для каждой льготы
    plan_offers = []
    for benefit, discounts in benefits:
        for plan, discount_str in discounts.items():
            offer = BenefitPlanOffer(
                benefit_id=benefit.id,
                plan=plan,
                discount_percent=Decimal(discount_str),
                is_available=True,
            )
            plan_offers.append(offer)

    session.add_all(plan_offers)
    await session.flush()

    # --- Массовая генерация промокодов и погашений ---
    # Каждому сотруднику по 1-3 промокода с реалистичным распределением
    # Статусы: 40% REDEEMED, 30% ACTIVE, 15% EXPIRED, 10% REVOKED, 5% OTHER

    all_employees = all_alpha_employees + all_beta_employees
    active_benefits = [b for b, _ in benefits if b.is_active]

    redemptions_and_promos = []

    for employee in all_employees[:150]:  # Ограничиваем для скорости: первые 150 сотрудников
        num_promos = random.randint(1, 3)
        for _ in range(num_promos):
            benefit, _ = random.choice(benefits)

            # Определить статус промокода
            status_rand = random.random()
            if status_rand < 0.40:  # 40% REDEEMED
                status = PromoCodeStatus.REDEEMED
                redemption_status = RedemptionStatus.REDEEMED
                days_ago = random.randint(1, 60)
                redeemed_at = now - timedelta(days=days_ago)
            elif status_rand < 0.70:  # 30% ACTIVE
                status = PromoCodeStatus.ACTIVE
                redemption_status = RedemptionStatus.ISSUED
                redeemed_at = None
            elif status_rand < 0.85:  # 15% EXPIRED
                status = PromoCodeStatus.EXPIRED
                redemption_status = RedemptionStatus.EXPIRED
                redeemed_at = None
            elif status_rand < 0.95:  # 10% REVOKED
                status = PromoCodeStatus.REVOKED
                redemption_status = RedemptionStatus.REVOKED
                redeemed_at = None
            else:  # 5% OTHER
                status = PromoCodeStatus.ACTIVE
                redemption_status = RedemptionStatus.ISSUED
                redeemed_at = None

            # Создать redemption
            redemption = BenefitRedemption(
                employee_id=employee.id,
                company_id=employee.company_id,
                benefit_id=benefit.id,
                status=redemption_status,
                redeemed_at=redeemed_at,
            )
            redemptions_and_promos.append(("redemption", redemption, benefit, employee, status, redeemed_at))

    # Добавить все redemptions
    session.add_all([r for t, r, *_ in redemptions_and_promos if t == "redemption"])
    await session.flush()

    # Создать промокоды для каждого redemption
    for _, redemption, benefit, employee, promo_status, redeemed_at in redemptions_and_promos:
        # Найти мерчанта по benefit.merchant_id
        merchant = next((m for m in merchants if m.id == benefit.merchant_id), merchants[0])

        promo = await issue_promo_code(
            db=session,
            benefit_id=benefit.id,
            employee_id=employee.id,
            redemption_id=redemption.id,
            merchant_name=merchant.name,
            promo_valid_days=benefit.promo_valid_days,
        )
        promo.status = promo_status
        if redeemed_at:
            promo.redeemed_at = redeemed_at
            if merchant_users:
                promo.redeemed_by_id = random.choice(merchant_users).id

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
    # Добавить несколько примеров audit logs
    if redemptions_and_promos:
        sample_redemption = redemptions_and_promos[0][1]  # Первое redemption
        sample_benefit = redemptions_and_promos[0][2]

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
                    entity_id=str(sample_redemption.id),
                    company_id=alpha.id,
                    meta={"benefit_id": str(sample_benefit.id)},
                ),
            ]
        )
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
    # Добавить несколько примеров audit logs
    if redemptions_and_promos:
        sample_redemption = redemptions_and_promos[0][1]  # Первое redemption
        sample_benefit = redemptions_and_promos[0][2]

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
                    entity_id=str(sample_redemption.id),
                    company_id=alpha.id,
                    meta={"benefit_id": str(sample_benefit.id)},
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
