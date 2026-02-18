"""
Standalone Flask application for ChatBotAI
Run this directly for development: python app.py
"""

import os
import logging
from flask import Flask
from flask_migrate import Migrate
from sqlalchemy import event

from .config import get_config
from .models import db, init_db
from .services.ai_service import init_ai_service
from .services.memory_service import init_memory_service

# Flask-Migrate instance
migrate = Migrate()


def _setup_sqlite_pragmas(engine):
    """Configure SQLite connection pragmas for WAL mode and busy timeout."""
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


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

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if app.config.get('DEBUG') else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    # Initialize database
    db.init_app(app)

    # Initialize Flask-Migrate with batch mode for SQLite compatibility
    migrate.init_app(app, db, render_as_batch=True)

    with app.app_context():
        # Enable WAL mode for SQLite (concurrent access for polling)
        if 'sqlite' in app.config.get('SQLALCHEMY_DATABASE_URI', ''):
            _setup_sqlite_pragmas(db.engine)

        # Note: Use 'flask db upgrade' for schema changes. create_all() is fallback for fresh installs.
        db.create_all()
        from .models import _populate_default_settings
        _populate_default_settings()
        logger.info("Database initialized")

    # Initialize services
    with app.app_context():
        ai_service = init_ai_service(app)
        memory_service = init_memory_service()

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

    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║                     ChatBotAI Development Server                  ║
╠══════════════════════════════════════════════════════════════════╣
║  Server running at: http://localhost:{port}                        ║
║  Ollama URL: {app.config.get('OLLAMA_URL'):<44} ║
║  Model: {app.config.get('OLLAMA_MODEL'):<49} ║
║  Database: SQLite (./instance/chatbot.db)                        ║
╠══════════════════════════════════════════════════════════════════╣
║  Press Ctrl+C to stop                                            ║
╚══════════════════════════════════════════════════════════════════╝
""")

    app.run(host=host, port=port, debug=True)


if __name__ == '__main__':
    run_development_server()
