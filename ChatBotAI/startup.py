"""Shared initialization for the integrated portal and standalone UMI app."""

import logging
import os
from pathlib import Path

from flask import Flask
from flask_compress import Compress
from flask_login import LoginManager
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config, DevelopmentConfig, ProductionConfig, TestingConfig

logger = logging.getLogger(__name__)
DEV_SECRET = 'dev-secret-key-change-in-production'
PLACEHOLDER_SECRETS = {DEV_SECRET, 'change-this-to-a-secure-random-string', 'your-secret-key-here'}

# Read these at startup, not only at module import: the parent may load .env
# after importing ChatBotAI services. Explicit host-app configuration wins.
ENV_KEYS = (
    'SECRET_KEY', 'DATABASE_URL', 'OLLAMA_URL', 'OLLAMA_MODEL', 'OLLAMA_TIMEOUT',
    'PROMPT_DEV_AUTO_RELOAD', 'AI_AUTO_RESPONSE_ENABLED',
    'AI_MEMORY_EXTRACTION_ENABLED', 'AI_RESPONSE_TONE', 'MAX_CONVERSATION_HISTORY',
    'GMAIL_CREDENTIALS_FILE', 'GMAIL_TOKEN_FILE', 'GMAIL_REDIRECT_URI',
    'EMAIL_FILTER_MODE', 'VAPID_CLAIM_EMAIL', 'SMOOBU_API_URL', 'SMOOBU_API_KEY',
    'KEEPALIVE_URL', 'KEEPALIVE_INTERVAL', 'CHATBOT_TRUST_PROXY_HEADERS',
)


def configure_app(app, config_class=None):
    """Load UMI defaults without turning a bare production host into debug mode."""
    if config_class is not None:
        app.config.from_object(config_class)
    else:
        existing = dict(app.config)
        defaults = TestingConfig if app.testing else DevelopmentConfig if app.debug else ProductionConfig
        app.config.from_object(defaults)
        if not app.testing:
            for key in ENV_KEYS:
                if key not in os.environ:
                    continue
                target = 'SQLALCHEMY_DATABASE_URI' if key == 'DATABASE_URL' else key
                value = os.environ[key]
                default = getattr(Config, target, None)
                if isinstance(default, bool):
                    value = value.lower() in ('true', '1', 'yes', 'on')
                elif isinstance(default, int):
                    value = int(value)
                app.config[target] = value
        for key, value in existing.items():
            if key not in Flask.default_config or value != Flask.default_config[key]:
                app.config[key] = value

    secret = app.config.get('SECRET_KEY')
    if not app.testing and not app.debug and (not secret or secret in PLACEHOLDER_SECRETS):
        raise RuntimeError('Set a private random SECRET_KEY before starting ChatBotAI in production.')
    if not secret:
        app.config['SECRET_KEY'] = DEV_SECRET
    app.extensions['chatbot_configured'] = True


def initialize_app(app):
    """Initialize once per Flask app; registering a blueprint uses this too."""
    if app.extensions.get('chatbot_initialized'):
        return
    if not app.extensions.get('chatbot_configured'):
        configure_app(app)

    from . import app as runtime
    from .models import db, User, AISettings, _populate_default_settings
    from .services.ai_service import init_ai_service
    from .services.memory_service import init_memory_service
    from .services.message_router import init_message_router
    from .services.push_service import init_push_service
    from .services.smoobu_service import init_smoobu_service
    from .services.notion_service import init_notion_service
    from .services.debug_service import init_debug_service

    if app.config.get('CHATBOT_TRUST_PROXY_HEADERS'):
        # Opt in only behind a trusted proxy. Do not trust forwarded host/prefix.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    if 'compress' not in app.extensions:
        Compress(app)
    if not hasattr(app, 'login_manager'):
        manager = LoginManager()
        manager.login_view = 'chatbot.login'
        manager.login_message = None
        manager.init_app(app)

        @manager.user_loader
        def load_user(user_id):
            try:
                return db.session.get(User, int(user_id))
            except (ValueError, TypeError):
                return None

    if app.config.get('SEND_FILE_MAX_AGE_DEFAULT') is None:
        app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0 if app.debug else 2592000
    if app.debug and not app.testing:
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

    pkg_logger = logging.getLogger('ChatBotAI')
    pkg_logger.disabled = False
    pkg_logger.setLevel(logging.DEBUG if app.debug else logging.INFO)
    if not app.testing and app.config.get('CHATBOT_FILE_LOGGING', True):
        runtime._install_file_logger(app)
    init_debug_service(app)

    if 'sqlalchemy' not in app.extensions:
        db.init_app(app)
    if 'migrate' not in app.extensions:
        runtime.migrate.init_app(app, db, directory=str(runtime.MIGRATIONS_DIR), render_as_batch=True)
    with app.app_context():
        if db.engine.dialect.name == 'sqlite':
            if db.engine.url.database not in (None, '', ':memory:'):
                Path(db.engine.url.database).parent.mkdir(parents=True, exist_ok=True)
            runtime._setup_sqlite_pragmas(db.engine)
        if not app.testing and app.config.get('CHATBOT_AUTO_MIGRATE', True):
            runtime._auto_upgrade_schema(app)
        db.create_all()
        _populate_default_settings()
        if db.engine.dialect.name == 'sqlite':
            runtime._ensure_fts5_index(app)

        ai = init_ai_service(app)
        init_memory_service()
        init_message_router()
        init_push_service(app)
        init_smoobu_service(app)
        init_notion_service(app)
        saved_model = AISettings.get('ollama_model')
        if saved_model and saved_model != ai.model:
            ai.change_model(saved_model, preload=False)
        if not app.testing and app.config.get('CHATBOT_STARTUP_CHECKS_ENABLED', True):
            if not ai.test_connection():
                logger.warning('Ollama connection failed; AI features may be unavailable')

    app.extensions['chatbot_initialized'] = True
    start_background_tasks(app)


def start_background_tasks(app):
    """Start each daemon at most once; never start daemons in a testing app."""
    if app.testing or not app.config.get('CHATBOT_BACKGROUND_TASKS_ENABLED', True):
        return
    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return
    from . import app as runtime
    started = app.extensions.setdefault('chatbot_background_tasks', set())
    for name, start in (
        ('smoobu', runtime._start_background_sync),
        ('email_reconcile', runtime._start_email_reconcile),
        ('keepalive', runtime._start_keepalive),
    ):
        if name in started:
            continue
        try:
            start(app)
            started.add(name)
        except Exception:
            logger.exception('Failed to start %s daemon', name)
