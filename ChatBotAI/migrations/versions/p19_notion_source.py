"""Add Notion-sync provenance columns to knowledge_entry and reply_template.

Revision ID: p19_notion_source
Revises: p18_email_backfill
Create Date: 2026-06-17

Additive only. Existing rows default to source='manual', preserving behavior.
"""
from alembic import op
import sqlalchemy as sa

revision = 'p19_notion_source'
down_revision = 'p18_email_backfill'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('knowledge_entry') as batch:
        batch.add_column(sa.Column('source', sa.String(length=20), nullable=False, server_default='manual'))
        batch.add_column(sa.Column('notion_page_id', sa.String(length=64), nullable=True))
        batch.add_column(sa.Column('synced_at', sa.DateTime(), nullable=True))
    op.create_index('ix_knowledge_entry_notion_page_id', 'knowledge_entry', ['notion_page_id'])

    with op.batch_alter_table('reply_template') as batch:
        batch.add_column(sa.Column('source', sa.String(length=20), nullable=False, server_default='manual'))
        batch.add_column(sa.Column('notion_page_id', sa.String(length=64), nullable=True))
    op.create_index('ix_reply_template_notion_page_id', 'reply_template', ['notion_page_id'])


def downgrade():
    op.drop_index('ix_reply_template_notion_page_id', table_name='reply_template')
    op.drop_index('ix_knowledge_entry_notion_page_id', table_name='knowledge_entry')
    with op.batch_alter_table('reply_template') as batch:
        batch.drop_column('notion_page_id')
        batch.drop_column('source')
    with op.batch_alter_table('knowledge_entry') as batch:
        batch.drop_column('synced_at')
        batch.drop_column('notion_page_id')
        batch.drop_column('source')
