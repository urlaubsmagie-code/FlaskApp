"""Add read cursor and sync watermark columns to conversation

Revision ID: p7_readcursor
Revises: p6_knowledge
Create Date: 2026-03-23
"""
from alembic import op
import sqlalchemy as sa

revision = 'p7_readcursor'
down_revision = 'p6_knowledge'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_read_message_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_synced_message_at', sa.DateTime(), nullable=True))
        batch_op.create_foreign_key(
            op.f('fk_conversation_last_read_message_id_message'),
            'message', ['last_read_message_id'], ['id'],
            ondelete='SET NULL'
        )

    # Backfill: for conversations marked as read, set cursor to their latest message
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE conversation
        SET last_read_message_id = (
            SELECT MAX(m.id) FROM message m WHERE m.conversation_id = conversation.id
        )
        WHERE is_read = 1
    """))
    # Backfill: set last_synced_message_at to the latest message sent_at per conversation
    conn.execute(sa.text("""
        UPDATE conversation
        SET last_synced_message_at = (
            SELECT MAX(m.sent_at) FROM message m WHERE m.conversation_id = conversation.id
        )
    """))


def downgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('fk_conversation_last_read_message_id_message'), type_='foreignkey')
        batch_op.drop_column('last_synced_message_at')
        batch_op.drop_column('last_read_message_id')
