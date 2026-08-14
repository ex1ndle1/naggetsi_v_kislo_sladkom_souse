"""Перечисления домена. StrEnum → в PostgreSQL создаются нативные enum-типы."""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """Роли платформы (ТЗ §14)."""

    EMPLOYEE = "EMPLOYEE"
    MERCHANT = "MERCHANT"
    COMPANY_ADMIN = "COMPANY_ADMIN"
    PLATFORM_ADMIN = "PLATFORM_ADMIN"


class CompanyStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class MerchantStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"


class BenefitCategory(StrEnum):
    """Категории льгот. Значения используются и в AI-промптах, и во фронте."""

    SPORT = "SPORT"
    EDUCATION = "EDUCATION"
    HEALTH = "HEALTH"
    FOOD = "FOOD"
    TRANSPORT = "TRANSPORT"
    ENTERTAINMENT = "ENTERTAINMENT"
    TECH = "TECH"
    OTHER = "OTHER"


class UserPlan(StrEnum):
    """Тарифные планы сотрудников (NEXUS30 §3)."""

    STANDARD = "STANDARD"
    PLUS = "PLUS"
    PRO = "PRO"


class InviteTokenStatus(StrEnum):
    """Статусы invite token (NEXUS30 §6)."""

    ACTIVE = "ACTIVE"
    USED = "USED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class PromoCodeStatus(StrEnum):
    """Статусы промокода (NEXUS30 §12)."""

    ISSUED = "ISSUED"
    REDEEMED = "REDEEMED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class RedemptionStatus(StrEnum):
    """Статусы активации льготы (NEXUS30 §13)."""

    ISSUED = "ISSUED"
    REDEEMED = "REDEEMED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class AuditAction(StrEnum):
    """Критические действия для audit log (NEXUS30 §16)."""

    USER_CREATED = "USER_CREATED"
    USER_BLOCKED = "USER_BLOCKED"
    USER_UNBLOCKED = "USER_UNBLOCKED"
    USER_LOGIN = "USER_LOGIN"
    USER_LOGIN_FAILED = "USER_LOGIN_FAILED"
    USER_LOGOUT = "USER_LOGOUT"
    ROLE_CHANGED = "ROLE_CHANGED"

    INVITE_CREATED = "INVITE_CREATED"
    INVITE_USED = "INVITE_USED"
    INVITE_EXPIRED = "INVITE_EXPIRED"

    PLAN_ASSIGNED = "PLAN_ASSIGNED"
    PLAN_CHANGED = "PLAN_CHANGED"

    COMPANY_CREATED = "COMPANY_CREATED"
    COMPANY_UPDATED = "COMPANY_UPDATED"

    MERCHANT_CREATED = "MERCHANT_CREATED"
    MERCHANT_UPDATED = "MERCHANT_UPDATED"
    MERCHANT_BLOCKED = "MERCHANT_BLOCKED"

    BENEFIT_CREATED = "BENEFIT_CREATED"
    BENEFIT_UPDATED = "BENEFIT_UPDATED"
    BENEFIT_DEACTIVATED = "BENEFIT_DEACTIVATED"

    PROMO_ISSUED = "PROMO_ISSUED"
    PROMO_REDEEMED = "PROMO_REDEEMED"
    PROMO_EXPIRED = "PROMO_EXPIRED"
    PROMO_REVOKED = "PROMO_REVOKED"

    REDEMPTION_CREATED = "REDEMPTION_CREATED"
    REDEMPTION_REJECTED = "REDEMPTION_REJECTED"

    ABUSE_DETECTED = "ABUSE_DETECTED"
    RATE_LIMIT_TRIGGERED = "RATE_LIMIT_TRIGGERED"

    AI_REQUEST = "AI_REQUEST"
    AI_ERROR = "AI_ERROR"


__all__ = [
    "AuditAction",
    "BenefitCategory",
    "CompanyStatus",
    "InviteTokenStatus",
    "MerchantStatus",
    "PromoCodeStatus",
    "RedemptionStatus",
    "UserPlan",
    "UserRole",
]
