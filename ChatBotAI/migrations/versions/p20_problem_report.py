"""Add problem_report table for team-reported problems/ideas.

Revision ID: p20_problem_report
Revises: p19_notion_source
Create Date: 2026-07-08

Additive only — new table, no changes to existing tables.
"""
from alembic import op
import sqlalchemy as sa

revision = 'p20_problem_report'
down_revision = 'p19_notion_source'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'problem_report',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=True),
        sa.Column('category', sa.String(length=30), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('page_url', sa.String(length=500), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='open'),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversation.id']),
        sa.ForeignKeyConstraint(['resolved_by'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_problem_report_status', 'problem_report', ['status'])
    op.create_index('ix_problem_report_created_at', 'problem_report', ['created_at'])
    op.create_index('ix_problem_report_user_id', 'problem_report', ['user_id'])
    op.create_index('ix_problem_report_conversation_id', 'problem_report', ['conversation_id'])


def downgrade():
    op.drop_index('ix_problem_report_conversation_id', table_name='problem_report')
    op.drop_index('ix_problem_report_user_id', table_name='problem_report')
    op.drop_index('ix_problem_report_created_at', table_name='problem_report')
    op.drop_index('ix_problem_report_status', table_name='problem_report')
    op.drop_table('problem_report')
