"""Add street scope to property and knowledge_entry.

Revision ID: p21_knowledge_street
Revises: p20_problem_report
Create Date: 2026-08-03

Additive. Backfills property.street from the first comma-part of the existing
address so street-scoped knowledge works without waiting for a Smoobu resync.
"""
from alembic import op
import sqlalchemy as sa

revision = 'p21_knowledge_street'
down_revision = 'p20_problem_report'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('property') as batch:
        batch.add_column(sa.Column('street', sa.String(length=200), nullable=True))
    with op.batch_alter_table('knowledge_entry') as batch:
        batch.add_column(sa.Column('street', sa.String(length=200), nullable=True))
    op.create_index('ix_knowledge_entry_street', 'knowledge_entry', ['street'])

    # Backfill property.street from address element 0 ("street, zip, city, country").
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, address FROM property WHERE address IS NOT NULL AND address != ''"
    )).fetchall()
    for row in rows:
        street = (row[1] or '').split(',')[0].strip()
        if street:
            conn.execute(sa.text("UPDATE property SET street=:s WHERE id=:i"),
                         {"s": street, "i": row[0]})


def downgrade():
    op.drop_index('ix_knowledge_entry_street', table_name='knowledge_entry')
    with op.batch_alter_table('knowledge_entry') as batch:
        batch.drop_column('street')
    with op.batch_alter_table('property') as batch:
        batch.drop_column('street')
