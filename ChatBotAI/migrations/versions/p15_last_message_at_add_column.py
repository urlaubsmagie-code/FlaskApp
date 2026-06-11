"""Add Conversation.last_message_at + backfill from MAX(message.sent_at).

Revision ID: p15_last_message_at
Revises: p14_uniq_platform_msg_id
Create Date: 2026-05-15

Inbox previously sorted by Conversation.updated_at, which gets bumped to
"now" for out-of-order synced messages and for any owner/AI reply. That
made our inbox order diverge from Smoobu's, which sorts by the real
message timestamp. This migration introduces a dedicated sort column
that always mirrors MAX(Message.sent_at). Backfill computes it from
existing messages; conversations with no messages fall back to
created_at.
"""
from alembic import op
import sqlalchemy as sa


revision = 'p15_last_message_at'
down_revision = 'p14_uniq_platform_msg_id'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # 1. Add the column (nullable initially so backfill can populate it).
    with op.batch_alter_table('conversation') as batch_op:
        batch_op.add_column(sa.Column('last_message_at', sa.DateTime(), nullable=True))

    # 2. Backfill: for each conversation, set last_message_at to the newest
    #    message's sent_at. Conversations with zero messages get created_at.
    conn.execute(sa.text("""
        UPDATE conversation
        SET last_message_at = COALESCE(
            (SELECT MAX(m.sent_at) FROM message m WHERE m.conversation_id = conversation.id),
            conversation.created_at,
            conversation.updated_at
        )
    """))

    # 3. Add index for inbox ORDER BY performance.
    op.create_index(
        'ix_conversation_last_message_at',
        'conversation',
        ['last_message_at'],
    )


def downgrade():
    op.drop_index('ix_conversation_last_message_at', table_name='conversation')
    with op.batch_alter_table('conversation') as batch_op:
        batch_op.drop_column('last_message_at')
