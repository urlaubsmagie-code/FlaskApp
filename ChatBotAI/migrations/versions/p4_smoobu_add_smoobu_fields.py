"""Add Smoobu integration fields

Revision ID: p4_smoobu
Revises: p3_push
Create Date: 2026-03-16
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'p4_smoobu'
down_revision = 'p3_push'
branch_labels = None
depends_on = None


def upgrade():
    # Guest: smoobu_guest_id
    with op.batch_alter_table('guest', schema=None) as batch_op:
        batch_op.add_column(sa.Column('smoobu_guest_id', sa.String(100), nullable=True))
        batch_op.create_index('ix_guest_smoobu_guest_id', ['smoobu_guest_id'])

    # Conversation: smoobu_reservation_id
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.add_column(sa.Column('smoobu_reservation_id', sa.String(100), nullable=True))
        batch_op.create_index('ix_conversation_smoobu_reservation_id', ['smoobu_reservation_id'])

    # Property: smoobu_apartment_id
    with op.batch_alter_table('property', schema=None) as batch_op:
        batch_op.add_column(sa.Column('smoobu_apartment_id', sa.String(100), nullable=True))
        batch_op.create_index('ix_property_smoobu_apartment_id', ['smoobu_apartment_id'])
        batch_op.create_unique_constraint('uq_property_smoobu_apartment_id', ['smoobu_apartment_id'])


def downgrade():
    with op.batch_alter_table('property', schema=None) as batch_op:
        batch_op.drop_constraint('uq_property_smoobu_apartment_id', type_='unique')
        batch_op.drop_index('ix_property_smoobu_apartment_id')
        batch_op.drop_column('smoobu_apartment_id')

    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.drop_index('ix_conversation_smoobu_reservation_id')
        batch_op.drop_column('smoobu_reservation_id')

    with op.batch_alter_table('guest', schema=None) as batch_op:
        batch_op.drop_index('ix_guest_smoobu_guest_id')
        batch_op.drop_column('smoobu_guest_id')
