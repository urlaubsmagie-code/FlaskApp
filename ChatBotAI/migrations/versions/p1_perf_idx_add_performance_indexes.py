"""add_performance_indexes

Revision ID: p1_perf_idx
Revises: b873bfba6705
Create Date: 2026-03-03 10:09:10.629252

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'p1_perf_idx'
down_revision = 'b873bfba6705'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.create_index('ix_conversation_updated_at', ['updated_at'])
        batch_op.create_index('ix_conversation_status', ['status'])


def downgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.drop_index('ix_conversation_status')
        batch_op.drop_index('ix_conversation_updated_at')
