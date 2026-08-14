# Alembic migrations для corporate benefits platform
#
# Каждая миграция контролируется вручную и проходит ревью перед мёржем.
# create_all() нигде не вызывается — схема создаётся только через upgrade (ТЗ §30).

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.core.database import Base

# Импортируем все модели, чтобы они попали в Base.metadata.
from app.applications.models import Application  # noqa: F401
from app.audit.models import AuditLog  # noqa: F401
from app.benefits.models import Benefit  # noqa: F401
from app.budgets.models import CompanyBudget  # noqa: F401
from app.companies.models import Company  # noqa: F401
from app.merchants.models import Merchant  # noqa: F401
from app.payments.models import Payment  # noqa: F401
from app.transactions.models import Transaction  # noqa: F401
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


def run_migrations_online() -> None:
    """Online migrations: применяет к живой БД."""
    # Для Alembic используем синхронный движок (asyncpg+psycopg драйвер или psycopg2).
    # Alembic не поддерживает async напрямую.
    sync_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")

    connectable = engine_from_config(
        {"sqlalchemy.url": sync_url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
