"""Add FTS5 search index

Revision ID: 6a66ca2c2d11
Revises: ef8fc18f76c4
Create Date: 2026-02-18 12:18:05.373730

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6a66ca2c2d11'
down_revision = 'ef8fc18f76c4'
branch_labels = None
depends_on = None


def upgrade():
    # Create FTS5 virtual table for message search
    # NOT using external content table because we need denormalized data from JOINs
    # Tokenizer: porter (stemming) + unicode61 (international) + diacritics removal
    op.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5(
            content,
            guest_name,
            subject,
            tokenize='porter unicode61 remove_diacritics 2'
        )
    """)

    # INSERT trigger - index new messages with denormalized guest name and subject
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS message_ai AFTER INSERT ON message BEGIN
            INSERT INTO message_fts(rowid, content, guest_name, subject)
            SELECT new.id, new.content, g.name, c.subject
            FROM conversation c
            JOIN guest g ON c.guest_id = g.id
            WHERE c.id = new.conversation_id;
        END
    """)

    # DELETE trigger - remove from index when message deleted
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS message_ad AFTER DELETE ON message BEGIN
            DELETE FROM message_fts WHERE rowid = old.id;
        END
    """)

    # UPDATE trigger - re-index when message content changes
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS message_au AFTER UPDATE ON message BEGIN
            DELETE FROM message_fts WHERE rowid = old.id;
            INSERT INTO message_fts(rowid, content, guest_name, subject)
            SELECT new.id, new.content, g.name, c.subject
            FROM conversation c
            JOIN guest g ON c.guest_id = g.id
            WHERE c.id = new.conversation_id;
        END
    """)

    # Populate index with existing messages
    op.execute("""
        INSERT INTO message_fts(rowid, content, guest_name, subject)
        SELECT m.id, m.content, g.name, c.subject
        FROM message m
        JOIN conversation c ON m.conversation_id = c.id
        JOIN guest g ON c.guest_id = g.id
    """)


def downgrade():
    # Drop triggers first
    op.execute("DROP TRIGGER IF EXISTS message_au")
    op.execute("DROP TRIGGER IF EXISTS message_ad")
    op.execute("DROP TRIGGER IF EXISTS message_ai")
    # Drop virtual table
    op.execute("DROP TABLE IF EXISTS message_fts")
