"""Add last_seen to user and user_session table for online-time tracking

Revision ID: p12_sessions
Revises: p11_msg_user
Create Date: 2026-03-30
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'p12_sessions'
down_revision = 'p11_msg_user'
branch_labels = None
depends_on = None


def upgrade():
    # Add last_seen to user table
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_seen', sa.DateTime(), nullable=True))

    # Create user_session table
    op.create_table(
        'user_session',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('last_active_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_user_session_user_id', 'user_session', ['user_id'])
    op.create_index('ix_user_session_started_at', 'user_session', ['started_at'])


def downgrade():
    op.drop_index('ix_user_session_started_at', table_name='user_session')
    op.drop_index('ix_user_session_user_id', table_name='user_session')
    op.drop_table('user_session')

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('last_seen')
