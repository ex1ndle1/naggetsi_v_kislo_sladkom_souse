"""Add Bitrix24 integration fields.

Revision ID: 002_bitrix_fields
Revises: 001_initial_schema
Create Date: 2026-08-16 12:45:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "002_bitrix_fields"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("bitrix_webhook_url", sa.String(length=512), nullable=True))
    op.add_column(
        "companies",
        sa.Column("bitrix_sync_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("users", sa.Column("external_bitrix_id", sa.Integer(), nullable=True))
    op.create_index("ix_users_external_bitrix_id", "users", ["external_bitrix_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_external_bitrix_id", table_name="users")
    op.drop_column("users", "external_bitrix_id")
    op.drop_column("companies", "bitrix_sync_enabled")
    op.drop_column("companies", "bitrix_webhook_url")
