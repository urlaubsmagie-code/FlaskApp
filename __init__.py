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

    # Only init if not already done - check for sqlalchemy extension
    if 'sqlalchemy' not in app.extensions:
        db.init_app(app)

        with app.app_context():
            # Create tables if they don't exist
            db.create_all()
            # Populate default settings
            _populate_default_settings()

            # Initialize services
            init_ai_service(app)
            init_memory_service()


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
    app.config.setdefault('SQLALCHEMY_DATABASE_URI', f'sqlite:///{db_path}')
    app.config.setdefault('SQLALCHEMY_TRACK_MODIFICATIONS', False)
    app.config.setdefault('OLLAMA_URL', 'http://localhost:11434')
    app.config.setdefault('OLLAMA_MODEL', 'mistral:7b-instruct')
    app.config.setdefault('OLLAMA_TIMEOUT', 30)

    # Initialize ChatBotAI
    init_chatbot(app)


# Import routes to register them with the blueprint
from . import routes
