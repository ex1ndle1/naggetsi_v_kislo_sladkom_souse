"""Initial schema: NEXUS30 refactored model (plans, promo codes, redemptions)

Создаёт нативные PG enum-типы, таблицы в правильном порядке (FK-зависимости).

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-08-14 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------------------------
    # Enum-типы
    # ---------------------------------------------------------------------------
    op.execute(
        "CREATE TYPE user_role AS ENUM "
        "('EMPLOYEE', 'MERCHANT', 'COMPANY_ADMIN', 'PLATFORM_ADMIN')"
    )
    op.execute("CREATE TYPE user_plan AS ENUM ('STANDARD', 'PLUS', 'PRO')")
    op.execute("CREATE TYPE company_status AS ENUM ('ACTIVE', 'SUSPENDED')")
    op.execute("CREATE TYPE merchant_status AS ENUM ('PENDING', 'ACTIVE', 'BLOCKED')")
    op.execute(
        "CREATE TYPE benefit_category AS ENUM "
        "('SPORT', 'EDUCATION', 'HEALTH', 'FOOD', 'TRANSPORT', 'ENTERTAINMENT', 'TECH', 'OTHER')"
    )
    op.execute("CREATE TYPE invite_token_status AS ENUM ('ACTIVE', 'USED', 'EXPIRED', 'REVOKED')")
    op.execute("CREATE TYPE promo_code_status AS ENUM ('ISSUED', 'REDEEMED', 'EXPIRED', 'REVOKED')")
    op.execute("CREATE TYPE redemption_status AS ENUM ('ISSUED', 'REDEEMED', 'EXPIRED', 'CANCELLED')")
    op.execute(
        "CREATE TYPE audit_action AS ENUM ("
        "'USER_CREATED', 'USER_BLOCKED', 'USER_UNBLOCKED', 'USER_LOGIN', 'USER_LOGIN_FAILED', 'USER_LOGOUT', "
        "'ROLE_CHANGED', "
        "'INVITE_CREATED', 'INVITE_USED', 'INVITE_EXPIRED', "
        "'PLAN_ASSIGNED', 'PLAN_CHANGED', "
        "'COMPANY_CREATED', 'COMPANY_UPDATED', "
        "'MERCHANT_CREATED', 'MERCHANT_UPDATED', 'MERCHANT_BLOCKED', "
        "'BENEFIT_CREATED', 'BENEFIT_UPDATED', 'BENEFIT_DEACTIVATED', "
        "'PROMO_ISSUED', 'PROMO_REDEEMED', 'PROMO_EXPIRED', 'PROMO_REVOKED', "
        "'REDEMPTION_CREATED', 'REDEMPTION_REJECTED', "
        "'ABUSE_DETECTED', 'RATE_LIMIT_TRIGGERED', "
        "'AI_REQUEST', 'AI_ERROR')"
    )

    # ---------------------------------------------------------------------------
    # Таблицы
    # ---------------------------------------------------------------------------
    op.create_table(
        'companies',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('status', postgresql.ENUM(name='company_status', create_type=False), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_companies')),
        sa.UniqueConstraint('name', name=op.f('uq_companies_name'))
    )
    op.create_index(op.f('ix_companies_name'), 'companies', ['name'], unique=False)

    op.create_table(
        'merchants',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('status', postgresql.ENUM(name='merchant_status', create_type=False), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_merchants')),
        sa.UniqueConstraint('email', name=op.f('uq_merchants_email'))
    )
    op.create_index(op.f('ix_merchants_name'), 'merchants', ['name'], unique=False)
    op.create_index(op.f('ix_merchants_email'), 'merchants', ['email'], unique=False)

    op.create_table(
        'users',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=False),
        sa.Column('last_name', sa.String(length=100), nullable=False),
        sa.Column('role', postgresql.ENUM(name='user_role', create_type=False), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('plan', postgresql.ENUM(name='user_plan', create_type=False), nullable=True),
        sa.Column('company_id', sa.UUID(), nullable=True),
        sa.Column('merchant_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_users_company_id_companies'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['merchant_id'], ['merchants.id'], name=op.f('fk_users_merchant_id_merchants'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
        sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=False)
    op.create_index(op.f('ix_users_role'), 'users', ['role'], unique=False)
    op.create_index(op.f('ix_users_is_active'), 'users', ['is_active'], unique=False)
    op.create_index(op.f('ix_users_plan'), 'users', ['plan'], unique=False)
    op.create_index(op.f('ix_users_company_id'), 'users', ['company_id'], unique=False)
    op.create_index(op.f('ix_users_merchant_id'), 'users', ['merchant_id'], unique=False)

    op.create_table(
        'plan_allocations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('plan', postgresql.ENUM(name='user_plan', create_type=False), nullable=False),
        sa.Column('allocated', sa.Integer(), nullable=False),
        sa.Column('assigned', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_plan_allocations_company_id_companies'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_plan_allocations')),
        sa.UniqueConstraint('company_id', 'plan', name='uq_plan_allocation_company_plan'),
        sa.CheckConstraint('allocated >= 0', name='ck_plan_allocation_allocated_non_negative'),
        sa.CheckConstraint('assigned >= 0', name='ck_plan_allocation_assigned_non_negative'),
        sa.CheckConstraint('assigned <= allocated', name='ck_plan_allocation_assigned_within_allocated')
    )
    op.create_index(op.f('ix_plan_allocations_company_id'), 'plan_allocations', ['company_id'], unique=False)
    op.create_index(op.f('ix_plan_allocations_plan'), 'plan_allocations', ['plan'], unique=False)

    op.create_table(
        'invite_tokens',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('plan', postgresql.ENUM(name='user_plan', create_type=False), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=True),
        sa.Column('status', postgresql.ENUM(name='invite_token_status', create_type=False), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by_id', sa.UUID(), nullable=True),
        sa.Column('used_by_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_invite_tokens_company_id_companies'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_invite_tokens_created_by_id_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['used_by_id'], ['users.id'], name=op.f('fk_invite_tokens_used_by_id_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_invite_tokens')),
        sa.UniqueConstraint('token_hash', name=op.f('uq_invite_tokens_token_hash'))
    )
    op.create_index(op.f('ix_invite_tokens_token_hash'), 'invite_tokens', ['token_hash'], unique=False)
    op.create_index(op.f('ix_invite_tokens_company_id'), 'invite_tokens', ['company_id'], unique=False)
    op.create_index(op.f('ix_invite_tokens_email'), 'invite_tokens', ['email'], unique=False)
    op.create_index(op.f('ix_invite_tokens_status'), 'invite_tokens', ['status'], unique=False)
    op.create_index(op.f('ix_invite_tokens_created_by_id'), 'invite_tokens', ['created_by_id'], unique=False)

    op.create_table(
        'benefits',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('category', postgresql.ENUM(name='benefit_category', create_type=False), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('destination_url', sa.String(length=2048), nullable=True),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=True),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('usage_limit', sa.Integer(), nullable=True),
        sa.Column('max_redemptions_per_employee', sa.Integer(), nullable=False, comment='1 = одноразовая льгота'),
        sa.Column('promo_valid_days', sa.Integer(), nullable=False),
        sa.Column('merchant_id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['merchant_id'], ['merchants.id'], name=op.f('fk_benefits_merchant_id_merchants'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_benefits_company_id_companies'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_benefits'))
    )
    op.create_index(op.f('ix_benefits_title'), 'benefits', ['title'], unique=False)
    op.create_index(op.f('ix_benefits_category'), 'benefits', ['category'], unique=False)
    op.create_index(op.f('ix_benefits_is_active'), 'benefits', ['is_active'], unique=False)
    op.create_index(op.f('ix_benefits_merchant_id'), 'benefits', ['merchant_id'], unique=False)
    op.create_index(op.f('ix_benefits_company_id'), 'benefits', ['company_id'], unique=False)

    op.create_table(
        'benefit_plan_offers',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('benefit_id', sa.UUID(), nullable=False),
        sa.Column('plan', postgresql.ENUM(name='user_plan', create_type=False), nullable=False),
        sa.Column('discount_percent', sa.Numeric(precision=5, scale=2), nullable=False, comment='Процент скидки: 0.00-100.00'),
        sa.Column('is_available', sa.Boolean(), nullable=False, comment='Можно временно отключить оффер для плана'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['benefit_id'], ['benefits.id'], name=op.f('fk_benefit_plan_offers_benefit_id_benefits'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_benefit_plan_offers')),
        sa.UniqueConstraint('benefit_id', 'plan', name='uq_benefit_plan_offer'),
        sa.CheckConstraint('discount_percent >= 0 AND discount_percent <= 100', name='ck_discount_percent_range')
    )
    op.create_index(op.f('ix_benefit_plan_offers_benefit_id'), 'benefit_plan_offers', ['benefit_id'], unique=False)
    op.create_index(op.f('ix_benefit_plan_offers_plan'), 'benefit_plan_offers', ['plan'], unique=False)

    op.create_table(
        'benefit_redemptions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('employee_id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('benefit_id', sa.UUID(), nullable=False),
        sa.Column('status', postgresql.ENUM(name='redemption_status', create_type=False), nullable=False),
        sa.Column('redeemed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['users.id'], name=op.f('fk_benefit_redemptions_employee_id_users'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_benefit_redemptions_company_id_companies'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['benefit_id'], ['benefits.id'], name=op.f('fk_benefit_redemptions_benefit_id_benefits'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_benefit_redemptions'))
    )
    op.create_index(op.f('ix_benefit_redemptions_employee_id'), 'benefit_redemptions', ['employee_id'], unique=False)
    op.create_index(op.f('ix_benefit_redemptions_company_id'), 'benefit_redemptions', ['company_id'], unique=False)
    op.create_index(op.f('ix_benefit_redemptions_benefit_id'), 'benefit_redemptions', ['benefit_id'], unique=False)
    op.create_index(op.f('ix_benefit_redemptions_status'), 'benefit_redemptions', ['status'], unique=False)

    op.create_table(
        'promo_codes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False, comment='FIT-8XK29-QJ4M7'),
        sa.Column('benefit_id', sa.UUID(), nullable=False),
        sa.Column('employee_id', sa.UUID(), nullable=False),
        sa.Column('redemption_id', sa.UUID(), nullable=True),
        sa.Column('status', postgresql.ENUM(name='promo_code_status', create_type=False), nullable=False),
        sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('redeemed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('redeemed_by_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['benefit_id'], ['benefits.id'], name=op.f('fk_promo_codes_benefit_id_benefits'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['employee_id'], ['users.id'], name=op.f('fk_promo_codes_employee_id_users'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['redemption_id'], ['benefit_redemptions.id'], name=op.f('fk_promo_codes_redemption_id_benefit_redemptions'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['redeemed_by_id'], ['users.id'], name=op.f('fk_promo_codes_redeemed_by_id_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_promo_codes')),
        sa.UniqueConstraint('code', name=op.f('uq_promo_codes_code'))
    )
    op.create_index(op.f('ix_promo_codes_code'), 'promo_codes', ['code'], unique=False)
    op.create_index(op.f('ix_promo_codes_benefit_id'), 'promo_codes', ['benefit_id'], unique=False)
    op.create_index(op.f('ix_promo_codes_employee_id'), 'promo_codes', ['employee_id'], unique=False)
    op.create_index(op.f('ix_promo_codes_redemption_id'), 'promo_codes', ['redemption_id'], unique=False)
    op.create_index(op.f('ix_promo_codes_status'), 'promo_codes', ['status'], unique=False)

    op.create_table(
        'audit_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('actor_id', sa.UUID(), nullable=True),
        sa.Column('company_id', sa.UUID(), nullable=True),
        sa.Column('action', postgresql.ENUM(name='audit_action', create_type=False), nullable=False),
        sa.Column('entity_type', sa.String(length=100), nullable=True),
        sa.Column('entity_id', sa.String(length=255), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], name=op.f('fk_audit_logs_actor_id_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_audit_logs_company_id_companies'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_logs'))
    )
    op.create_index(op.f('ix_audit_logs_actor_id'), 'audit_logs', ['actor_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_company_id'), 'audit_logs', ['company_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_entity_type'), 'audit_logs', ['entity_type'], unique=False)
    op.create_index(op.f('ix_audit_logs_entity_id'), 'audit_logs', ['entity_id'], unique=False)


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('promo_codes')
    op.drop_table('benefit_redemptions')
    op.drop_table('benefit_plan_offers')
    op.drop_table('benefits')
    op.drop_table('invite_tokens')
    op.drop_table('plan_allocations')
    op.drop_table('users')
    op.drop_table('merchants')
    op.drop_table('companies')

    op.execute('DROP TYPE IF EXISTS audit_action')
    op.execute('DROP TYPE IF EXISTS redemption_status')
    op.execute('DROP TYPE IF EXISTS promo_code_status')
    op.execute('DROP TYPE IF EXISTS invite_token_status')
    op.execute('DROP TYPE IF EXISTS benefit_category')
    op.execute('DROP TYPE IF EXISTS merchant_status')
    op.execute('DROP TYPE IF EXISTS company_status')
    op.execute('DROP TYPE IF EXISTS user_plan')
    op.execute('DROP TYPE IF EXISTS user_role')
