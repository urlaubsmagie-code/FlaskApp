"""Add AI summary columns to conversation

Revision ID: p9_summary
Revises: p8_escalation
Create Date: 2026-03-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'p9_summary'
down_revision = 'p8_escalation'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ai_summary', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('ai_summary_through_id', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.drop_column('ai_summary_through_id')
        batch_op.drop_column('ai_summary')
