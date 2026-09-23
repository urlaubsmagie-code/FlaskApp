"""Add is_internal to knowledge_entry and flag the known team-only rows.

Revision ID: p24_knowledge_is_internal
Revises: p23_knowledge_trigger_words
Create Date: 2026-09-04

Since the whole Wissensdatenbank goes into the rich guest-reply prompt, the
team's internal working notes (invoicing process, office hours, how to phrase
things to guests) reach the model that writes to guests. `is_internal` keeps
them in the Wissensdatenbank for the team but out of the prompt.

Additive and conservative: the column defaults to 0, so every entry stays
guest-facing unless it is on the list below or the team ticks the box. The
seed matches on exact label + global scope and never overwrites a row that is
already flagged, so re-running is safe.
"""
from alembic import op
import sqlalchemy as sa

revision = 'p24_knowledge_is_internal'
down_revision = 'p23_knowledge_trigger_words'
branch_labels = None
depends_on = None

# Global entries that are working instructions for the team, not guest answers.
# Identified 2026-09-04 by reading every non-escalation entry in prod.
INTERNAL_LABELS = (
    'Vorgehen',                          # Smoobu/invoice bookkeeping rules
    'Rechnungen',                        # invoicing process + internal mail address
    'Kurtaxe Konto',                     # invoice creation + tax rate
    'Büro',                              # a colleague's office hours and location
    'Hausmeister/Reinigungskraft in Wohnung',   # coaching on what to tell guests
    'Unbedruckte Karte erhalten',        # addressed to the team, not the guest
)


def _columns(conn, table):
    return {row[1] for row in conn.execute(sa.text(f'PRAGMA table_info({table})'))}


def upgrade():
    conn = op.get_bind()

    # Guarded: the app's startup schema-repair may have added it from the model
    # metadata before this migration ran.
    if 'is_internal' not in _columns(conn, 'knowledge_entry'):
        with op.batch_alter_table('knowledge_entry') as batch:
            batch.add_column(sa.Column('is_internal', sa.Boolean(), nullable=False,
                                       server_default='0'))

    for label in INTERNAL_LABELS:
        conn.execute(
            sa.text("UPDATE knowledge_entry SET is_internal = 1 "
                    "WHERE label = :label AND property_id IS NULL "
                    "AND is_internal = 0"),
            {'label': label},
        )


def downgrade():
    with op.batch_alter_table('knowledge_entry') as batch:
        batch.drop_column('is_internal')
