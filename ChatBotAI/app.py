"""
Standalone Flask application for ChatBotAI
Run this directly for development: python app.py
"""

import os
import logging
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


def _setup_sqlite_pragmas(engine):
    """Configure SQLite connection pragmas for WAL mode and busy timeout."""
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
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

    # Ensure secret key is always set (required for Flask sessions / OAuth)
    if not app.config.get('SECRET_KEY'):
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
