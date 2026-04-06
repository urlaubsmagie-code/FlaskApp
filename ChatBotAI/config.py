"""
Configuration settings for ChatBotAI
"""

import os
from pathlib import Path

# Base directory for the ChatBotAI module
BASE_DIR = Path(__file__).resolve().parent


class Config:
    """Base configuration"""

    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    # Database settings
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        f'sqlite:///{BASE_DIR / "instance" / "chatbot.db"}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False

    # Ollama AI settings
    OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://localhost:11434')
    OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'gemma2:9b')
    OLLAMA_TIMEOUT = int(os.environ.get('OLLAMA_TIMEOUT', '120'))

    # AI behavior settings
    AI_AUTO_RESPONSE_ENABLED = os.environ.get('AI_AUTO_RESPONSE_ENABLED', 'true').lower() == 'true'
    AI_MEMORY_EXTRACTION_ENABLED = os.environ.get('AI_MEMORY_EXTRACTION_ENABLED', 'true').lower() == 'true'
    AI_RESPONSE_TONE = os.environ.get('AI_RESPONSE_TONE', 'friendly_professional')
    MAX_CONVERSATION_HISTORY = int(os.environ.get('MAX_CONVERSATION_HISTORY', '10'))

    # Platform integration settings (for future use)
    GMAIL_CREDENTIALS_FILE = os.environ.get('GMAIL_CREDENTIALS_FILE', 'credentials.json')
    GMAIL_TOKEN_FILE = os.environ.get('GMAIL_TOKEN_FILE', 'token.json')
    # Explicit redirect URI for Gmail OAuth - set this to avoid redirect_uri_mismatch errors
    # Example: http://localhost/chatbot/gmail/callback or https://yourdomain.com/chatbot/gmail/callback
    GMAIL_REDIRECT_URI = os.environ.get('GMAIL_REDIRECT_URI', '')

    # Email filtering settings - only process emails matching these criteria
    # Domains: emails FROM these domains will be processed
    EMAIL_ALLOWED_DOMAINS = [
        'airbnb.com',
        'airbnb.de',
        'airbnb.es',
        'airbnb.fr',
        'airbnb.it',
        'booking.com',
        'guest.booking.com',
    ]

    # Keywords: emails with these words in subject will be processed
    # (case-insensitive, matches partial words)
    EMAIL_SUBJECT_KEYWORDS = [
        'booking',
        'reservation',
        'buchung',        # German
        'reservierung',   # German
        'inquiry',
        'anfrage',        # German
        'check-in',
        'check-out',
        'guest',
        'gast',           # German
        'arrival',
        'ankunft',        # German
        'confirmation',
        'bestatigung',    # German
    ]

    # Filter mode: 'domain', 'keyword', 'both', 'either'
    # - 'domain': only check domain whitelist
    # - 'keyword': only check subject keywords
    # - 'both': must match domain AND keyword
    # - 'either': must match domain OR keyword (recommended)
    EMAIL_FILTER_MODE = os.environ.get('EMAIL_FILTER_MODE', 'either')

    # Web Push Notifications
    VAPID_CLAIM_EMAIL = os.environ.get('VAPID_CLAIM_EMAIL', 'mailto:admin@chatbotai.local')

    # Smoobu API integration
    SMOOBU_API_URL = os.environ.get('SMOOBU_API_URL', 'https://login.smoobu.com/api')
    SMOOBU_API_KEY = os.environ.get('SMOOBU_API_KEY', '')


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SQLALCHEMY_ECHO = True


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False

    # In production, use PostgreSQL
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        Config.SQLALCHEMY_DATABASE_URI
    )


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_config():
    """Get configuration based on environment"""
    env = os.environ.get('FLASK_ENV', 'development')
    return config.get(env, config['default'])
