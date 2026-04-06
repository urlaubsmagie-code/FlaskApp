"""Add composite indexes for query performance

Revision ID: p5_perf_idx2
Revises: p4_smoobu
Create Date: 2026-03-18
"""
from alembic import op

# revision identifiers
revision = 'p5_perf_idx2'
down_revision = 'p4_smoobu'
branch_labels = None
depends_on = None


def upgrade():
    # Composite index: message queries always filter by conversation_id + order by sent_at
    with op.batch_alter_table('message', schema=None) as batch_op:
        batch_op.create_index('ix_message_conv_sent', ['conversation_id', 'sent_at'])

    # Foreign key indexes for frequently joined/filtered columns
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.create_index('ix_conversation_user_id', ['user_id'])
        batch_op.create_index('ix_conversation_property_id', ['property_id'])

    with op.batch_alter_table('guest_detail', schema=None) as batch_op:
        batch_op.create_index('ix_guest_detail_source_message_id', ['source_message_id'])


def downgrade():
    with op.batch_alter_table('guest_detail', schema=None) as batch_op:
        batch_op.drop_index('ix_guest_detail_source_message_id')

    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.drop_index('ix_conversation_property_id')
        batch_op.drop_index('ix_conversation_user_id')

    with op.batch_alter_table('message', schema=None) as batch_op:
        batch_op.drop_index('ix_message_conv_sent')
