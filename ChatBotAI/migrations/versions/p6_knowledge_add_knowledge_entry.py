"""Add knowledge_entry table for AI knowledge base

Revision ID: p6_knowledge
Revises: p5_perf_idx2
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'p6_knowledge'
down_revision = 'p5_perf_idx2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'knowledge_entry',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('property_id', sa.Integer(), sa.ForeignKey('property.id', ondelete='CASCADE'), nullable=True),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('label', sa.String(200), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_knowledge_entry_property_id', 'knowledge_entry', ['property_id'])
    op.create_index('ix_knowledge_entry_property_category', 'knowledge_entry', ['property_id', 'category'])


def downgrade():
    op.drop_index('ix_knowledge_entry_property_category', table_name='knowledge_entry')
    op.drop_index('ix_knowledge_entry_property_id', table_name='knowledge_entry')
    op.drop_table('knowledge_entry')
