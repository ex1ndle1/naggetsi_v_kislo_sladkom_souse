"""Pytest configuration using the production Alembic schema.

Isolation strategy
------------------
Один event_loop на всю сессию (scope="session") — asyncpg создаёт соединения
в этом цикле и закрывает их тоже в нём, без "Event loop is closed" ошибок.
TRUNCATE перед каждым тестом заменяет transaction-rollback подход: работает
надёжнее при вложенных commit() в хелперах вроде make_invite.
"""

import asyncio
import os
import subprocess
from collections.abc import AsyncGenerator, Generator
from typing import Any

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import get_session
from app.main import app

TEST_DATABASE = "benefits_test"
TEST_DATABASE_URL = settings.database_url.rsplit("/", 1)[0] + f"/{TEST_DATABASE}"

# Единый движок для тестов. Без NullPool — пул нужен для session-loop совместимости.
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionFactory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

# Порядок учитывает FK-зависимости: сначала зависимые таблицы, потом родители.
_TRUNCATE_ORDER = [
    "audit_logs",
    "benefit_redemptions",
    "promo_codes",
    "benefit_plan_offers",
    "benefits",
    "invite_tokens",
    "plan_allocations",
    "users",
    "merchants",
    "companies",
]


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, Any, None]:
    """Session-scoped event loop: все async-фикстуры и тесты работают в одном цикле,
    поэтому asyncpg не пытается закрыть соединения через уже закрытый loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


async def _ensure_test_database() -> None:
    admin = await asyncpg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
        database="postgres",
    )
    try:
        exists = await admin.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", TEST_DATABASE
        )
        if not exists:
            await admin.execute(f'CREATE DATABASE "{TEST_DATABASE}"')
    finally:
        await admin.close()


def _migrate_test_database() -> None:
    env = os.environ.copy()
    env["POSTGRES_DB"] = TEST_DATABASE
    subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
        check=True,
    )


@pytest_asyncio.fixture(scope="session", autouse=True)
async def migrated_database() -> AsyncGenerator[None, None]:
    """Создаёт БД и применяет миграции один раз для всей сессии."""
    await _ensure_test_database()
    _migrate_test_database()
    yield
    await test_engine.dispose()


@pytest_asyncio.fixture(scope="function", autouse=True)
async def clean_db() -> AsyncGenerator[None, None]:
    """TRUNCATE всех изменяемых таблиц перед каждым тестом."""
    async with test_engine.begin() as conn:
        for tbl in _TRUNCATE_ORDER:
            await conn.execute(text(f'TRUNCATE "{tbl}" RESTART IDENTITY CASCADE'))
    yield


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionFactory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def demo_password() -> str:
    return "Demo1234!"
