"""transactional_fencing_and_memento_cleanup

Revision ID: 002_transactional_fencing_and_memento_cleanup
Revises: 001_initial_complete_schema
Create Date: 2026-11-06 12:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '002_transactional_fencing_and_memento_cleanup'
down_revision: Union[str, Sequence[str], None] = '001_initial_complete_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Add fencing_generation to assessments
    with op.batch_alter_table('assessments') as batch_op:
        batch_op.add_column(
            sa.Column('fencing_generation', sa.Integer(), server_default='1', nullable=False)
        )

    # 2. Add fencing_generation to review_jobs
    with op.batch_alter_table('review_jobs') as batch_op:
        batch_op.add_column(
            sa.Column('fencing_generation', sa.Integer(), server_default='1', nullable=False)
        )

    # 3. Add fencing_generation to historical_assessments
    with op.batch_alter_table('historical_assessments') as batch_op:
        batch_op.add_column(
            sa.Column('fencing_generation', sa.Integer(), server_default='1', nullable=False)
        )

    # 4. Drop obsolete Memento cloud fields from integration_settings
    with op.batch_alter_table('integration_settings') as batch_op:
        batch_op.drop_column('memento_api_key')
        batch_op.drop_column('memento_endpoint')

def downgrade() -> None:
    with op.batch_alter_table('integration_settings') as batch_op:
        batch_op.add_column(
            sa.Column('memento_endpoint', sa.String(length=255), server_default='https://api.memento.ai/v1', nullable=True)
        )
        batch_op.add_column(
            sa.Column('memento_api_key', sa.String(length=500), server_default='', nullable=True)
        )

    with op.batch_alter_table('historical_assessments') as batch_op:
        batch_op.drop_column('fencing_generation')

    with op.batch_alter_table('review_jobs') as batch_op:
        batch_op.drop_column('fencing_generation')

    with op.batch_alter_table('assessments') as batch_op:
        batch_op.drop_column('fencing_generation')

