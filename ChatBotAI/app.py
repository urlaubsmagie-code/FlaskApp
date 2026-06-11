"""
Standalone Flask application for ChatBotAI
Run this directly for development: python app.py
"""

import os
import logging
import threading
from pathlib import Path
from flask import Flask
from flask_compress import Compress
from flask_login import LoginManager
from flask_migrate import Migrate
from sqlalchemy import event

from werkzeug.middleware.proxy_fix import ProxyFix
from .config import get_config

# Path to migrations directory within ChatBotAI package
MIGRATIONS_DIR = Path(__file__).parent / 'migrations'
from .models import db, init_db
from .services.ai_service import init_ai_service
from .services.memory_service import init_memory_service
from .services.message_router import init_message_router
from .services.push_service import init_push_service
from .services.smoobu_service import init_smoobu_service

# Flask-Migrate instance
migrate = Migrate()


def _auto_upgrade_schema(app):
    """Auto-apply pending Alembic migrations, then verify and repair any missing columns.

    This runs on every startup to ensure the database schema matches the models,
    even if 'flask db upgrade' was never run manually.
    """
    logger = logging.getLogger(__name__)

    # --- Step 1: Try running pending Alembic migrations ---
    try:
        from flask_migrate import upgrade as fm_upgrade

        # Ensure Flask-Migrate is initialized (may not be when loaded as blueprint)
        if 'migrate' not in app.extensions:
            temp_migrate = Migrate()
            temp_migrate.init_app(app, db, directory=str(MIGRATIONS_DIR), render_as_batch=True)

        fm_upgrade(directory=str(MIGRATIONS_DIR))
        logger.info("Alembic migrations applied successfully")
    except Exception as e:
        logger.warning(f"Alembic auto-upgrade skipped or failed: {e}")
        # This is expected on fresh installs where alembic_version table doesn't exist yet

    # --- Step 2: Verify schema matches models (catch anything migrations missed) ---
    try:
        from sqlalchemy import inspect as sa_inspect, text

        inspector = sa_inspect(db.engine)
        existing_tables = set(inspector.get_table_names())

        # Build expected schema from model metadata
        for table_name, table_obj in db.metadata.tables.items():
            if table_name not in existing_tables:
                # Table is entirely missing — create_all() should handle this
                logger.info(f"Table '{table_name}' missing, will be created by create_all()")
                continue

            # Check for missing columns
            existing_cols = {col['name'] for col in inspector.get_columns(table_name)}
            for col in table_obj.columns:
                if col.name not in existing_cols:
                    # Determine SQL type string
                    col_type = col.type.compile(db.engine.dialect)
                    nullable = "NULL" if col.nullable else "NOT NULL"
                    default_clause = ""

                    # Handle server_default
                    if col.server_default is not None:
                        default_clause = f" DEFAULT {col.server_default.arg}"
                    elif col.nullable:
                        default_clause = " DEFAULT NULL"

                    alter_sql = f'ALTER TABLE "{table_name}" ADD COLUMN "{col.name}" {col_type} {nullable}{default_clause}'
                    logger.warning(f"Missing column detected — running: {alter_sql}")
                    with db.engine.connect() as conn:
                        conn.execute(text(alter_sql))
                        conn.commit()
                    logger.info(f"Added missing column '{table_name}.{col.name}'")

        logger.info("Schema verification complete")

    except Exception as e:
        logger.error(f"Schema verification/repair failed: {e}", exc_info=True)


def _install_file_logger(app):
    """Attach a rotating file handler to the ChatBotAI package logger.

    Idempotent — safe to call from both create_app() (dev) and init_chatbot()
    (production blueprint). Submodule loggers named ChatBotAI.* propagate up
    to this handler so we capture daemon/webhook/sync activity to disk.
    """
    from logging.handlers import RotatingFileHandler

    log_dir = os.path.join(os.path.dirname(__file__), 'instance')
    os.makedirs(log_dir, exist_ok=True)
    pkg_logger = logging.getLogger('ChatBotAI')
    if any(isinstance(h, RotatingFileHandler) for h in pkg_logger.handlers):
        return
    handler = RotatingFileHandler(
        os.path.join(log_dir, 'chatbot.log'),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8',
    )
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s %(name)s: %(message)s'
    ))
    pkg_logger.addHandler(handler)
    if pkg_logger.level == logging.NOTSET or pkg_logger.level > logging.INFO:
        pkg_logger.setLevel(logging.INFO)


def _setup_sqlite_pragmas(engine):
    """Configure SQLite connection pragmas for WAL mode and busy timeout."""
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        # Negative cache_size = KB of memory (here 64MB). Keeps more DB pages
        # in-process so first queries after idle don't hit cold OS file cache.
        cursor.execute("PRAGMA cache_size=-65536")
        # mmap_io speeds up large reads on Windows by letting SQLite read pages
        # directly from the OS page cache without going through the read syscall.
        cursor.execute("PRAGMA mmap_size=268435456")  # 256MB
        cursor.close()


def _ensure_fts5_index(app):
    """Ensure the FTS5 search index and triggers exist and are populated.

    db.create_all() does not recreate FTS5 virtual tables or triggers,
    so we must verify and repair them on every startup.
    """
    logger = logging.getLogger(__name__)
    try:
        from sqlalchemy import text

        with db.engine.connect() as conn:
            # Check if message_fts virtual table exists
            fts_exists = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='message_fts'"
            )).fetchone()

            if not fts_exists:
                logger.warning("FTS5 table missing — creating message_fts and triggers")
                conn.execute(text("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5(
                        content,
                        guest_name,
                        subject,
                        tokenize='porter unicode61 remove_diacritics 2'
                    )
                """))
                needs_populate = True
            else:
                needs_populate = False

            # Ensure triggers exist (they can be lost if db was recreated)
            for trigger_name, trigger_sql in [
                ('message_ai', """
                    CREATE TRIGGER IF NOT EXISTS message_ai AFTER INSERT ON message BEGIN
                        INSERT INTO message_fts(rowid, content, guest_name, subject)
                        SELECT new.id, new.content, g.name, c.subject
                        FROM conversation c
                        JOIN guest g ON c.guest_id = g.id
                        WHERE c.id = new.conversation_id;
                    END
                """),
                ('message_ad', """
                    CREATE TRIGGER IF NOT EXISTS message_ad AFTER DELETE ON message BEGIN
                        DELETE FROM message_fts WHERE rowid = old.id;
                    END
                """),
                ('message_au', """
                    CREATE TRIGGER IF NOT EXISTS message_au AFTER UPDATE ON message BEGIN
                        DELETE FROM message_fts WHERE rowid = old.id;
                        INSERT INTO message_fts(rowid, content, guest_name, subject)
                        SELECT new.id, new.content, g.name, c.subject
                        FROM conversation c
                        JOIN guest g ON c.guest_id = g.id
                        WHERE c.id = new.conversation_id;
                    END
                """),
            ]:
                trigger_exists = conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='trigger' AND name=:name"
                ), {'name': trigger_name}).fetchone()
                if not trigger_exists:
                    logger.warning(f"FTS5 trigger '{trigger_name}' missing — recreating")
                    conn.execute(text(trigger_sql))
                    needs_populate = True

            # Check if index is out of sync (empty or stale)
            fts_count = conn.execute(text(
                "SELECT COUNT(*) FROM message_fts"
            )).scalar()
            msg_count = conn.execute(text(
                "SELECT COUNT(*) FROM message"
            )).scalar()

            if fts_count == 0 and msg_count > 0:
                needs_populate = True
                logger.warning(f"FTS5 index empty but {msg_count} messages exist — rebuilding")
            elif msg_count > 0 and abs(fts_count - msg_count) > msg_count * 0.1:
                needs_populate = True
                logger.warning(f"FTS5 index out of sync ({fts_count} indexed vs {msg_count} messages) — rebuilding")

            if needs_populate:
                conn.execute(text("DELETE FROM message_fts"))
                conn.execute(text("""
                    INSERT INTO message_fts(rowid, content, guest_name, subject)
                    SELECT m.id, m.content, g.name, c.subject
                    FROM message m
                    JOIN conversation c ON m.conversation_id = c.id
                    JOIN guest g ON c.guest_id = g.id
                """))
                conn.commit()
                new_count = conn.execute(text("SELECT COUNT(*) FROM message_fts")).scalar()
                logger.info(f"FTS5 search index rebuilt: {new_count} messages indexed")
            else:
                logger.info(f"FTS5 search index OK: {fts_count} messages indexed")

    except Exception as e:
        logger.error(f"FTS5 index check failed: {e}", exc_info=True)


def _reconcile_read_states():
    """Fix conversations marked unread but already answered outside the app.

    Finds conversations where is_read=False but the most recent message is
    from the owner or AI (meaning someone already handled it). Marks them
    as read and advances the read cursor.

    Returns the number of conversations fixed.
    """
    from .models import db, Conversation, Message

    # Find each unread conversation's most recent message by sent_at (the
    # source of truth — id can be out of order when Smoobu pages historical
    # messages). Tiebreak by id desc for stable ordering when sent_at ties.
    # Unread set is typically small (dozens), so per-conv lookups are fine.
    unread_convs = Conversation.query.filter_by(is_read=False).all()
    fixed = 0
    for conv in unread_convs:
        last_msg = Message.query.filter_by(conversation_id=conv.id).order_by(
            Message.sent_at.desc(), Message.id.desc()
        ).first()
        if not last_msg or last_msg.sender_type == 'guest':
            continue
        conv.is_read = True
        if not conv.last_read_message_id or last_msg.id > conv.last_read_message_id:
            conv.last_read_message_id = last_msg.id
        fixed += 1

    if fixed:
        db.session.commit()

    return fixed


def _start_keepalive(app):
    """Ping our own public URL every few minutes to keep the whole chain warm.

    Why: after an idle period (e.g. overnight) the first request feels slow
    because Cloudflare's edge cache cools off, the Cloudflare tunnel may need
    to re-handshake, and SQLite pages get evicted from the OS file cache.
    A scheduled outbound hit through the public URL keeps:
      - CF edge cache hot
      - CF tunnel connection alive
      - Waitress threads warm
      - SQLite pages in OS file cache (the health endpoint touches the DB)

    Configure via KEEPALIVE_URL and KEEPALIVE_INTERVAL. Disabled if URL unset.
    """
    logger = logging.getLogger(__name__)
    keepalive_url = app.config.get('KEEPALIVE_URL') or os.environ.get('KEEPALIVE_URL')
    if not keepalive_url:
        logger.info("Keepalive disabled (KEEPALIVE_URL not configured)")
        return

    interval = int(app.config.get('KEEPALIVE_INTERVAL', os.environ.get('KEEPALIVE_INTERVAL', 300)))
    STARTUP_DELAY = 60  # let everything boot before first ping

    def _ping_loop():
        import time
        import requests
        time.sleep(STARTUP_DELAY)
        logger.info("Keepalive started: pinging %s every %ds", keepalive_url, interval)
        while True:
            try:
                r = requests.get(keepalive_url, timeout=15)
                logger.debug("Keepalive ping → %s", r.status_code)
            except Exception as e:
                # Don't spam logs if the tunnel is briefly down — debug only
                logger.debug("Keepalive ping failed: %s", e)
            time.sleep(interval)

    thread = threading.Thread(target=_ping_loop, daemon=True, name="keepalive")
    thread.start()


def _start_background_sync(app):
    """Start a daemon thread that syncs Smoobu messages every 10 minutes.

    Only starts if Smoobu is configured with an API key. The thread runs
    inside an app context so it can access the database. A lock prevents
    overlap with manual syncs or slow cycles.
    """
    logger = logging.getLogger(__name__)
    sync_lock = threading.Lock()

    SYNC_INTERVAL = 600  # seconds — webhook is primary; daemon is safety net + read-state reconciler
    STARTUP_DELAY = 3    # seconds — brief delay so app finishes booting before first sync

    def _run_one_sync(force: bool = False):
        """Run a single sync cycle. Returns silently on any error (logged).

        Args:
            force: If True, bypass the SmoobuService 30s cooldown. Set by the
                manual /api/smoobu/sync route so a human click always does work.
        """
        try:
            if sync_lock.acquire(blocking=False):
                try:
                    with app.app_context():
                        try:
                            from .services.smoobu_service import get_smoobu_service
                            smoobu = get_smoobu_service()
                            if smoobu and smoobu.is_configured():
                                result = smoobu.sync_messages(force=force)
                                imported = result.get('imported', 0)
                                if imported > 0:
                                    # Step 7 instrumentation: once webhooks are live, the daemon
                                    # ideally imports 0 new messages per cycle — anything it does
                                    # import is a "webhook miss" worth investigating.
                                    logger.warning(
                                        "[WEBHOOK_MISS] Background sync imported %d new message(s) — webhooks missed these",
                                        imported,
                                    )
                                    print(
                                        f"[ChatBotAI] [WEBHOOK_MISS] daemon imported {imported} new msg(s) — webhook missed them",
                                        flush=True,
                                    )
                                else:
                                    logger.debug("Background sync: no new messages (webhooks healthy)")

                                # Reconcile read states: if a conversation is marked
                                # unread but the last message is from the owner or AI,
                                # someone already handled it outside the app.
                                fixed = _reconcile_read_states()
                                if fixed > 0:
                                    logger.info("Background sync: reconciled %d conversations (already answered)", fixed)

                                # Email reconciliation: backfill guest messages Smoobu
                                # dropped, using Airbnb/Booking notification emails as an
                                # independent source. Guarded by AISettings + Gmail config.
                                try:
                                    from .services.email_reconcile import reconcile_from_email, get_reconcile_config
                                    if get_reconcile_config()['enabled']:
                                        from .services.gmail_service import get_gmail_service
                                        gmail = get_gmail_service()
                                        if gmail and gmail.is_authenticated():
                                            estats = reconcile_from_email(gmail)
                                            if estats['auto_inserted'] or estats['queued']:
                                                logger.info(
                                                    "Email reconcile: inserted %d, queued %d (scanned %d)",
                                                    estats['auto_inserted'], estats['queued'], estats['scanned'])
                                                print(
                                                    f"[ChatBotAI] Email reconcile: +{estats['auto_inserted']} inserted, "
                                                    f"{estats['queued']} queued (scanned {estats['scanned']})", flush=True)
                                except Exception:
                                    logger.exception("Email reconciliation error")
                            else:
                                logger.debug("Background sync: Smoobu not configured, skipping")
                        finally:
                            # Always release the SQLAlchemy session so the daemon
                            # doesn't accumulate idle connections from the pool.
                            from .models import db
                            db.session.remove()
                finally:
                    sync_lock.release()
            else:
                logger.debug("Background sync: skipped, sync already in progress")
        except Exception:
            logger.exception("Background sync error")

    def _sync_loop():
        import time
        # Brief startup delay so Flask/Waitress finishes booting first
        time.sleep(STARTUP_DELAY)
        logger.info("Background Smoobu sync started (immediate first run, then every %ds)", SYNC_INTERVAL)

        # Immediate first sync on startup — team sees new messages right after restart
        _run_one_sync()

        while True:
            time.sleep(SYNC_INTERVAL)
            _run_one_sync()

    thread = threading.Thread(target=_sync_loop, daemon=True, name="smoobu-bg-sync")
    thread.start()
    logger.info("Background Smoobu sync thread scheduled (first run in %ds, then every %ds)", STARTUP_DELAY, SYNC_INTERVAL)
    # Also print() so it shows in the console regardless of logging config —
    # the main FlaskApp/app.py production path doesn't configure handlers for
    # the ChatBotAI logger, so logger.info() is invisible there.
    print(f"[ChatBotAI] Background Smoobu sync thread scheduled (first run in {STARTUP_DELAY}s, then every {SYNC_INTERVAL}s)", flush=True)

    # Expose the single-sync function so the manual /api/smoobu/sync route
    # can trigger it fire-and-forget without holding a Waitress thread for
    # the full 2+ minute sync. The shared sync_lock prevents overlap with
    # the periodic daemon cycle.
    app.smoobu_trigger_sync = _run_one_sync
    print("[ChatBotAI] app.smoobu_trigger_sync registered — manual sync is now fire-and-forget", flush=True)


def create_app(config_class=None):
    """Application factory for ChatBotAI"""

    # Create Flask app
    app = Flask(__name__,
                template_folder='templates',
                static_folder='static')

    # Load configuration
    if config_class is None:
        config_class = get_config()
    app.config.from_object(config_class)

    # Trust proxy headers (X-Forwarded-For/Proto/Host) from Cloudflare tunnel
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # Enable gzip compression for all responses > 500 bytes
    Compress(app)

    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.login_view = 'chatbot.login'
    login_manager.login_message = None  # Suppress default flash message
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        from .models import User
        try:
            return User.query.get(int(user_id))
        except (ValueError, TypeError):
            return None

    # Cache static assets: 0 in dev (instant refresh), 30 days in production (with ?v= busting)
    if app.config.get('DEBUG'):
        app.config.setdefault('SEND_FILE_MAX_AGE_DEFAULT', 0)
    else:
        app.config.setdefault('SEND_FILE_MAX_AGE_DEFAULT', 2592000)

    # Ensure secret key is always set (required for Flask sessions / OAuth).
    # In production, refuse to start with the dev fallback — predictable
    # session keys mean attackers can forge sessions.
    is_production = (
        not app.config.get('DEBUG')
        and os.environ.get('FLASK_ENV', '').lower() == 'production'
    )
    secret_key = app.config.get('SECRET_KEY')
    if is_production and secret_key in (None, '', 'dev-secret-key-change-in-production'):
        raise RuntimeError(
            "SECRET_KEY environment variable must be set to a strong random "
            "value when FLASK_ENV=production. Refusing to start with the dev fallback."
        )
    if not secret_key:
        app.secret_key = 'dev-secret-key-change-in-production'

    # Allow OAuth over HTTP in development (required for localhost Gmail OAuth)
    if app.config.get('DEBUG'):
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if app.config.get('DEBUG') else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    _install_file_logger(app)

    # Initialize in-memory debug log handler
    from .services.debug_service import init_debug_service
    init_debug_service(app)

    # Initialize database
    db.init_app(app)

    # Initialize Flask-Migrate with batch mode for SQLite compatibility
    # Directory points to ChatBotAI/migrations
    migrate.init_app(app, db, directory=str(MIGRATIONS_DIR), render_as_batch=True)

    with app.app_context():
        # Enable WAL mode for SQLite (concurrent access for polling)
        if 'sqlite' in app.config.get('SQLALCHEMY_DATABASE_URI', ''):
            _setup_sqlite_pragmas(db.engine)

        # Auto-apply migrations and repair any schema drift
        _auto_upgrade_schema(app)

        # create_all() handles any brand-new tables not covered by migrations
        db.create_all()
        from .models import _populate_default_settings
        _populate_default_settings()

        # Ensure FTS5 search index exists and is in sync
        _ensure_fts5_index(app)

        logger.info("Database initialized")

    # Initialize services
    with app.app_context():
        ai_service = init_ai_service(app)
        memory_service = init_memory_service()
        message_router = init_message_router()
        push_service = init_push_service(app)
        smoobu_service = init_smoobu_service(app)

        # Load saved model preference from database
        from .models import AISettings
        saved_model = AISettings.get('ollama_model')
        if saved_model and saved_model != ai_service.model:
            ai_service.change_model(saved_model)
            logger.info(f"Loaded saved model preference: {saved_model}")

        # Test Ollama connection
        if ai_service.test_connection():
            logger.info("Ollama connection successful")
        else:
            logger.warning("Ollama connection failed - AI features will be limited")

    # Register blueprint
    from . import chatbot_bp
    app.register_blueprint(chatbot_bp)

    # Add root redirect
    @app.route('/')
    def root():
        from flask import redirect, url_for
        return redirect(url_for('chatbot.index'))

    # Start background Smoobu message sync (every 2 minutes)
    # Guard: only in reloader child process (debug) or non-debug (Waitress)
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.config.get('DEBUG'):
        _start_background_sync(app)
        _start_keepalive(app)

    logger.info(f"ChatBotAI application created (debug={app.config.get('DEBUG')})")

    return app


def run_development_server():
    """Run the development server"""
    app = create_app()

    # Get port from environment or use default
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')

    # Show the actual active model (may differ from config default if user changed it)
    from .services.ai_service import get_ai_service
    active_model = app.config.get('OLLAMA_MODEL')
    with app.app_context():
        ai = get_ai_service()
        if ai:
            active_model = ai.model

    print(f"""
====================================================================
  ChatBotAI Development Server
====================================================================
  Server running at: http://localhost:{port}
  Ollama URL: {app.config.get('OLLAMA_URL')}
  Model: {active_model}
  Database: SQLite (./instance/chatbot.db)
--------------------------------------------------------------------
  Press Ctrl+C to stop
====================================================================
""")

    app.run(host=host, port=port, debug=True)


if __name__ == '__main__':
    run_development_server()
