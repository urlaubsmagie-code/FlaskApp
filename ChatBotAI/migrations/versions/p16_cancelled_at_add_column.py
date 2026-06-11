"""Add Conversation.cancelled_at — tracks Smoobu cancelReservation webhook.

Revision ID: p16_cancelled_at
Revises: p15_last_message_at
Create Date: 2026-05-19

When Smoobu fires a cancelReservation webhook we set cancelled_at on the
matching Conversation. The team sees a "Storniert" label in the inbox so
they can decide whether the conversation still needs attention. We do NOT
change AI behavior, hide the conversation, or alter message content —
just record that the underlying reservation was cancelled.

Nullable column, no backfill. Existing rows stay NULL (= not cancelled).
"""
from alembic import op
import sqlalchemy as sa


revision = 'p16_cancelled_at'
down_revision = 'p15_last_message_at'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('conversation') as batch_op:
        batch_op.add_column(sa.Column('cancelled_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('conversation') as batch_op:
        batch_op.drop_column('cancelled_at')
