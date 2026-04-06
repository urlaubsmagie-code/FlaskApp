"""Add user_id to message for sender tracking

Revision ID: p11_msg_user
Revises: p10_approval
Create Date: 2026-03-27
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'p11_msg_user'
down_revision = 'p10_approval'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('message', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_message_user_id', 'user', ['user_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('message', schema=None) as batch_op:
        batch_op.drop_constraint('fk_message_user_id', type_='foreignkey')
        batch_op.drop_column('user_id')
