"""Add approval queue columns to message and conversation

Revision ID: p10_approval
Revises: p9_summary
Create Date: 2026-03-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'p10_approval'
down_revision = 'p9_summary'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('message', schema=None) as batch_op:
        batch_op.add_column(sa.Column('approval_status', sa.String(20), nullable=True))
        batch_op.add_column(sa.Column('approved_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('original_content', sa.Text(), nullable=True))
        batch_op.create_index(op.f('ix_message_approval_status'), ['approval_status'])

    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.add_column(sa.Column('auto_approve', sa.Boolean(), server_default='0', nullable=False))


def downgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.drop_column('auto_approve')

    with op.batch_alter_table('message', schema=None) as batch_op:
        batch_op.drop_index(op.f('ix_message_approval_status'))
        batch_op.drop_column('original_content')
        batch_op.drop_column('approved_at')
        batch_op.drop_column('approval_status')
