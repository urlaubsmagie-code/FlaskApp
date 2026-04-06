"""add auto_respond to conversation

Revision ID: b873bfba6705
Revises: 6a66ca2c2d11
Create Date: 2026-02-25 10:24:32.612541

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b873bfba6705'
down_revision = '6a66ca2c2d11'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.add_column(sa.Column('auto_respond', sa.Boolean(), server_default='0', nullable=False))


def downgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.drop_column('auto_respond')
