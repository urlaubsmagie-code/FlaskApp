"""Dedupe message.platform_message_id and add partial unique index.

Revision ID: p14_uniq_platform_msg_id
Revises: p13_reservation_dates
Create Date: 2026-05-13

Background: a race condition between concurrent Smoobu sync paths
(background daemon + manual full-sync route + per-conversation sync route)
allowed the same Smoobu message to be inserted twice. The schema had no
DB-level uniqueness on platform_message_id, so the check-then-insert
pattern in the code did not catch it. This migration:

  1. Repoints conversation.last_read_message_id from soon-to-be-deleted
     duplicate rows to the surviving (lowest-id) row.
  2. Deletes duplicate rows (keeps MIN(id) per platform_message_id).
  3. Creates a partial UNIQUE index on platform_message_id WHERE NOT NULL.

The code in services/smoobu_service.py and services/message_router.py
catches IntegrityError on the insert paths so the new constraint is safe.
"""
from alembic import op
import sqlalchemy as sa


revision = 'p14_uniq_platform_msg_id'
down_revision = 'p13_reservation_dates'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # Step 1: repoint any conversation.last_read_message_id that currently
    # points to a row we're about to delete. Move the pointer to the
    # surviving lowest-id row for the same platform_message_id.
    conn.execute(sa.text("""
        UPDATE conversation
        SET last_read_message_id = (
            SELECT MIN(m2.id) FROM message m2
            WHERE m2.platform_message_id = (
                SELECT m1.platform_message_id FROM message m1
                WHERE m1.id = conversation.last_read_message_id
            )
        )
        WHERE last_read_message_id IN (
            SELECT id FROM message
            WHERE platform_message_id IS NOT NULL
            AND id NOT IN (
                SELECT MIN(id) FROM message
                WHERE platform_message_id IS NOT NULL
                GROUP BY platform_message_id
            )
        )
    """))

    # Step 2: delete duplicate message rows (keep the earliest, MIN(id)).
    conn.execute(sa.text("""
        DELETE FROM message
        WHERE platform_message_id IS NOT NULL
        AND id NOT IN (
            SELECT MIN(id) FROM message
            WHERE platform_message_id IS NOT NULL
            GROUP BY platform_message_id
        )
    """))

    # Step 3: enforce uniqueness going forward.
    # SQLite supports partial indexes — NULL platform_message_id values
    # (locally-sent messages awaiting sync backfill) are exempted.
    conn.execute(sa.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS ix_message_platform_message_id_unique
        ON message (platform_message_id)
        WHERE platform_message_id IS NOT NULL
    """))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text(
        "DROP INDEX IF EXISTS ix_message_platform_message_id_unique"
    ))
    # Cannot un-delete the duplicates — not reversible.
