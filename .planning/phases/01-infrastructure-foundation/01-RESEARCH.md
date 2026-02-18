# Phase 1: Infrastructure Foundation - Research

**Researched:** 2026-02-18
**Domain:** SQLite infrastructure (WAL mode, FTS5 full-text search, Flask-Migrate schema migrations)
**Confidence:** HIGH

## Summary

This phase establishes three critical database infrastructure components: schema migrations via Flask-Migrate, SQLite WAL mode for concurrent access, and FTS5 full-text search indexing. All three technologies are mature and well-documented, with established patterns for Flask/SQLAlchemy applications.

Flask-Migrate wraps Alembic and requires `render_as_batch=True` for SQLite (enabled by default in v4.0+). WAL mode is a persistent PRAGMA that enables concurrent readers/writers. FTS5 requires external content tables with triggers to stay synchronized with source data.

**Primary recommendation:** Use Flask-Migrate with naming conventions for constraints, enable WAL via SQLAlchemy event listener, and implement FTS5 as an external content table with database triggers (not Python hooks) to maintain synchronization.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Index **everything searchable**: message content, guest names, and subjects/topics
- **Exclude** guest memory items (GuestDetail) from FTS - memories visible on profiles, not through search
- Existing conversations default to **is_read = True** (no blue dots on initial launch)
- Backup **recommended** before migrations - warn user and confirm, but don't block
- Migrations are **manual** - run via explicit command (`flask db upgrade`), not auto-applied on startup

### Claude's Discretion
- Search result ranking algorithm (bm25 vs chronological)
- Case/accent handling in FTS
- Migration rollback strategy (all-or-nothing vs partial)
- Exact FTS5 configuration and tokenizer

### Deferred Ideas (OUT OF SCOPE)
None - discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFRA-01 | System adds `is_read` field to Conversation model for unread tracking | Flask-Migrate schema migration adds Boolean column with default True |
| INFRA-02 | System configures SQLite WAL mode for concurrent polling access | SQLAlchemy event listener on `connect` executes `PRAGMA journal_mode=WAL` |
| INFRA-03 | System implements full-text search index on Message.content | FTS5 external content table with triggers on Message, plus Guest.name and Conversation.subject |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Flask-Migrate | >= 4.0.0 | Schema migrations via Alembic | Official Flask extension by Miguel Grinberg; `render_as_batch=True` default since v4.0 |
| Alembic | >= 1.10 | Underlying migration engine | Industry-standard SQLAlchemy migrations; batch mode solves SQLite limitations |
| SQLite FTS5 | Built-in | Full-text search | Ships with Python's sqlite3 module; no external dependency required |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| SQLAlchemy events | Built-in | WAL mode PRAGMA | Set connection pragmas on every new connection |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| FTS5 external content | FTS5 content table | External content saves ~50% storage but requires trigger maintenance |
| Database triggers | SQLAlchemy event listeners | Triggers are more reliable (work outside Python), but harder to test |
| Flask-Migrate | Raw Alembic | Flask-Migrate adds CLI integration and sensible defaults |

**Installation:**
```bash
pip install Flask-Migrate>=4.0.0
```

## Architecture Patterns

### Project Structure Additions
```
ChatBotAI/
├── migrations/           # Created by flask db init
│   ├── versions/         # Individual migration scripts
│   ├── alembic.ini       # Alembic configuration
│   ├── env.py            # Migration environment
│   └── script.py.mako    # Template for new migrations
├── models.py             # Add is_read field to Conversation
└── app.py                # Add Migrate initialization, WAL event
```

### Pattern 1: Flask-Migrate Initialization

**What:** Initialize Flask-Migrate with batch mode for SQLite compatibility
**When to use:** App factory pattern with Flask-SQLAlchemy

```python
# Source: https://flask-migrate.readthedocs.io/
from flask_migrate import Migrate

migrate = Migrate()

def create_app(config_class=None):
    app = Flask(__name__)
    # ... config loading ...
    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)
    return app
```

### Pattern 2: Naming Conventions for Constraints

**What:** Define constraint naming convention to enable batch migrations
**When to use:** Before first migration; prevents unnamed constraint errors

```python
# Source: https://flask-sqlalchemy.readthedocs.io/en/stable/models/
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

metadata = MetaData(naming_convention=convention)
db = SQLAlchemy(metadata=metadata)
```

### Pattern 3: SQLite WAL Mode via Event Listener

**What:** Enable WAL mode on every database connection
**When to use:** At engine creation time

```python
# Source: https://til.simonwillison.net/sqlite/enabling-wal-mode
from sqlalchemy import event

def setup_wal_mode(app):
    """Enable WAL mode for SQLite databases."""
    with app.app_context():
        engine = db.engine

        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()
```

### Pattern 4: FTS5 External Content Table

**What:** FTS5 table that reads content from source tables, index only
**When to use:** When you need to search existing data without duplication

```sql
-- Source: https://www.sqlite.org/fts5.html
-- Create external content FTS5 table
CREATE VIRTUAL TABLE message_fts USING fts5(
    content,
    guest_name,
    subject,
    content='message',
    content_rowid='id',
    tokenize='porter unicode61 remove_diacritics 2'
);
```

### Pattern 5: FTS5 Synchronization Triggers

**What:** Database triggers to keep FTS index synchronized with source data
**When to use:** Mandatory for external content FTS tables

```sql
-- Source: https://www.sqlite.org/fts5.html#external_content_tables
-- INSERT trigger
CREATE TRIGGER message_ai AFTER INSERT ON message BEGIN
    INSERT INTO message_fts(rowid, content, guest_name, subject)
    SELECT new.id, new.content, g.name, c.subject
    FROM conversation c
    JOIN guest g ON c.guest_id = g.id
    WHERE c.id = new.conversation_id;
END;

-- DELETE trigger (must provide old values)
CREATE TRIGGER message_ad AFTER DELETE ON message BEGIN
    INSERT INTO message_fts(message_fts, rowid, content, guest_name, subject)
    SELECT 'delete', old.id, old.content, g.name, c.subject
    FROM conversation c
    JOIN guest g ON c.guest_id = g.id
    WHERE c.id = old.conversation_id;
END;

-- UPDATE trigger (delete old, insert new)
CREATE TRIGGER message_au AFTER UPDATE ON message BEGIN
    INSERT INTO message_fts(message_fts, rowid, content, guest_name, subject)
    SELECT 'delete', old.id, old.content, g.name, c.subject
    FROM conversation c
    JOIN guest g ON c.guest_id = g.id
    WHERE c.id = old.conversation_id;

    INSERT INTO message_fts(rowid, content, guest_name, subject)
    SELECT new.id, new.content, g.name, c.subject
    FROM conversation c
    JOIN guest g ON c.guest_id = g.id
    WHERE c.id = new.conversation_id;
END;
```

### Anti-Patterns to Avoid

- **Hand-rolling migration SQL:** Always use Alembic; it handles edge cases and rollbacks
- **Python-side FTS sync:** Using SQLAlchemy events for FTS sync is fragile; database triggers ensure consistency even for direct SQL operations
- **Unnamed constraints:** Always use naming conventions; batch mode cannot drop unnamed constraints
- **Setting WAL once at app start:** WAL mode persists, but busy_timeout must be set per connection

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Schema migrations | Custom SQL scripts | Flask-Migrate + Alembic | Handles versioning, rollbacks, batch mode for SQLite |
| Full-text search | LIKE queries | FTS5 virtual tables | Orders of magnitude faster; supports ranking, stemming |
| FTS synchronization | Application-level sync | Database triggers | Triggers work for all writes, not just ORM operations |
| Constraint naming | Manual naming | SQLAlchemy naming_convention | Automatic, consistent, required for batch migrations |

**Key insight:** SQLite has quirks (limited ALTER TABLE, external content tables) that are well-solved by established patterns. Custom solutions will miss edge cases.

## Common Pitfalls

### Pitfall 1: Unnamed Constraints Break Batch Migrations

**What goes wrong:** `batch_op.drop_constraint(None, ...)` fails silently
**Why it happens:** SQLAlchemy doesn't auto-name constraints; Alembic can't reference `None`
**How to avoid:** Define `naming_convention` on MetaData before creating any models
**Warning signs:** `None` appearing in generated migration scripts

### Pitfall 2: FTS5 Not Compiled In

**What goes wrong:** `sqlite3.OperationalError: no such module: fts5`
**Why it happens:** Some Python distributions don't include FTS5 in sqlite3
**How to avoid:** Test FTS5 availability at startup; provide clear error message
**Warning signs:** Works on dev machine (Conda/recent Python), fails on older servers

```python
def check_fts5_support():
    """Verify FTS5 is available in the SQLite library."""
    import sqlite3
    try:
        conn = sqlite3.connect(':memory:')
        conn.execute('CREATE VIRTUAL TABLE test USING fts5(content)')
        conn.close()
        return True
    except sqlite3.OperationalError:
        return False
```

### Pitfall 3: WAL Mode on Network Filesystem

**What goes wrong:** Corruption, locking errors, unpredictable behavior
**Why it happens:** WAL requires shared memory; network FS can't provide this
**How to avoid:** SQLite database MUST be on local filesystem
**Warning signs:** Database on NFS, SMB, or cloud-mounted storage

### Pitfall 4: FTS External Content Out of Sync

**What goes wrong:** Search returns deleted items, misses new items
**Why it happens:** Triggers not created, or triggers created after data exists
**How to avoid:** Create triggers before inserting data; run `rebuild` command for existing data
**Warning signs:** Inconsistent search results, stale matches

```sql
-- Rebuild FTS index from source table
INSERT INTO message_fts(message_fts) VALUES('rebuild');
```

### Pitfall 5: Adding Non-Nullable Column to Existing Table

**What goes wrong:** Migration fails with "cannot add NOT NULL column"
**Why it happens:** Existing rows have no value for new column
**How to avoid:** Add as nullable with default, or use server_default
**Warning signs:** `nullable=False` on new column without `server_default`

```python
# Correct approach for is_read field
is_read = db.Column(db.Boolean, default=True, server_default='1', nullable=False)
```

## Code Examples

### Complete WAL Setup in app.py

```python
# Source: Verified pattern from Simon Willison + SQLite docs
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import event, MetaData

# Naming convention for constraints
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

metadata = MetaData(naming_convention=convention)
db = SQLAlchemy(metadata=metadata)
migrate = Migrate()

def create_app(config_class=None):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)

    # Enable WAL mode for SQLite
    if 'sqlite' in app.config.get('SQLALCHEMY_DATABASE_URI', ''):
        with app.app_context():
            _setup_sqlite_pragmas(db.engine)

    return app

def _setup_sqlite_pragmas(engine):
    """Configure SQLite connection pragmas."""
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
```

### FTS5 Search Query Pattern

```python
# Source: https://www.sqlite.org/fts5.html
def search_messages(query_text, limit=50):
    """Search messages using FTS5 with BM25 ranking."""
    sql = """
        SELECT m.*, bm25(message_fts) as relevance
        FROM message_fts
        JOIN message m ON message_fts.rowid = m.id
        WHERE message_fts MATCH :query
        ORDER BY bm25(message_fts)
        LIMIT :limit
    """
    return db.session.execute(
        text(sql),
        {'query': query_text, 'limit': limit}
    ).fetchall()
```

### Migration Script for is_read Field

```python
# Source: Flask-Migrate + Alembic batch mode pattern
"""Add is_read field to conversation

Revision ID: xxxx
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('is_read', sa.Boolean(),
                      server_default='1', nullable=False)
        )

def downgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.drop_column('is_read')
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual schema SQL | Flask-Migrate 4.0+ | 2023 | Batch mode default, automatic `compare_type` |
| Rollback journal | WAL mode | 2010 (SQLite 3.7) | Standard for concurrent access |
| FTS3/FTS4 | FTS5 | 2015 (SQLite 3.9) | Better ranking, BM25, prefix indexes |
| LIKE '%query%' | FTS5 MATCH | Always | 100-1000x faster for large datasets |

**Deprecated/outdated:**
- `render_as_batch` as explicit option: Now default in Flask-Migrate 4.0+
- FTS3/FTS4: Use FTS5 unless compatibility with SQLite < 3.9 required

## Recommendations for Claude's Discretion Items

### Search Result Ranking: BM25 (Relevance)

**Recommendation:** Use `ORDER BY bm25(message_fts)` (relevance ranking)

**Rationale:**
- BM25 is the FTS5 default ranking algorithm, optimized for text search
- `ORDER BY rank` is even faster (uses early termination)
- Chronological can be secondary sort: `ORDER BY bm25(fts), m.sent_at DESC`
- Guest messaging context benefits from relevance (find most relevant mentions)

### Case/Accent Handling: Porter + Unicode61 with Diacritics Removal

**Recommendation:** `tokenize='porter unicode61 remove_diacritics 2'`

**Rationale:**
- `porter` enables stemming: "running", "runs", "ran" all match "run"
- `unicode61` handles international characters correctly
- `remove_diacritics 2` normalizes accents: "cafe" matches "cafe"
- This is the most user-friendly configuration for a guest messaging system

### Migration Rollback Strategy: All-or-Nothing

**Recommendation:** All-or-nothing with explicit backup warning

**Rationale:**
- Alembic migrations are atomic within a single `upgrade()` function
- Partial rollbacks are complex and error-prone
- Clear backup recommendation before major migrations is simpler and safer
- SQLite batch migrations already do table copy/replace, which is effectively all-or-nothing

### FTS5 Configuration

**Recommendation:** External content table with message, guest name, and subject

```sql
CREATE VIRTUAL TABLE search_index USING fts5(
    content,           -- Message.content
    guest_name,        -- Guest.name (denormalized)
    subject,           -- Conversation.subject
    content='message',
    content_rowid='id',
    tokenize='porter unicode61 remove_diacritics 2'
);
```

**Rationale:**
- External content saves storage (no content duplication)
- Denormalizing guest_name and subject into FTS enables single-table search
- Triggers handle synchronization automatically
- `rebuild` command handles initial data population

## Open Questions

1. **FTS5 Trigger Complexity for Denormalized Data**
   - What we know: Triggers work well for single-table FTS; denormalized data (guest_name from Guest table) requires JOINs in triggers
   - What's unclear: Whether updating Guest.name should trigger FTS rebuild for all their messages
   - Recommendation: Accept eventual consistency; Guest.name changes are rare. Run periodic `rebuild` or handle in application

2. **Existing Database Migration Path**
   - What we know: No migrations folder exists; database was created via `db.create_all()`
   - What's unclear: Exact state of production database schema
   - Recommendation: Use `flask db init` then `flask db migrate` to capture current state, then add new changes

## Sources

### Primary (HIGH confidence)
- [Flask-Migrate Documentation](https://flask-migrate.readthedocs.io/) - Initialization, CLI commands, SQLite batch mode
- [SQLite FTS5 Documentation](https://www.sqlite.org/fts5.html) - External content tables, triggers, tokenizers, BM25 ranking
- [SQLite WAL Mode Documentation](https://www.sqlite.org/wal.html) - PRAGMA syntax, persistence, limitations
- [Flask-SQLAlchemy Models](https://flask-sqlalchemy.readthedocs.io/en/stable/models/) - Naming conventions for constraints

### Secondary (MEDIUM confidence)
- [Miguel Grinberg: Fixing ALTER TABLE Errors](https://blog.miguelgrinberg.com/post/fixing-alter-table-errors-with-flask-migrate-and-sqlite) - Batch mode details, unnamed constraint handling
- [Simon Willison: Enabling WAL Mode](https://til.simonwillison.net/sqlite/enabling-wal-mode) - SQLAlchemy event listener pattern
- [Charles Leifer: SQLite FTS with Python](https://charlesleifer.com/blog/using-sqlite-full-text-search-with-python/) - Python integration patterns

### Tertiary (LOW confidence)
- WebSearch results for 2026 patterns - Verified against official documentation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Flask-Migrate and FTS5 are well-documented, mature tools
- Architecture: HIGH - Patterns verified against official documentation
- Pitfalls: HIGH - Based on official SQLite and Alembic documentation

**Research date:** 2026-02-18
**Valid until:** 2026-03-18 (30 days - stable technologies)
