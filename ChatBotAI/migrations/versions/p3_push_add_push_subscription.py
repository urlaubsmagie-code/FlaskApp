"""add push_subscription table

Revision ID: p3_push
Revises: p2_auth
Create Date: 2026-03-11 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'p3_push'
down_revision = 'p2_auth'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('push_subscription',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('endpoint', sa.Text(), nullable=False),
        sa.Column('p256dh', sa.String(length=256), nullable=False),
        sa.Column('auth', sa.String(length=256), nullable=False),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_push_subscription_user_id_user'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_push_subscription')),
        sa.UniqueConstraint('endpoint', name=op.f('uq_push_subscription_endpoint'))
    )
    op.create_index(op.f('ix_push_subscription_user_id'), 'push_subscription', ['user_id'])


def downgrade():
    op.drop_index(op.f('ix_push_subscription_user_id'), table_name='push_subscription')
    op.drop_table('push_subscription')
