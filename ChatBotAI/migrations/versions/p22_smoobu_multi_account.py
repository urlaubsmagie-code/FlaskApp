"""Tag conversations and properties with their Smoobu account.

Revision ID: p22_smoobu_multi_account
Revises: p21_knowledge_street
Create Date: 2026-08-07

UMI now talks to more than one Smoobu account (the Sonnenhof apartment lives in
a separate one). Rows are tagged with the owning account id so sends and syncs
always use the right API key.

Additive and non-breaking: the new columns are nullable and NULL is read as
"the primary account", i.e. exactly today's behaviour. The backfill stamps the
existing account id when it is already known; otherwise the app self-heals on
the next sync cycle (SmoobuService.ensure_account_id).

Uniqueness: apartment ids are only unique *within* one Smoobu account, so the
guarantee becomes a unique index on (account, apartment). Plain indexes are used
rather than batch_alter_table constraint surgery — the live property table was
rebuilt by an earlier migration and no longer carries the original named
constraint, so dropping by name fails there.
"""
from alembic import op
import sqlalchemy as sa

revision = 'p22_smoobu_multi_account'
down_revision = 'p21_knowledge_street'
branch_labels = None
depends_on = None

CONV_IDX = 'ix_conversation_smoobu_account_id'
PROP_IDX = 'ix_property_smoobu_account_id'
PROP_UNIQ = 'uq_property_account_apartment'
LEGACY_PROP_UNIQ = 'uq_property_smoobu_apartment_id'


def _columns(conn, table):
    return {row[1] for row in conn.execute(sa.text(f'PRAGMA table_info({table})'))}


def _indexes(conn, table):
    return {row[1] for row in conn.execute(sa.text(f'PRAGMA index_list({table})'))}


def upgrade():
    conn = op.get_bind()

    # Columns — guarded because the app's startup schema-repair may have already
    # added them from the model metadata before this migration got to run.
    if 'smoobu_account_id' not in _columns(conn, 'conversation'):
        with op.batch_alter_table('conversation') as batch:
            batch.add_column(sa.Column('smoobu_account_id', sa.String(length=20), nullable=True))
    if 'smoobu_account_id' not in _columns(conn, 'property'):
        with op.batch_alter_table('property') as batch:
            batch.add_column(sa.Column('smoobu_account_id', sa.String(length=20), nullable=True))

    existing = _indexes(conn, 'conversation') | _indexes(conn, 'property')
    if CONV_IDX not in existing:
        op.create_index(CONV_IDX, 'conversation', ['smoobu_account_id'])
    if PROP_IDX not in existing:
        op.create_index(PROP_IDX, 'property', ['smoobu_account_id'])

    # The account-blind unique is wrong once a second account exists.
    if LEGACY_PROP_UNIQ in existing:
        op.drop_index(LEGACY_PROP_UNIQ, table_name='property')
    if PROP_UNIQ not in existing:
        op.create_index(PROP_UNIQ, 'property',
                        ['smoobu_account_id', 'smoobu_apartment_id'], unique=True)

    # Backfill: every existing Smoobu row belongs to the account connected today.
    row = conn.execute(sa.text(
        "SELECT value FROM ai_settings WHERE key = 'smoobu_account_id'"
    )).fetchone()
    account_id = (row[0] or '').strip() if row and row[0] else None
    if account_id:
        conn.execute(sa.text(
            "UPDATE conversation SET smoobu_account_id = :a "
            "WHERE smoobu_reservation_id IS NOT NULL AND smoobu_account_id IS NULL"
        ), {'a': account_id})
        conn.execute(sa.text(
            "UPDATE property SET smoobu_account_id = :a "
            "WHERE smoobu_apartment_id IS NOT NULL AND smoobu_account_id IS NULL"
        ), {'a': account_id})
    # If the id isn't stored yet (it is only written when a key is connected),
    # rows stay NULL — they still resolve to the primary account, and the next
    # daemon cycle stamps them via SmoobuService.ensure_account_id().


def downgrade():
    """Restore the old uniqueness rule; the two columns are left in place.

    Dropping a column in SQLite means rebuilding the table, and rebuilding
    `conversation` breaks the FTS5 triggers that reference it. An unused
    nullable column costs nothing, so the rollback only undoes the indexes —
    which is what actually changes behaviour.
    """
    conn = op.get_bind()
    existing = _indexes(conn, 'property') | _indexes(conn, 'conversation')

    if PROP_UNIQ in existing:
        op.drop_index(PROP_UNIQ, table_name='property')
    if PROP_IDX in existing:
        op.drop_index(PROP_IDX, table_name='property')
    if CONV_IDX in existing:
        op.drop_index(CONV_IDX, table_name='conversation')
    if LEGACY_PROP_UNIQ not in existing:
        op.create_index(LEGACY_PROP_UNIQ, 'property', ['smoobu_apartment_id'], unique=True)
