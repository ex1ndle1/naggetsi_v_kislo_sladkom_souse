# Alembic migrations для corporate benefits platform
#
# Каждая миграция контролируется вручную и проходит ревью перед мёржем.
# create_all() нигде не вызывается — схема создаётся только через upgrade (ТЗ §30).

import asyncio
from logging.config import fileConfig

from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Импортируем все модели, чтобы они попали в Base.metadata.
from app.audit.models import AuditLog  # noqa: F401
from app.benefits.models import Benefit  # noqa: F401
from app.benefits.plan_offers import BenefitPlanOffer  # noqa: F401
from app.companies.models import Company  # noqa: F401
from app.core.config import settings
from app.core.database import Base
from app.invites.models import InviteToken  # noqa: F401
from app.merchants.models import Merchant  # noqa: F401
from app.plans.models import PlanAllocation  # noqa: F401
from app.promo_codes.models import PromoCode  # noqa: F401
from app.redemptions.models import BenefitRedemption  # noqa: F401
from app.users.models import User  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Подставляем реальный database_url из окружения.
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Offline migrations: генерирует SQL без подключения к БД."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Online migrations: применяет к живой БД.

    Движок асинхронный, потому что в зависимостях проекта есть только asyncpg;
    синхронного драйвера (psycopg2) нет, и добавлять второй драйвер ради alembic
    незачем — сами миграции выполняются в run_sync.
    """
    connectable = async_engine_from_config(
        {"sqlalchemy.url": settings.database_url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
