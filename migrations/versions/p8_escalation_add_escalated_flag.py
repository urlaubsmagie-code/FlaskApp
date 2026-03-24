"""Add escalated flag and timestamp to conversation

Revision ID: p8_escalation
Revises: p7_readcursor
Create Date: 2026-03-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'p8_escalation'
down_revision = 'p7_readcursor'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.add_column(sa.Column('escalated', sa.Boolean(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('escalated_at', sa.DateTime(), nullable=True))
        batch_op.create_index(op.f('ix_conversation_escalated'), ['escalated'])


def downgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.drop_index(op.f('ix_conversation_escalated'))
        batch_op.drop_column('escalated_at')
        batch_op.drop_column('escalated')
