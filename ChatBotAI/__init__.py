"""
ChatBotAI - Unified Guest Messaging System
A Flask Blueprint for managing guest communications with AI-powered responses
"""

import os
from pathlib import Path
from flask import Blueprint

# Base directory for ChatBotAI
CHATBOT_DIR = Path(__file__).resolve().parent

# Create the main blueprint for ChatBotAI
chatbot_bp = Blueprint(
    'chatbot',
    __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='/chatbot/static',
    url_prefix='/chatbot'
)


def init_chatbot(app):
    """Initialize ChatBotAI with the Flask app

    This is called when ChatBotAI is used as a blueprint in another Flask app.
    Skip initialization if db is already registered (e.g., when using app.py factory).
    """
    from .models import db, _populate_default_settings
    from .services.ai_service import init_ai_service
    from .services.memory_service import init_memory_service
    from .services.push_service import init_push_service
    from .services.smoobu_service import init_smoobu_service

    # Initialize Flask-Login if not already done
    if 'login' not in app.extensions:
        from flask_login import LoginManager
        login_manager = LoginManager()
        login_manager.login_view = 'chatbot.login'
        login_manager.login_message = None
        login_manager.init_app(app)

        @login_manager.user_loader
        def load_user(user_id):
            from .models import User
            return User.query.get(int(user_id))

    # Only init if not already done - check for sqlalchemy extension
    if 'sqlalchemy' not in app.extensions:
        db.init_app(app)

        with app.app_context():
            # Auto-apply migrations and repair schema drift
            from .app import _auto_upgrade_schema
            _auto_upgrade_schema(app)

            # Create tables if they don't exist
            db.create_all()
            # Populate default settings
            _populate_default_settings()

            # Initialize services
            ai_service = init_ai_service(app)
            init_memory_service()
            init_push_service(app)
            init_smoobu_service(app)

            # Load saved model preference from database
            from .models import AISettings
            saved_model = AISettings.get('ollama_model')
            if saved_model and ai_service and saved_model != ai_service.model:
                ai_service.change_model(saved_model)
                import logging
                logging.getLogger(__name__).info(f"Loaded saved model preference: {saved_model}")


@chatbot_bp.record_once
def on_register(state):
    """Called when blueprint is registered with an app"""
    app = state.app

    # Ensure instance directory exists
    instance_dir = CHATBOT_DIR / 'instance'
    instance_dir.mkdir(exist_ok=True)

    # Database path for ChatBotAI
    db_path = instance_dir / 'chatbot.db'

    # Set config values for ChatBotAI
    if not app.config.get('SECRET_KEY'):
        app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'
    app.config.setdefault('SQLALCHEMY_DATABASE_URI', f'sqlite:///{db_path}')
    app.config.setdefault('SQLALCHEMY_TRACK_MODIFICATIONS', False)
    app.config.setdefault('OLLAMA_URL', 'http://localhost:11434')
    app.config.setdefault('OLLAMA_MODEL', 'mistral:7b-instruct')
    app.config.setdefault('OLLAMA_TIMEOUT', 30)

    # Initialize ChatBotAI
    init_chatbot(app)


@chatbot_bp.context_processor
def inject_online_users():
    """Make online users available in all templates."""
    from datetime import datetime, timedelta
    from flask_login import current_user
    from .models import User

    if not current_user.is_authenticated:
        return {'online_users': []}

    threshold = datetime.utcnow() - timedelta(minutes=5)
    online = User.query.filter(
        User.last_seen >= threshold
    ).order_by(User.display_name).all()

    return {'online_users': online}


@chatbot_bp.app_template_filter('to_local')
def to_local_time(utc_dt):
    """Convert naive UTC datetime to Europe/Berlin local time string."""
    if utc_dt is None:
        return ''
    from datetime import timezone
    from zoneinfo import ZoneInfo
    utc_aware = utc_dt.replace(tzinfo=timezone.utc)
    local_dt = utc_aware.astimezone(ZoneInfo('Europe/Berlin'))
    return local_dt.strftime('%d.%m.%Y %H:%M')


@chatbot_bp.app_template_filter('to_local_short')
def to_local_time_short(utc_dt):
    """Convert naive UTC datetime to short local time (dd.mm HH:MM)."""
    if utc_dt is None:
        return ''
    from datetime import timezone
    from zoneinfo import ZoneInfo
    utc_aware = utc_dt.replace(tzinfo=timezone.utc)
    local_dt = utc_aware.astimezone(ZoneInfo('Europe/Berlin'))
    return local_dt.strftime('%d.%m %H:%M')


@chatbot_bp.app_template_filter('to_local_iso')
def to_local_iso(utc_dt):
    """Convert naive UTC datetime to local ISO string for JS."""
    if utc_dt is None:
        return ''
    from datetime import timezone
    from zoneinfo import ZoneInfo
    utc_aware = utc_dt.replace(tzinfo=timezone.utc)
    local_dt = utc_aware.astimezone(ZoneInfo('Europe/Berlin'))
    return local_dt.isoformat()


# Import routes to register them with the blueprint
from . import routes
