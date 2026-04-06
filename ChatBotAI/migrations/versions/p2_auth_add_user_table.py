"""add user table and conversation user_id

Revision ID: p2_auth
Revises: p1_perf_idx
Create Date: 2026-03-03 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'p2_auth'
down_revision = 'p1_perf_idx'
branch_labels = None
depends_on = None


def upgrade():
    # Create user table
    op.create_table('user',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=80), nullable=False),
        sa.Column('display_name', sa.String(length=200), nullable=False),
        sa.Column('password_hash', sa.String(length=256), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_user')),
        sa.UniqueConstraint('username', name=op.f('uq_user_username'))
    )
    op.create_index(op.f('ix_user_username'), 'user', ['username'], unique=True)

    # Add user_id FK to conversation
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            op.f('fk_conversation_user_id_user'),
            'user', ['user_id'], ['id'],
            ondelete='SET NULL'
        )


def downgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('fk_conversation_user_id_user'), type_='foreignkey')
        batch_op.drop_column('user_id')

    op.drop_index(op.f('ix_user_username'), table_name='user')
    op.drop_table('user')
