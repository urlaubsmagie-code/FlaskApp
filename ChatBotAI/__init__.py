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
    """Use the same initialization path in the portal and standalone app."""
    from .startup import initialize_app
    initialize_app(app)


@chatbot_bp.record_once
def on_register(state):
    init_chatbot(state.app)


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


@chatbot_bp.context_processor
def inject_whatsapp_enabled():
    """The sidebar WhatsApp badge renders only when the bridge integration is set up."""
    import os
    return {'whatsapp_enabled': bool(os.environ.get('WHATSAPP_BRIDGE_URL'))}


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
