"""v3 ai usage ledgers and indexes

Revision ID: 004
Revises: 003
Create Date: 2026-11-06 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = '004_v3_ai_usage_ledgers_and_indexes'
down_revision = '003_v2_commercial_saas_platform'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Create ai_usage_ledgers table
    op.create_table(
        'ai_usage_ledgers',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('org_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=True),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('operation_type', sa.String(length=100), nullable=False, server_default='chat'),
        sa.Column('prompt_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completion_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('estimated_cost_usd', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=datetime.utcnow),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_ai_ledger_org_created', 'ai_usage_ledgers', ['org_id', 'created_at'], unique=False)
    op.create_index('ix_ai_usage_ledgers_org_id', 'ai_usage_ledgers', ['org_id'], unique=False)
    op.create_index('ix_ai_usage_ledgers_provider', 'ai_usage_ledgers', ['provider'], unique=False)
    op.create_index('ix_ai_usage_ledgers_created_at', 'ai_usage_ledgers', ['created_at'], unique=False)

def downgrade() -> None:
    op.drop_index('ix_ai_usage_ledgers_created_at', table_name='ai_usage_ledgers')
    op.drop_index('ix_ai_usage_ledgers_provider', table_name='ai_usage_ledgers')
    op.drop_index('ix_ai_usage_ledgers_org_id', table_name='ai_usage_ledgers')
    op.drop_index('idx_ai_ledger_org_created', table_name='ai_usage_ledgers')
    op.drop_table('ai_usage_ledgers')
