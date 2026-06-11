"""Dedupe Guest by smoobu_guest_id and add partial unique index.

Revision ID: p17_guest_dedup
Revises: p16_cancelled_at
Create Date: 2026-05-21

Background:
    The 175-duplicate Steven Amaya bug happened because concurrent webhooks
    ran check-then-insert on Guest.smoobu_guest_id with no uniqueness
    guarantee. This migration:

    1. Merges duplicate Guest rows sharing the same non-NULL smoobu_guest_id.
       The oldest id wins (it has the longest history). All Conversations,
       GuestDetails, etc. are reassigned to the winner; losers are deleted.

    2. Adds a partial unique index on Guest.smoobu_guest_id WHERE NOT NULL
       so future concurrent inserts hit IntegrityError instead of duplicating.

Code that creates Guest rows must now catch IntegrityError and re-query
(handled in services/smoobu_service.py and memory_service.find_or_create_guest).
"""
from alembic import op
import sqlalchemy as sa


revision = 'p17_guest_dedup'
down_revision = 'p16_cancelled_at'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()

    # Find duplicate smoobu_guest_id groups
    dup_rows = bind.execute(sa.text("""
        SELECT smoobu_guest_id, GROUP_CONCAT(id) AS ids, COUNT(*) AS n
        FROM guest
        WHERE smoobu_guest_id IS NOT NULL AND smoobu_guest_id != ''
        GROUP BY smoobu_guest_id
        HAVING n > 1
    """)).fetchall()

    for row in dup_rows:
        ids = [int(x) for x in row.ids.split(',')]
        ids.sort()
        winner = ids[0]
        losers = ids[1:]
        loser_list = ','.join(str(i) for i in losers)

        # Reassign foreign keys to the winner
        bind.execute(sa.text(
            f"UPDATE conversation SET guest_id = {winner} WHERE guest_id IN ({loser_list})"
        ))
        bind.execute(sa.text(
            f"UPDATE guest_detail SET guest_id = {winner} WHERE guest_id IN ({loser_list})"
        ))

        # Delete loser guest rows
        bind.execute(sa.text(
            f"DELETE FROM guest WHERE id IN ({loser_list})"
        ))

    # Add partial unique index — NULLs allowed but non-NULL must be unique
    op.create_index(
        'uq_guest_smoobu_guest_id',
        'guest',
        ['smoobu_guest_id'],
        unique=True,
        sqlite_where=sa.text('smoobu_guest_id IS NOT NULL')
    )


def downgrade():
    op.drop_index('uq_guest_smoobu_guest_id', table_name='guest')
