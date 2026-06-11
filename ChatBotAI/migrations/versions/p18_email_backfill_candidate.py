"""Add email_backfill_candidate table for the email reconciliation pass.

Revision ID: p18_email_backfill
Revises: p17_guest_dedup
Create Date: 2026-06-09

Stores guest messages discovered in Airbnb/Booking notification emails that
were not auto-inserted (low confidence). Reviewed via /chatbot/email-review.
"""
from alembic import op
import sqlalchemy as sa


revision = 'p18_email_backfill'
down_revision = 'p17_guest_dedup'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'email_backfill_candidate',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('gmail_message_id', sa.String(length=255), nullable=False),
        sa.Column('platform', sa.String(length=20), nullable=False),
        sa.Column('parsed_name', sa.String(length=255), nullable=True),
        sa.Column('parsed_text', sa.Text(), nullable=True),
        sa.Column('parsed_timestamp', sa.DateTime(), nullable=True),
        sa.Column('guessed_conversation_id', sa.Integer(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['guessed_conversation_id'], ['conversation.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_email_backfill_candidate_gmail_message_id',
                    'email_backfill_candidate', ['gmail_message_id'], unique=True)
    op.create_index('ix_email_backfill_candidate_status',
                    'email_backfill_candidate', ['status'], unique=False)


def downgrade():
    op.drop_index('ix_email_backfill_candidate_status', table_name='email_backfill_candidate')
    op.drop_index('ix_email_backfill_candidate_gmail_message_id', table_name='email_backfill_candidate')
    op.drop_table('email_backfill_candidate')
