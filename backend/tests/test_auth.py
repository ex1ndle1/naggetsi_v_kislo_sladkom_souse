"""Authentication tests for invite-only employee registration."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from app.companies.models import Company
from app.core.enums import CompanyStatus, UserPlan
from app.invites.service import create_invite_token
from app.plans.models import PlanAllocation


async def make_invite(db_session, email: str | None = None, plan: UserPlan = UserPlan.STANDARD) -> str:
    company = Company(name=f"Test Company {email or plan.value}", status=CompanyStatus.ACTIVE)
    db_session.add(company)
    await db_session.flush()
    db_session.add(PlanAllocation(company_id=company.id, plan=plan, allocated=2, assigned=0))
    _, token = await create_invite_token(
        db_session,
        company_id=company.id,
        plan=plan,
        created_by_id=None,
        email=email,
        expires_in_days=7,
    )
    await db_session.commit()
    return token


async def test_register_requires_invite(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "no-invite@example.com", "password": "TestPass123!", "first_name": "Test", "last_name": "User"},
    )
    assert response.status_code == 422


async def test_register_assigns_invited_plan(client: AsyncClient, db_session):
    token = await make_invite(db_session, "employee@example.com", UserPlan.PRO)
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "employee@example.com",
            "password": "TestPass123!",
            "first_name": "Test",
            "last_name": "User",
            "invite_token": token,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["role"] == "EMPLOYEE"
    assert data["plan"] == "PRO"


async def test_register_invite_is_single_use(client: AsyncClient, db_session):
    token = await make_invite(db_session, "single@example.com")
    payload = {"email": "single@example.com", "password": "TestPass123!", "first_name": "Test", "last_name": "User", "invite_token": token}
    assert (await client.post("/api/v1/auth/register", json=payload)).status_code == 201
    second = await client.post("/api/v1/auth/register", json=payload)
    assert second.status_code in {400, 409}


async def test_register_wrong_invite_email_is_rejected(client: AsyncClient, db_session):
    token = await make_invite(db_session, "bound@example.com")
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "other@example.com", "password": "TestPass123!", "first_name": "Test", "last_name": "User", "invite_token": token},
    )
    assert response.status_code in {400, 409}


async def test_register_expired_invite_is_rejected(client: AsyncClient, db_session):
    token = await make_invite(db_session, "expired@example.com")
    from sqlalchemy import update
    from app.invites.models import InviteToken
    await db_session.execute(update(InviteToken).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
    await db_session.commit()
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "expired@example.com", "password": "TestPass123!", "first_name": "Test", "last_name": "User", "invite_token": token},
    )
    assert response.status_code in {400, 409}


async def test_login_and_me(client: AsyncClient, db_session):
    token = await make_invite(db_session, "login@example.com")
    registration = await client.post(
        "/api/v1/auth/register",
        json={"email": "login@example.com", "password": "TestPass123!", "first_name": "Test", "last_name": "User", "invite_token": token},
    )
    assert registration.status_code == 201
    login = await client.post("/api/v1/auth/login", json={"email": "login@example.com", "password": "TestPass123!"})
    assert login.status_code == 200
    access = login.json()["access_token"]
    profile = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {access}"})
    assert profile.status_code == 200
    assert profile.json()["plan"] == "STANDARD"


async def test_login_wrong_password(client: AsyncClient, db_session):
    token = await make_invite(db_session, "wrongpass@example.com")
    await client.post("/api/v1/auth/register", json={"email": "wrongpass@example.com", "password": "TestPass123!", "first_name": "Test", "last_name": "User", "invite_token": token})
    response = await client.post("/api/v1/auth/login", json={"email": "wrongpass@example.com", "password": "WrongPassword!"})
    assert response.status_code == 401
