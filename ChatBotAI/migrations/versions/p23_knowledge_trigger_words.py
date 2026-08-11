"""Add trigger_words to knowledge_entry and seed the Eskalation topics.

Revision ID: p23_knowledge_trigger_words
Revises: p22_smoobu_multi_account
Create Date: 2026-08-11

The escalation trigger words used to be a hardcoded tuple in MessageRouter,
invisible and uneditable for the team. They move into the Wissensdatenbank as
nine topic rows so the team owns them.

Additive: one nullable column plus nine global rows. The seed is skipped when
any escalation row already carries trigger words, so re-running is safe.
"""
from alembic import op
import sqlalchemy as sa

revision = 'p23_knowledge_trigger_words'
down_revision = 'p22_smoobu_multi_account'
branch_labels = None
depends_on = None

# (category, label, comma-separated trigger words)
SEED_TOPICS = (
    ('esc_emergency', 'Notfall',
     'notfall, notarzt, feuer, brennt, polizei, rettungsdienst, einbruch, '
     'unfall, verletzt, gasgeruch, emergency, urgent, asap, fire, police, '
     'ambulance, injured'),
    ('esc_maintenance', 'Wasserschaden / Schimmel',
     'wasserschaden, überschwemmt, überflutet, rohrbruch, schimmel, flood, '
     'flooded, water damage, leak, mold'),
    ('esc_maintenance', 'Kein Wasser / Strom / Heizung',
     'kein warmwasser, kein wasser, kein strom, stromausfall, heizung defekt, '
     'heizung geht nicht, heizung kaputt, no hot water, no water, no power, '
     'no electricity, heating not working'),
    # Broad, generic words — deliberately their own row so the team can delete
    # them without losing the specific topics above.
    ('esc_maintenance', 'Defekt / kaputt',
     'kaputt, funktioniert nicht, defekt, broken, not working'),
    ('esc_access', 'Aussperrung / Zugang',
     'ausgesperrt, eingesperrt, komme nicht rein, schlüssel verloren, '
     'code funktioniert nicht, türe geht nicht, tür geht nicht, locked out, '
     "lost the key, lost my key, code does not work, code doesn't work"),
    ('esc_payment', 'Zahlung / Erstattung',
     'rückerstattung, geld zurück, stornieren, storno, abbrechen, refund, '
     'money back, cancel my booking'),
    ('esc_other', 'Beschwerde / Rechtliches',
     'anwalt, rechtsanwalt, beschwerde, beschweren, lawyer, complaint'),
    ('esc_noise', 'Lärm',
     'lärm, laut, polizei gerufen'),
    ('esc_cleanliness', 'Sauberkeit / Ungeziefer',
     'dreckig, schmutzig, ungeziefer, bettwanzen, kakerlaken, bed bugs, '
     'cockroach, filthy, dirty'),
)


def _columns(conn, table):
    return {row[1] for row in conn.execute(sa.text(f'PRAGMA table_info({table})'))}


def upgrade():
    conn = op.get_bind()

    # Column — guarded because the app's startup schema-repair may have already
    # added it from the model metadata before this migration got to run.
    if 'trigger_words' not in _columns(conn, 'knowledge_entry'):
        with op.batch_alter_table('knowledge_entry') as batch:
            batch.add_column(sa.Column('trigger_words', sa.Text(), nullable=True))

    already = conn.execute(sa.text(
        "SELECT COUNT(*) FROM knowledge_entry "
        "WHERE category LIKE 'esc%' AND trigger_words IS NOT NULL "
        "AND TRIM(trigger_words) != ''"
    )).scalar()
    if already:
        return

    for sort_order, (category, label, words) in enumerate(SEED_TOPICS, start=1):
        conn.execute(
            sa.text(
                "INSERT INTO knowledge_entry "
                "(property_id, category, label, value, street, sort_order, "
                " source, trigger_words, created_at, updated_at) "
                "VALUES (NULL, :category, :label, '', NULL, :sort_order, "
                " 'manual', :words, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {'category': category, 'label': label,
             'sort_order': sort_order, 'words': words},
        )


def downgrade():
    conn = op.get_bind()
    for _category, label, words in SEED_TOPICS:
        conn.execute(
            sa.text("DELETE FROM knowledge_entry "
                    "WHERE label = :label AND property_id IS NULL "
                    "AND trigger_words = :words"),
            {'label': label, 'words': words},
        )
    with op.batch_alter_table('knowledge_entry') as batch:
        batch.drop_column('trigger_words')
