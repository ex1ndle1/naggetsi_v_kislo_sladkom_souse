"""AI router: персонализированные рекомендации и аналитика."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.ai.service import assess_fraud_risk, generate_company_report, get_benefit_recommendations
from app.applications.models import Application
from app.benefits.models import Benefit
from app.core.deps import CurrentUser, DbSession, require_roles
from app.core.enums import ApplicationStatus, UserRole
from app.core.errors import BadRequest, Forbidden, NotFound

router = APIRouter(prefix="/ai", tags=["ai"])


class RecommendationsResponse(BaseModel):
    """Рекомендации льгот для сотрудника."""

    recommended: list[UUID]
    fallback_used: bool


class FraudAssessmentRequest(BaseModel):
    """Запрос оценки fraud риска."""

    application_id: UUID


class FraudAssessmentResponse(BaseModel):
    """Результат оценки fraud."""

    risk_score: float
    reason: str
    blocked: bool


class CompanyReportResponse(BaseModel):
    """Аналитический отчёт компании."""

    report: str
    fallback_used: bool


@router.get("/recommendations", response_model=RecommendationsResponse)
async def get_recommendations(
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require_roles(UserRole.EMPLOYEE))],
) -> RecommendationsResponse:
    """Персонализированные рекомендации льгот (AI сценарий 1).

    Fallback: сортировка по популярности (количество заявок).
    """
    if not user.company_id:
        raise BadRequest(message="Employee must be associated with a company")

    # Получаем доступные льготы
    stmt = select(Benefit).where(
        Benefit.is_active == True,  # noqa: E712
        (Benefit.company_id.is_(None)) | (Benefit.company_id == user.company_id),
    )
    benefits = list((await db.scalars(stmt)).all())

    if not benefits:
        return RecommendationsResponse(recommended=[], fallback_used=True)

    # Пробуем AI рекомендации
    employee_profile = {
        "role": user.role.value,
        "company_id": str(user.company_id),
        "user_id": str(user.user_id),
    }
    benefits_data = [
        {
            "id": str(b.id),
            "title": b.title,
            "category": b.category.value,
            "price": float(b.price),
        }
        for b in benefits
    ]

    ai_recommendations = await get_benefit_recommendations(employee_profile, benefits_data)

    if ai_recommendations:
        # AI вернул результат
        recommended_ids = [UUID(bid) for bid in ai_recommendations if bid in [str(b.id) for b in benefits]]
        return RecommendationsResponse(recommended=recommended_ids, fallback_used=False)

    # Fallback: сортировка по популярности
    popularity_stmt = (
        select(Benefit.id, func.count(Application.id).label("count"))
        .outerjoin(Application, Benefit.id == Application.benefit_id)
        .where(Benefit.id.in_([b.id for b in benefits]))
        .group_by(Benefit.id)
        .order_by(func.count(Application.id).desc())
    )
    popular = await db.execute(popularity_stmt)
    recommended_ids = [row[0] for row in popular.all()]

    return RecommendationsResponse(recommended=recommended_ids, fallback_used=True)


@router.post("/fraud-check", response_model=FraudAssessmentResponse)
async def check_fraud(
    payload: FraudAssessmentRequest,
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require_roles(UserRole.COMPANY_ADMIN, UserRole.PLATFORM_ADMIN))],
) -> FraudAssessmentResponse:
    """Оценка риска fraud для заявки (AI сценарий 2).

    Fallback: пропускаем проверку (risk_score=0.0).
    """
    # Проверяем заявку
    stmt = select(Application).where(Application.id == payload.application_id)
    application = await db.scalar(stmt)

    if not application:
        raise NotFound(message="Application not found")

    # Tenant isolation
    if user.role == UserRole.COMPANY_ADMIN and application.company_id != user.company_id:
        raise Forbidden(message="Access denied")

    # AI оценка fraud
    application_data = {
        "id": str(application.id),
        "employee_id": str(application.employee_id),
        "benefit_id": str(application.benefit_id),
        "price": float(application.price),
        "status": application.status.value,
    }

    assessment = await assess_fraud_risk(application_data)

    if assessment:
        return FraudAssessmentResponse(
            risk_score=assessment["risk_score"],
            reason=assessment["reason"],
            blocked=assessment["blocked"],
        )

    # Fallback: нет AI — пропускаем
    return FraudAssessmentResponse(risk_score=0.0, reason="AI unavailable", blocked=False)


@router.get("/company-report", response_model=CompanyReportResponse)
async def get_company_report(
    db: DbSession,
    user: Annotated[CurrentUser, Depends(require_roles(UserRole.COMPANY_ADMIN, UserRole.PLATFORM_ADMIN))],
) -> CompanyReportResponse:
    """Генерация аналитического отчёта компании (AI сценарий 3).

    Fallback: базовая статистика без AI-анализа.
    """
    if user.role == UserRole.COMPANY_ADMIN and not user.company_id:
        raise BadRequest(message="COMPANY_ADMIN must be associated with a company")

    company_id = user.company_id if user.role == UserRole.COMPANY_ADMIN else None

    # Собираем данные для отчёта
    applications_stmt = select(Application)
    if company_id:
        applications_stmt = applications_stmt.where(Application.company_id == company_id)

    applications = list((await db.scalars(applications_stmt)).all())

    company_data = {
        "company_id": str(company_id) if company_id else "all",
        "total_applications": len(applications),
        "applications_by_status": {
            status.value: len([a for a in applications if a.status == status])
            for status in ApplicationStatus
        },
        "total_spent": sum(a.price for a in applications if a.status == ApplicationStatus.PAID),
    }

    # AI генерация отчёта
    ai_report = await generate_company_report(company_data)

    if ai_report:
        return CompanyReportResponse(report=ai_report, fallback_used=False)

    # Fallback: простая статистика
    fallback_report = f"""Company Analytics Report

Total Applications: {company_data['total_applications']}
Total Spent: {company_data['total_spent']} UZS

Applications by Status:
"""
    for status, count in company_data["applications_by_status"].items():
        fallback_report += f"- {status}: {count}\n"

    fallback_report += "\n(AI analysis unavailable)"

    return CompanyReportResponse(report=fallback_report, fallback_used=True)
