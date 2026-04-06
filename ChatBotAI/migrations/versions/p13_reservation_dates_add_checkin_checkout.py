"""Add check_in and check_out date columns to conversation

Revision ID: p13_reservation_dates
Revises: p12_sessions
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'p13_reservation_dates'
down_revision = 'p12_sessions'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.add_column(sa.Column('check_in', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('check_out', sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.drop_column('check_out')
        batch_op.drop_column('check_in')
