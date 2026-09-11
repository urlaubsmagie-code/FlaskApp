"""
Routes for ChatBotAI
Defines all URL endpoints for the messaging system
"""

import difflib
import hmac
import logging
import os
import threading
import time
import uuid
from functools import wraps, lru_cache

from flask import render_template, request, jsonify, redirect, url_for, current_app
from flask_login import login_user, logout_user, current_user, login_required
from datetime import datetime, timezone


def admin_required(f):
    """Decorator that restricts access to admin users only."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            if request.is_json or request.path.startswith('/chatbot/api/'):
                return jsonify({'error': 'Admin access required'}), 403
            return redirect(url_for('chatbot.index'))
        return f(*args, **kwargs)
    return decorated
from sqlalchemy import case as sa_case
from sqlalchemy.orm import joinedload

from . import chatbot_bp

logger = logging.getLogger(__name__)
from .models import db, User, UserSession, Guest, GuestDetail, Conversation, Message, Property, AISettings, ReplyTemplate, KnowledgeEntry, EmailBackfillCandidate, ProblemReport, preload_last_messages, preload_unread_counts, preload_display_platforms, pending_guest_question
from .services.ai_service import get_ai_service
from .services.memory_service import get_memory_service
from .services.message_router import get_message_router


# ============================================================================
# HELPERS
# ============================================================================

def _store_correction_if_needed(original_ai_content, corrected_content, conversation):
    """Compare original AI text with host's corrected version and store as correction if meaningfully different."""
    if not original_ai_content or not corrected_content:
        return None

    # Check similarity — skip if just a typo fix (ratio >= 0.90)
    ratio = difflib.SequenceMatcher(None, original_ai_content, corrected_content).ratio()
    if ratio >= 0.90:
        logger.info(f"[CORRECTION] Skipped — similarity {ratio:.2f} >= 0.90 (typo-level edit)")
        return None

    # Format the correction value
    value = f"FALSCH: {original_ai_content}\nRICHTIG: {corrected_content}"

    # Create KnowledgeEntry with placeholder label
    entry = KnowledgeEntry(
        property_id=conversation.property_id,
        category='correction',
        label='(wird extrahiert...)',
        value=value,
        sort_order=0
    )
    db.session.add(entry)
    db.session.commit()

    logger.info(f"[CORRECTION] Stored correction {entry.id} for conversation {conversation.id} "
                f"(similarity={ratio:.2f}, property_id={conversation.property_id})")

    # Extract topic label via AI in background thread
    entry_id = entry.id
    app = current_app._get_current_object()

    def _extract_topic():
        with app.app_context():
            try:
                ai = get_ai_service()
                if not ai:
                    return
                topic = ai.extract_correction_topic(original_ai_content, corrected_content)
                if topic:
                    e = KnowledgeEntry.query.get(entry_id)
                    if e:
                        e.label = topic
                        db.session.commit()
                        logger.info(f"[CORRECTION] Topic extracted for {entry_id}: {topic}")
            except Exception as ex:
                logger.warning(f"[CORRECTION] Topic extraction failed for {entry_id}: {ex}")

    threading.Thread(target=_extract_topic, daemon=True).start()

    return entry


# ============================================================================
# AUTHENTICATION GATE
# ============================================================================

@chatbot_bp.after_request
def prevent_html_cache(response):
    """Prevent browser from caching HTML pages so back-navigation shows fresh data."""
    if response.content_type and 'text/html' in response.content_type:
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
    return response


@chatbot_bp.before_request
def require_login():
    """Redirect to setup (if no users) or login (if not authenticated)."""
    # Whitelist: static files, login, setup, webhooks, health check, service worker
    if request.endpoint and (
        request.endpoint == 'chatbot.static'
        or request.endpoint in ('chatbot.login', 'chatbot.setup', 'chatbot.service_worker', 'chatbot.manifest')
        or (request.endpoint and request.endpoint.startswith('chatbot.webhook_'))
        or request.endpoint == 'chatbot.health_check'
        or request.endpoint == 'chatbot.api_keepalive'
    ):
        return None

    # If not authenticated, check if setup is needed or redirect to login
    if not current_user.is_authenticated:
        # API callers get JSON, never a redirect. fetch() follows a 302 to the
        # login page, gets 200 + HTML, and every caller's r.json() then throws —
        # surfacing an expired session as whatever generic error that caller
        # happens to show ("Wissensextraktion fehlgeschlagen"). 401 + JSON lets
        # the frontend say "session expired" and stops the pointless retry.
        if '/api/' in request.path:
            # Logged so an expired session is visible without waiting for someone
            # to report it. Absence of these lines during a reported failure means
            # the request never reached us — proxy/network, not auth.
            logger.warning('API call rejected, not authenticated: %s %s (ua=%.60s)',
                           request.method, request.path,
                           request.headers.get('User-Agent', '-'))
            return jsonify({'error': 'Sitzung abgelaufen — bitte neu anmelden.',
                            'session_expired': True}), 401
        # Use EXISTS for efficiency instead of COUNT (stops at first row)
        has_users = db.session.query(User.id).first() is not None
        if not has_users:
            if request.endpoint != 'chatbot.setup':
                return redirect(url_for('chatbot.setup'))
            return None
        return redirect(url_for('chatbot.login'))

    # Track user online presence and session time
    _track_user_session(current_user)

    return None


# Session inactivity gap (minutes) — gap > this starts a new session
_SESSION_GAP_MINUTES = 15
# Rate-limit last_seen writes to once per this many seconds
_LAST_SEEN_RATE_LIMIT = 60


def _track_user_session(user):
    """Update last_seen and maintain session tracking for online-time stats."""
    from datetime import timedelta

    now = datetime.utcnow()

    # Rate-limit: skip if last_seen was updated less than 60s ago
    if user.last_seen and (now - user.last_seen).total_seconds() < _LAST_SEEN_RATE_LIMIT:
        return

    try:
        gap = timedelta(minutes=_SESSION_GAP_MINUTES)

        if user.last_seen is None or (now - user.last_seen) > gap:
            # New session — either first visit or returning after inactivity
            new_session = UserSession(user_id=user.id, started_at=now, last_active_at=now)
            db.session.add(new_session)
        else:
            # Extend current session — find the latest one and update last_active_at
            latest = UserSession.query.filter_by(user_id=user.id).order_by(
                UserSession.started_at.desc()
            ).first()
            if latest:
                latest.last_active_at = now

        user.last_seen = now
        db.session.commit()
    except Exception:
        db.session.rollback()
        logging.getLogger(__name__).debug('Failed to track user session', exc_info=True)


# ============================================================================
# AUTH ROUTES
# ============================================================================

@chatbot_bp.route('/setup', methods=['GET', 'POST'])
def setup():
    """First-user creation (only works when 0 users exist)"""
    if db.session.query(User.id).first() is not None:
        return redirect(url_for('chatbot.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        display_name = request.form.get('display_name', '').strip()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')

        error = None
        if not username or not display_name or not password:
            error = 'Alle Felder sind erforderlich.'
        elif len(password) < 4:
            error = 'Passwort muss mindestens 4 Zeichen haben.'
        elif password != password_confirm:
            error = 'Passwörter stimmen nicht überein.'

        if error:
            return render_template('chatbot/setup.html', error=error,
                                   username=username, display_name=display_name)

        user = User(username=username, display_name=display_name, is_admin=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        login_user(user, remember=True)
        return redirect(url_for('chatbot.index'))

    return render_template('chatbot/setup.html')


@chatbot_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if db.session.query(User.id).first() is None:
        return redirect(url_for('chatbot.setup'))

    if current_user.is_authenticated:
        return redirect(url_for('chatbot.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=remember)
            return redirect(url_for('chatbot.index'))
        else:
            return render_template('chatbot/login.html', error='Benutzername oder Passwort falsch.',
                                   username=username)

    return render_template('chatbot/login.html')


@chatbot_bp.route('/logout', methods=['POST'])
def logout():
    """User logout"""
    logout_user()
    return redirect(url_for('chatbot.login'))


# ============================================================================
# PAGE ROUTES (HTML Templates)
# ============================================================================

# ---------------------------------------------------------------------------
# Inbox source filters: booking channel (Booking.com / Airbnb / Direkt) and
# Smoobu account. Server-side on purpose — the inbox is paginated, so filtering
# only the cards already on screen leaves the rest hidden behind "Load More"
# (the exact trap the unread filter fell into).
# ---------------------------------------------------------------------------

# channel -> (Conversation.platform values, GuestDetail.booking_channel LIKE)
_CHANNEL_FILTERS = {
    'booking': (('booking', 'booking.com'), '%booking.com%'),
    'airbnb': (('airbnb',), '%airbnb%'),
    'direct': ((), '%direct%'),
    'whatsapp': (('whatsapp',), '%whatsapp%'),
}


def apply_source_filters(query, channel=None, account=None):
    """Add channel/account filters to a Conversation query. Unknown values are ignored.

    Both list paths (Jinja first paint and /api/conversations) go through here.
    """
    if channel in _CHANNEL_FILTERS:
        platforms, like = _CHANNEL_FILTERS[channel]
        guests = db.session.query(GuestDetail.guest_id).filter(
            GuestDetail.detail_key == 'booking_channel',
            GuestDetail.detail_value.ilike(like),
        )
        query = query.filter(db.or_(
            Conversation.platform.in_(platforms),
            Conversation.guest_id.in_(guests),
        ))
    if account:
        cond = Conversation.smoobu_account_id == str(account)
        if str(account) == str(AISettings.get('smoobu_account_id') or ''):
            # Rows written before multi-account carry a NULL tag = primary account.
            cond = db.or_(cond, Conversation.smoobu_account_id.is_(None))
        query = query.filter(cond)
    return query


def smoobu_account_choices():
    """[(account_id, label)] for the inbox account filter; empty when only one account."""
    from .services.smoobu_service import get_smoobu_services
    # ponytail: labels are cosmetic. Override per slot with a
    # smoobu_account_label_<slot> setting if the names ever change.
    defaults = {1: 'Urlaubsmagie', 2: 'Sonnenhof'}
    choices = []
    for svc in get_smoobu_services():
        if not svc.account_id:
            continue
        label = (AISettings.get(f'smoobu_account_label_{svc.slot}')
                 or defaults.get(svc.slot) or f'Konto {svc.slot}')
        choices.append((str(svc.account_id), label))
    return choices if len(choices) > 1 else []


@chatbot_bp.route('/')
def index():
    """Main inbox/dashboard view - shows first page of conversations"""
    channel = request.args.get('channel')
    account = request.args.get('account')
    query = apply_source_filters(
        Conversation.query.options(
            joinedload(Conversation.guest),
            joinedload(Conversation.property)
        ).filter(Conversation.platform != 'playtest'),
        channel, account)
    conversations = query.order_by(Conversation.last_message_at.desc()).limit(50).all()
    total_conversations = query.count()
    preload_last_messages(conversations)
    preload_unread_counts(conversations)
    preload_display_platforms(conversations)
    instant_send = AISettings.get('inbox_umi_instant_send', 'false') == 'true'
    from .services.smoobu_service import get_smoobu_services
    from .services.gmail_service import get_gmail_service
    return render_template('chatbot/inbox.html', conversations=conversations,
                           total_conversations=total_conversations,
                           # ponytail: config presence, not a live check — a dead key still
                           # shows the button; clicking it reports the error.
                           smoobu_connected=any(s.is_configured() for s in get_smoobu_services()),
                           gmail_connected=os.path.exists(get_gmail_service().token_file),
                           smoobu_accounts=smoobu_account_choices(),
                           whatsapp_enabled=bool(os.environ.get('WHATSAPP_BRIDGE_URL')),
                           inbox_instant_send=instant_send)


@chatbot_bp.route('/conversation/<int:conversation_id>')
def conversation_view(conversation_id):
    """Single conversation view with message thread"""
    PAGE_SIZE = 50

    conversation = Conversation.query.options(
        joinedload(Conversation.guest)
    ).get_or_404(conversation_id)

    # Silently pull near-certain email candidates matched to this chat into the
    # thread on open (toggleable). Idempotent; failures must never block the view.
    if AISettings.get('email_autoinsert_on_open', 'true') != 'false':
        try:
            from .services.email_reconcile import promote_email_candidates
            try:
                onopen_threshold = float(AISettings.get('email_onopen_threshold', '0.95'))
            except (TypeError, ValueError):
                onopen_threshold = 0.95
            promote_email_candidates(conversation_id, onopen_threshold)
        except Exception:
            current_app.logger.exception(
                "on-open email promote failed for conv %s", conversation_id)

    # Exclude rejected drafts from all queries
    base_filter = Message.query.filter_by(conversation_id=conversation_id).filter(
        db.or_(Message.approval_status.is_(None), Message.approval_status != 'rejected')
    )

    # Count total messages for "load older" indicator
    total_messages = base_filter.count()

    # Load only the last PAGE_SIZE messages (most recent)
    messages = base_filter.order_by(Message.sent_at.desc()).limit(PAGE_SIZE).all()
    messages.reverse()  # Back to chronological order for display

    has_older = total_messages > len(messages)
    guest = conversation.guest

    # Check platform connection status (only for the relevant platform)
    gmail_connected = False
    smoobu_connected = False
    whatsapp_connected = False
    if conversation.platform == 'email':
        try:
            from .services.gmail_service import get_gmail_service
            gmail = get_gmail_service()
            gmail_connected = gmail.is_authenticated()
        except Exception:
            pass
    elif conversation.platform == 'smoobu':
        try:
            from .services.smoobu_service import get_smoobu_service
            smoobu = get_smoobu_service()
            smoobu_connected = smoobu is not None and smoobu.is_configured()
        except Exception:
            pass
    elif conversation.platform == 'whatsapp':
        try:
            from .services.whatsapp_service import get_whatsapp_service
            # is_configured() only, not get_status(): a live HTTP call to the
            # sidecar on every page render would put a dead bridge in the way
            # of reading the chat. The send path reports a down bridge itself.
            whatsapp_connected = get_whatsapp_service().is_configured()
        except Exception:
            pass

    approval_queue_enabled = AISettings.get('approval_queue_enabled', 'true') != 'false'
    is_playtest = conversation.platform == 'playtest'
    playtest_note = ''
    if is_playtest:
        from .services.playtest_export import load_notes
        playtest_note = load_notes(current_app.instance_path).get(str(conversation.id), '')

    return render_template(
        'chatbot/conversation.html',
        conversation=conversation,
        messages=messages,
        guest=guest,
        gmail_connected=gmail_connected,
        smoobu_connected=smoobu_connected,
        whatsapp_connected=whatsapp_connected,
        has_older=has_older,
        total_messages=total_messages,
        approval_queue_enabled=approval_queue_enabled,
        is_playtest=is_playtest,
        playtest_note=playtest_note
    )


@chatbot_bp.route('/guest/<int:guest_id>')
@login_required
def guest_profile(guest_id):
    """Guest profile view showing all stored memories"""
    from sqlalchemy import func
    guest = Guest.query.get_or_404(guest_id)
    memory_service = get_memory_service()
    profile = memory_service.get_guest_profile(guest_id) if memory_service else {}
    conversations = Conversation.query.filter_by(
        guest_id=guest_id
    ).order_by(Conversation.last_message_at.desc()).all()
    preload_last_messages(conversations)
    preload_unread_counts(conversations)
    preload_display_platforms(conversations)

    # Preload message counts to avoid N+1 in template
    if conversations:
        conv_ids = [c.id for c in conversations]
        count_rows = db.session.query(
            Message.conversation_id, func.count(Message.id)
        ).filter(Message.conversation_id.in_(conv_ids)).group_by(Message.conversation_id).all()
        count_map = dict(count_rows)
        for c in conversations:
            c._cached_message_count = count_map.get(c.id, 0)

    return render_template(
        'chatbot/guest_profile.html',
        guest=guest,
        profile=profile,
        conversations=conversations
    )


@chatbot_bp.route('/statistics')
@login_required
def statistics():
    """Statistics dashboard page"""
    return render_template('chatbot/statistics.html')


@chatbot_bp.route('/settings')
@login_required
def settings():
    """AI settings configuration page"""
    all_settings = AISettings.query.all()
    properties = Property.query.all()
    return render_template('chatbot/settings.html', settings=all_settings, properties=properties,
                           whatsapp_enabled=bool(os.environ.get('WHATSAPP_BRIDGE_URL')))


@chatbot_bp.route('/knowledge')
@login_required
def knowledge_base():
    """UMI page: knowledge, examples, escalation topics, personality, templates."""
    properties = Property.query.order_by(Property.name).all()
    # The Persönlichkeit tab renders the AI settings form — same rows as /settings.
    return render_template('chatbot/knowledge.html', properties=properties,
                           settings=AISettings.query.all())


@chatbot_bp.route('/help')
def help_page():
    """Help and documentation page"""
    return render_template('chatbot/help.html')


@chatbot_bp.route('/viewport-check')
def viewport_check():
    """Throwaway diagnostic: report what the chat layout actually measures on a
    real device. Screenshots can't tell us whether the header is clipped by a
    safe-area inset, a too-tall container, or page scroll — this can.
    Delete once the mobile layout is settled."""
    return """<!doctype html><meta name="viewport"
      content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<style>
  body{font:13px/1.5 monospace;margin:0;padding:12px;background:#111;color:#0f0}
  b{color:#ff0} .bad{color:#f66} .ok{color:#6f6}
  #probe{position:fixed;top:0;left:0;right:0;height:env(safe-area-inset-top,0px);background:#f0f}
</style>
<div id="probe"></div>
<pre id="out">measuring…</pre>
<script>
const px = v => Math.round(v) + 'px';
const cs = getComputedStyle(document.getElementById('probe'));
const rows = {
  'screen (physical)': screen.width + ' x ' + screen.height,
  'window.inner': innerWidth + ' x ' + innerHeight,
  'visualViewport': window.visualViewport
      ? Math.round(visualViewport.width) + ' x ' + Math.round(visualViewport.height) : 'n/a',
  '100dvh resolves to': px(parseFloat(getComputedStyle(document.documentElement).fontSize) * 0 +
      (() => { const d = document.createElement('div'); d.style.height = '100dvh';
               document.body.appendChild(d); const h = d.getBoundingClientRect().height;
               d.remove(); return h; })()),
  'safe-area-inset-top': cs.height + '   <-- 0px means Android gives us nothing',
  'devicePixelRatio': devicePixelRatio,
  'display-mode standalone': matchMedia('(display-mode: standalone)').matches,
  'matches max-width:768px': matchMedia('(max-width: 768px)').matches,
  'page scrolled by': px(scrollY),
  'user agent': navigator.userAgent.slice(0, 90),
};
document.getElementById('out').innerHTML = Object.entries(rows)
  .map(([k, v]) => '<b>' + k.padEnd(24) + '</b>: ' + v).join('\\n');
</script>"""


@chatbot_bp.route('/debug')
def debug_page():
    """Debug dashboard — admin only (first user = admin)."""
    if not current_user.is_authenticated or not current_user.is_admin:
        return redirect(url_for('chatbot.index'))
    return render_template('chatbot/debug.html')


@chatbot_bp.route('/api/debug/logs')
def api_debug_logs():
    """API: get recent log entries."""
    if not current_user.is_authenticated or not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    from .services.debug_service import get_log_handler
    handler = get_log_handler()
    if not handler:
        return jsonify({'entries': [], 'stats': {}})
    level = request.args.get('level')
    logger_name = request.args.get('logger')
    limit = min(int(request.args.get('limit', 200)), 500)
    return jsonify({
        'entries': handler.get_entries(level=level, logger_name=logger_name, limit=limit),
        'stats': handler.get_stats(),
    })


@chatbot_bp.route('/api/debug/api-calls')
def api_debug_api_calls():
    """API: get recent API call history."""
    if not current_user.is_authenticated or not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    from .services.debug_service import get_api_tracker
    tracker = get_api_tracker()
    if not tracker:
        return jsonify({'calls': [], 'summary': {}})
    service = request.args.get('service')
    return jsonify({
        'calls': tracker.get_calls(service=service),
        'summary': tracker.get_summary(),
    })


@chatbot_bp.route('/api/debug/status')
def api_debug_status():
    """API: system status check."""
    if not current_user.is_authenticated or not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    from .services.ai_service import get_ai_service
    from .services.gmail_service import get_gmail_service
    from .services.smoobu_service import get_smoobu_service

    status = {}
    # Ollama
    ai = get_ai_service()
    status['ollama'] = {'connected': ai.test_connection() if ai else False,
                        'model': ai.model if ai else 'N/A'}
    # Gmail
    gmail = get_gmail_service()
    try:
        status['gmail'] = {'connected': gmail.is_authenticated() if gmail else False}
    except Exception:
        status['gmail'] = {'connected': False}
    # Smoobu
    smoobu = get_smoobu_service()
    status['smoobu'] = {'configured': smoobu.is_configured() if smoobu else False,
                        'rate_limit_remaining': smoobu._rate_limit_remaining if smoobu else None}
    # DB
    status['db'] = {
        'conversations': Conversation.query.count(),
        'messages': Message.query.count(),
        'guests': Guest.query.count(),
    }
    return jsonify(status)


# ============================================================================
# CHAT PLAYTEST API (Debug)
# ============================================================================

@chatbot_bp.route('/api/debug/playtest/start', methods=['POST'])
@admin_required
def api_playtest_start():
    """Create a new playtest conversation with optional guest profile."""
    import uuid
    from .services.playtest_events import playtest_log

    data = request.get_json() or {}
    guest_name = data.get('guest_name', 'Playtest Guest')

    # Create a dedicated playtest guest
    guest = Guest(
        name=guest_name,
        email=f"playtest-{uuid.uuid4().hex[:8]}@test.local"
    )
    db.session.add(guest)
    db.session.flush()

    # Create GuestDetail records for each non-empty profile field
    detail_fields = {
        'family': ('family', 'family_info'),
        'pets': ('pet', 'pet_info'),
        'allergies': ('allergy', 'allergy_info'),
        'preferences': ('preference', 'preference_info'),
        'special_requests': ('special_request', 'request_info'),
    }
    for field_name, (detail_type, detail_key) in detail_fields.items():
        value = data.get(field_name, '').strip()
        if value:
            detail = GuestDetail(
                guest_id=guest.id,
                detail_type=detail_type,
                detail_key=detail_key,
                detail_value=value,
                confidence=1.0
            )
            db.session.add(detail)

    # Create playtest conversation — AI enabled, auto-respond OFF by default
    conversation = Conversation(
        guest_id=guest.id,
        platform='playtest',
        platform_id=f"playtest-{uuid.uuid4().hex[:8]}",
        subject=f"Playtest {datetime.utcnow().strftime('%H:%M')}",
        status='active',
        ai_enabled=True,
        auto_respond=False,
        is_read=True
    )
    db.session.add(conversation)
    db.session.commit()

    playtest_log(conversation.id, 'conversation_created',
                 f'Playtest conversation #{conversation.id} created (guest: {guest_name})')

    return jsonify({
        'conversation_id': conversation.id,
        'guest_id': guest.id,
        'guest_name': guest_name
    })


@chatbot_bp.route('/api/debug/playtest/history')
@admin_required
def api_playtest_history():
    """Get recent playtest conversations for the launcher."""
    conversations = Conversation.query.filter_by(
        platform='playtest'
    ).order_by(Conversation.created_at.desc()).limit(10).all()

    return jsonify({
        'conversations': [{
            'id': c.id,
            'guest_name': c.guest.name if c.guest else 'Unknown',
            'created_at': c.created_at.strftime('%d.%m.%Y %H:%M') if c.created_at else '',
        } for c in conversations]
    })


@chatbot_bp.route('/api/debug/playtest/<int:conversation_id>/message', methods=['POST'])
@admin_required
def api_playtest_message(conversation_id):
    """Send a message in a playtest conversation as guest or host."""
    from .services.message_router import get_message_router

    conversation = Conversation.query.get_or_404(conversation_id)
    if conversation.platform != 'playtest':
        return jsonify({'error': 'Not a playtest conversation'}), 400

    data = request.get_json()
    if not data or not data.get('content', '').strip():
        return jsonify({'error': 'Content is required'}), 400

    content = data['content'].strip()
    role = data.get('role', 'guest')
    # Playtest-only auto-reply: when the playtest "Auto-Antwort" toggle is on we
    # generate an AI reply right after storing the guest message. This is an
    # isolated world — it calls generate_ai_response_for_conversation() directly
    # and never consults the global master_ai_enabled switch, so it cannot make
    # real guest conversations auto-respond.
    auto_reply = bool(data.get('auto_reply', False))
    router = get_message_router()

    if role == 'guest':
        result = router.process_incoming_message(
            platform='playtest',
            platform_conversation_id=conversation.platform_id,
            sender_email=conversation.guest.email,
            sender_name=conversation.guest.name,
            message_content=content,
            subject=conversation.subject,
            auto_respond=False,
            skip_push=True
        )
        response = {
            'message_id': result.get('message_id'),
            'success': result.get('success', False)
        }
        if auto_reply and result.get('success'):
            from .services.playtest_events import playtest_log
            # Make THIS playtest conversation auto-send (skip the approval queue)
            # so the full pipeline — including escalation — runs end to end. This
            # is a per-conversation flag on a platform='playtest' chat only: it
            # never changes the global UMI-Freigabe setting or any real chat.
            if not conversation.auto_approve:
                conversation.auto_approve = True
                db.session.commit()
            playtest_log(conversation.id, 'auto_reply',
                         'Playtest auto-reply ON — auto-approve set, generating AI response')
            ai_result = router.generate_ai_response_for_conversation(conversation.id)
            response['ai_message_id'] = ai_result.get('message_id')
            response['ai_success'] = ai_result.get('success', False)
            if not ai_result.get('success'):
                response['ai_error'] = ai_result.get('error')
            # Surface escalation so the playtest UI can show the banner instantly.
            db.session.refresh(conversation)
            response['escalated'] = conversation.escalated
        return jsonify(response)
    elif role == 'host':
        result = router.process_owner_message(
            conversation_id=conversation_id,
            content=content,
            extract_memory=True,
            sent_via_app=True
        )
        return jsonify({
            'message_id': result.get('message_id'),
            'success': result.get('success', False)
        })
    else:
        return jsonify({'error': 'Invalid role — use "guest" or "host"'}), 400


@chatbot_bp.route('/api/debug/playtest/<int:conversation_id>/ai-response', methods=['POST'])
@admin_required
def api_playtest_ai_response(conversation_id):
    """Generate an AI response for a playtest conversation."""
    from .services.message_router import get_message_router

    conversation = Conversation.query.get_or_404(conversation_id)
    if conversation.platform != 'playtest':
        return jsonify({'error': 'Not a playtest conversation'}), 400

    router = get_message_router()
    result = router.generate_ai_response_for_conversation(conversation_id)

    if result.get('success'):
        return jsonify({
            'message_id': result.get('message_id'),
            'content': result.get('response'),
            'success': True
        })
    else:
        return jsonify({'error': result.get('error', 'AI generation failed')}), 500


@chatbot_bp.route('/api/debug/playtest/<int:conversation_id>/events')
@admin_required
def api_playtest_events(conversation_id):
    """Poll for new playtest events."""
    from .services.playtest_events import get_events

    since = request.args.get('since', 0, type=int)
    events, cursor = get_events(conversation_id, since)
    return jsonify({'events': events, 'cursor': cursor})


@chatbot_bp.route('/api/debug/playtest/<int:conversation_id>/messages')
@admin_required
def api_playtest_messages(conversation_id):
    """Get all messages in a playtest conversation."""
    conversation = Conversation.query.get_or_404(conversation_id)
    if conversation.platform != 'playtest':
        return jsonify({'error': 'Not a playtest conversation'}), 400

    messages = Message.query.filter_by(
        conversation_id=conversation_id
    ).order_by(Message.sent_at.asc()).all()

    return jsonify({
        'messages': [m.to_dict() for m in messages]
    })


@chatbot_bp.route('/api/debug/playtest/<int:conversation_id>/note', methods=['POST'])
@admin_required
def api_playtest_note(conversation_id):
    """Save a free-text review note for a playtest conversation."""
    from .services.playtest_export import save_note

    conversation = Conversation.query.get_or_404(conversation_id)
    if conversation.platform != 'playtest':
        return jsonify({'error': 'Not a playtest conversation'}), 400

    data = request.get_json() or {}
    note = (data.get('note') or '').strip()
    save_note(current_app.instance_path, conversation_id, note)
    return jsonify({'success': True})


@chatbot_bp.route('/api/debug/playtest/export', methods=['POST'])
@admin_required
def api_playtest_export():
    """Export all playtest conversations to PLAYTEST_LOG.md for later review."""
    from .services.playtest_export import export_playtest_log

    result = export_playtest_log(current_app._get_current_object())
    return jsonify(result)


# ============================================================================
# API ROUTES (JSON Responses)
# ============================================================================

@chatbot_bp.route('/api/conversations/last-updated', methods=['GET'])
def api_conversations_last_updated():
    """Lightweight check: returns the most recent updated_at and unread count.
    Used by the inbox poller to decide whether a full fetch is needed."""
    from sqlalchemy import func
    ts_result = db.session.query(func.max(Conversation.updated_at)).filter(
        Conversation.platform != 'playtest'
    ).scalar()
    unread = db.session.query(func.count(Conversation.id)).filter(
        Conversation.is_read == False,
        Conversation.platform != 'playtest'
    ).scalar()
    ts = ts_result.isoformat() if ts_result else None
    return jsonify({'ts': ts, 'unread': unread})


@chatbot_bp.route('/api/conversations', methods=['GET'])
def api_get_conversations():
    """Get all conversations with pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status')

    query = Conversation.query.options(joinedload(Conversation.guest), joinedload(Conversation.property))
    query = query.filter(Conversation.platform != 'playtest')
    if status == 'pending_approval':
        query = query.filter(Conversation.id.in_(
            db.session.query(Message.conversation_id)
            .filter(Message.approval_status == 'pending')
            .distinct()
        ))
    elif status:
        query = query.filter_by(status=status)
    escalated = request.args.get('escalated')
    if escalated == 'true':
        # Open escalations only — the same set the inbox badge counts, so
        # clicking a badge showing 19 shows exactly 19. A closed chat is
        # handled, whatever its stale escalated flag says.
        query = query.filter(Conversation.escalated == True,
                             Conversation.status != 'closed')
    # Unread filter is server-side so the inbox shows ALL unread conversations, not
    # just the unread ones on the currently loaded page (the client-side filter alone
    # hid old unread behind "Load More").
    if request.args.get('unread') == 'true':
        query = query.filter(Conversation.is_read == False)
    query = apply_source_filters(query, request.args.get('channel'),
                                 request.args.get('account'))

    pagination = query.order_by(Conversation.last_message_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Preload last messages and unread counts in batch queries instead of N+1
    preload_last_messages(pagination.items)
    preload_unread_counts(pagination.items)
    preload_display_platforms(pagination.items)

    # Get conversation IDs with pending approvals
    pending_conv_ids = set(
        row[0] for row in db.session.query(Message.conversation_id)
        .filter(Message.approval_status == 'pending')
        .distinct()
        .all()
    )

    conv_list = []
    for c in pagination.items:
        conv_dict = c.to_dict()
        conv_dict['has_pending_approval'] = c.id in pending_conv_ids
        conv_list.append(conv_dict)

    return jsonify({
        'conversations': conv_list,
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page
    })


@chatbot_bp.route('/api/search', methods=['GET'])
def api_search():
    """
    Search messages using FTS5 with BM25 ranking.
    Returns results grouped by conversation with snippets.
    """
    import html
    from .utils.search import search_messages, get_search_snippet

    def sanitize_snippet(snippet):
        """Sanitize snippet to prevent XSS while allowing <mark> tags."""
        if not snippet:
            return None
        escaped = html.escape(snippet)
        escaped = escaped.replace('&lt;mark&gt;', '<mark>')
        escaped = escaped.replace('&lt;/mark&gt;', '</mark>')
        return escaped

    query = request.args.get('q', '').strip()
    platform = request.args.get('platform')
    status = request.args.get('status')

    # Handle empty query
    if not query:
        return jsonify({'results': [], 'query': '', 'total': 0})

    # Get FTS5 results
    results = search_messages(query, limit=100)

    # Get snippets and sanitize
    for r in results:
        snippet = get_search_snippet(query, r['message_id'])
        r['snippet'] = sanitize_snippet(snippet)

    # Optionally filter by platform/status
    if platform:
        results = [r for r in results if r['platform'] == platform]
    if status:
        # Need to get conversation status - fetch from DB
        conv_statuses = {}
        conv_ids = list(set(r['conversation_id'] for r in results))
        if conv_ids:
            convs = Conversation.query.filter(Conversation.id.in_(conv_ids)).all()
            conv_statuses = {c.id: c.status for c in convs}
        results = [r for r in results if conv_statuses.get(r['conversation_id']) == status]

    # Group results by conversation
    grouped = {}
    guest_ids_for_channel = set()
    for r in results:
        conv_id = r['conversation_id']
        if conv_id not in grouped:
            grouped[conv_id] = {
                'conversation_id': conv_id,
                'guest_name': r['guest_name'],
                'guest_id': r['guest_id'],
                'subject': r['subject'],
                'property_name': r.get('property_name'),
                'platform': r['platform'],
                'display_platform': r['platform'].capitalize() if r['platform'] else '',
                'match_count': 0,
                'first_snippet': None
            }
            if r['platform'] == 'smoobu' and r.get('guest_id'):
                guest_ids_for_channel.add(r['guest_id'])
        grouped[conv_id]['match_count'] += 1
        if grouped[conv_id]['first_snippet'] is None:
            grouped[conv_id]['first_snippet'] = r.get('snippet')

    # Also search Guest fields (name/email/phone) so guests are findable even
    # when the query text never appears in any message body.
    like = f'%{query}%'
    guest_matches = Guest.query.filter(
        db.or_(
            Guest.name.ilike(like),
            Guest.email.ilike(like),
            Guest.phone.ilike(like),
        )
    ).limit(50).all()
    if guest_matches:
        guest_ids = [g.id for g in guest_matches]
        guest_by_id = {g.id: g for g in guest_matches}
        guest_convs = (
            Conversation.query
            .filter(Conversation.guest_id.in_(guest_ids))
            .filter(Conversation.platform != 'playtest')
            .options(joinedload(Conversation.property))
            .limit(50)
            .all()
        )
        for conv in guest_convs:
            # Apply the same platform/status filters as the FTS path
            if platform and conv.platform != platform:
                continue
            if status and conv.status != status:
                continue
            if conv.id in grouped:
                continue  # already added by FTS — dedupe
            g = guest_by_id.get(conv.guest_id)
            prop_name = conv.property.name if conv.property else None
            grouped[conv.id] = {
                'conversation_id': conv.id,
                'guest_name': g.name if g else None,
                'guest_id': conv.guest_id,
                'subject': conv.subject,
                'property_name': prop_name,
                'platform': conv.platform,
                'display_platform': conv.platform.capitalize() if conv.platform else '',
                'match_count': 0,
                'first_snippet': None,
            }
            if conv.platform == 'smoobu' and conv.guest_id:
                guest_ids_for_channel.add(conv.guest_id)

    # Batch-resolve booking channels for Smoobu conversations
    if guest_ids_for_channel:
        channels = GuestDetail.query.filter(
            GuestDetail.guest_id.in_(list(guest_ids_for_channel)),
            GuestDetail.detail_key == 'booking_channel'
        ).all()
        channel_map = {ch.guest_id: ch.detail_value for ch in channels}
        for g in grouped.values():
            if g['platform'] == 'smoobu' and g.get('guest_id') in channel_map:
                g['display_platform'] = channel_map[g['guest_id']]

    return jsonify({
        'results': list(grouped.values()),
        'query': query,
        'total': len(grouped)
    })


@chatbot_bp.route('/api/search/rebuild', methods=['POST'])
def api_rebuild_search_index():
    """Admin endpoint: rebuild FTS5 search index from scratch."""
    if not current_user.is_authenticated or not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403

    from .utils.search import rebuild_search_index
    from sqlalchemy import text

    msg_count = db.session.execute(text("SELECT COUNT(*) FROM message")).scalar()
    success = rebuild_search_index()

    if success:
        fts_count = db.session.execute(text("SELECT COUNT(*) FROM message_fts")).scalar()
        return jsonify({
            'success': True,
            'messages_total': msg_count,
            'messages_indexed': fts_count
        })
    else:
        return jsonify({'success': False, 'error': 'Rebuild failed — check server logs'}), 500


@chatbot_bp.route('/api/conversations/<int:conversation_id>/messages', methods=['GET'])
def api_get_messages(conversation_id):
    """Get messages for a specific conversation.

    Query params:
        after: Only return messages with id > this value (for polling new messages)
        before: Only return messages with id < this value (for loading older messages)
        limit: Max messages to return (default 50)
    """
    conversation = Conversation.query.get_or_404(conversation_id)
    after_id = request.args.get('after', type=int)
    before_id = request.args.get('before', type=int)
    limit = request.args.get('limit', 50, type=int)

    query = Message.query.filter_by(conversation_id=conversation_id).filter(
        db.or_(Message.approval_status.is_(None), Message.approval_status != 'rejected')
    )

    if after_id:
        # Polling: only new messages after the last known ID
        query = query.filter(Message.id > after_id)
        messages = query.order_by(Message.sent_at.asc()).all()
        return jsonify({
            'conversation_id': conversation_id,
            'messages': [m.to_dict() for m in messages],
            'escalated': conversation.escalated
        })

    if before_id:
        # Load older: get messages before a given ID, newest first, then reverse
        query = query.filter(Message.id < before_id)
        messages = query.order_by(Message.sent_at.desc()).limit(limit).all()
        messages.reverse()
        has_more = query.count() > limit
        return jsonify({
            'conversation_id': conversation_id,
            'messages': [m.to_dict() for m in messages],
            'has_more': has_more,
            'escalated': conversation.escalated
        })

    # Default: return last N messages
    messages = query.order_by(Message.sent_at.desc()).limit(limit).all()
    messages.reverse()
    return jsonify({
        'conversation_id': conversation_id,
        'messages': [m.to_dict() for m in messages],
        'escalated': conversation.escalated
    })


@chatbot_bp.route('/api/conversations/mark-all-read', methods=['PATCH'])
def api_mark_all_read():
    """Mark all unread conversations as read — advances cursor to latest message for each."""
    from sqlalchemy import func

    unread_convs = Conversation.query.filter_by(is_read=False).all()
    if not unread_convs:
        return jsonify({'success': True, 'marked': 0})

    # Batch-fetch max message ID per conversation in a single query
    conv_ids = [c.id for c in unread_convs]
    max_ids = dict(db.session.query(
        Message.conversation_id, func.max(Message.id)
    ).filter(Message.conversation_id.in_(conv_ids)).group_by(Message.conversation_id).all())

    for conv in unread_convs:
        max_id = max_ids.get(conv.id)
        if max_id and (not conv.last_read_message_id or max_id > conv.last_read_message_id):
            conv.last_read_message_id = max_id
        conv.is_read = True

    db.session.commit()
    return jsonify({'success': True, 'marked': len(unread_convs)})


@chatbot_bp.route('/api/conversations/<int:conversation_id>/read', methods=['PATCH'])
def api_mark_conversation_read(conversation_id):
    """Mark a conversation as read by advancing the read cursor.

    Accepts optional JSON body: { "last_message_id": 123 }
    If not provided, uses the conversation's latest message ID.
    """
    conversation = Conversation.query.get_or_404(conversation_id)

    data = request.get_json(silent=True) or {}
    last_message_id = data.get('last_message_id')

    if not last_message_id:
        # Highest message ID — unread is derived by ID (recompute_is_read), and
        # backfilled/email-recovered messages carry an old sent_at with a new ID.
        # Message.query, not conversation.messages: the dynamic relationship
        # appends to its own order_by and would hand back the OLDEST message.
        latest = Message.query.filter_by(conversation_id=conversation.id).order_by(
            Message.id.desc()).first()
        last_message_id = latest.id if latest else None

    changed = False
    if last_message_id:
        # Only advance the cursor forward, never backward
        if not conversation.last_read_message_id or last_message_id > conversation.last_read_message_id:
            conversation.last_read_message_id = last_message_id
            changed = True

    # Derive is_read from cursor (handles race: new guest msg may have arrived since page load)
    if conversation.recompute_is_read():
        changed = True

    if changed:
        db.session.commit()

    return jsonify({'success': True, 'is_read': conversation.is_read, 'last_read_message_id': conversation.last_read_message_id})


@chatbot_bp.route('/api/conversations/<int:conversation_id>/unread', methods=['POST'])
@login_required
def api_mark_conversation_unread(conversation_id):
    """Mark a conversation as unread: rewind the read cursor and recompute is_read.

    Counterpart to /read (which only advances the cursor forward). Used by the
    inbox ⋮ menu to re-flag a chat. Unread only takes effect if a guest message
    exists — recompute_is_read derives is_read from the (now-cleared) cursor.
    """
    conversation = Conversation.query.get_or_404(conversation_id)
    conversation.last_read_message_id = None
    conversation.recompute_is_read()
    db.session.commit()
    return jsonify({'success': True, 'is_read': conversation.is_read})


@chatbot_bp.route('/api/conversations/<int:conversation_id>/messages', methods=['POST'])
def api_send_message(conversation_id):
    """Send a new message in a conversation (owner message)"""
    conversation = Conversation.query.get_or_404(conversation_id)
    data = request.get_json()

    if not data or 'content' not in data:
        return jsonify({'error': 'Content is required'}), 400

    content = data['content']

    # This generic local-store endpoint does NOT send to any platform, so without a
    # duplicate guard it silently creates a phantom copy of a reply that was already
    # delivered via the Smoobu/Gmail path — a second DB row shown twice in our app
    # while the guest was messaged only once. Same per-conversation lock + guard as
    # the platform-send paths, so a concurrent local + platform send can't race.
    with _conversation_send_lock(conversation_id):
        if _recent_duplicate_owner_reply(conversation_id, content):
            logger.info(f"Duplicate local message skipped for conversation {conversation_id}")
            return jsonify({'success': True, 'duplicate_skipped': True,
                            'content': content}), 200

        # The platform-send paths fall back here when Smoobu/Gmail refuses the
        # message. Stamp it so the thread shows "not delivered" with a retry —
        # without this the bubble is indistinguishable from a delivered one and
        # nobody learns the guest never got it.
        failed_marker = (f"{Message.FAILED_PREFIX}{uuid.uuid4().hex}"
                         if data.get('delivery_failed') else None)

        # Create owner message
        message = Message(
            conversation_id=conversation_id,
            sender_type='owner',
            content=content,
            platform_message_id=failed_marker,
            sent_at=datetime.utcnow(),
            sent_via_app=True,
            user_id=current_user.id if current_user.is_authenticated else None
        )
        db.session.add(message)
        now_ts = datetime.utcnow()
        conversation.updated_at = now_ts
        msg_sent_at = message.sent_at or now_ts
        if not conversation.last_message_at or msg_sent_at > conversation.last_message_at:
            conversation.last_message_at = msg_sent_at

        # Assign conversation to the user who is responding
        if current_user.is_authenticated and conversation.user_id is None:
            conversation.user_id = current_user.id

        db.session.commit()

    # Store correction if host edited an AI draft
    correction_saved = False
    original_ai_content = data.get('original_ai_content')
    if original_ai_content:
        correction_saved = _store_correction_if_needed(original_ai_content, data['content'], conversation) is not None

    response_data = message.to_dict()
    response_data['correction_saved'] = correction_saved

    # Process memory extraction in background thread (non-blocking)
    message_id = message.id
    app = current_app._get_current_object()

    def _extract_memory():
        with app.app_context():
            try:
                msg = Message.query.get(message_id)
                if msg:
                    ms = get_memory_service()
                    if ms:
                        ms.process_message_for_memory(msg)
            except Exception as e:
                logger.warning(f"Background memory extraction failed: {e}")

    threading.Thread(target=_extract_memory, daemon=True).start()

    return jsonify(response_data), 201


@chatbot_bp.route('/api/conversations/<int:conversation_id>/ai-response', methods=['POST'])
def api_generate_ai_response(conversation_id):
    """Generate an AI response for a conversation"""
    conversation = Conversation.query.get_or_404(conversation_id)

    # When set, always save the reply as a pending draft (never auto-send),
    # regardless of the conversation's auto_approve. The inbox ⋮ menu uses this
    # so it can preview-then-approve (or approve instantly) uniformly.
    draft_only = bool((request.get_json(silent=True) or {}).get('draft_only'))

    if not conversation.ai_enabled:
        return jsonify({'error': 'AI is disabled for this conversation'}), 400

    ai_service = get_ai_service()
    memory_service = get_memory_service()

    if not ai_service:
        return jsonify({'error': 'AI service not initialized'}), 503

    # Quick connection check
    if not ai_service.test_connection():
        return jsonify({'error': 'Cannot connect to Ollama. Is the server running?'}), 503

    # Delete any existing pending draft before generating a new one
    existing_pending = Message.query.filter_by(
        conversation_id=conversation_id,
        approval_status='pending'
    ).first()
    if existing_pending:
        db.session.delete(existing_pending)
        db.session.commit()

    try:
        # Read AI settings from DB
        tone = AISettings.get('ai_response_tone', 'friendly_professional')
        host_instructions = AISettings.get('host_instructions', '')
        max_history = int(AISettings.get('max_conversation_history', '10'))

        # Get conversation context (exclude pending/rejected drafts from history)
        messages = conversation.messages.filter(
            db.or_(Message.approval_status.is_(None), Message.approval_status == 'approved')
        ).order_by(Message.sent_at.desc()).limit(max_history).all()
        messages.reverse()

        if not messages:
            return jsonify({'error': 'No messages in conversation'}), 400

        # Query latest guest message directly (bypass relationship default ordering)
        latest_guest_message, question_text = pending_guest_question(conversation)

        if not latest_guest_message:
            return jsonify({'error': 'No guest message to respond to'}), 400

        # Check if the latest guest message is a pure acknowledgment (Ok, Gut, etc.)
        # Checked against the full pending text, not just the newest message: an
        # "Ok" after an unanswered question must not skip the question.
        if ai_service.is_acknowledgment(question_text):
            logger.info(f"[AI SKIP] Acknowledgment detected in auto-response: '{question_text[:50]}'")
            return jsonify({'skipped': True, 'reason': 'acknowledgment',
                           'message': 'No response needed — guest acknowledged your message.'}), 200

        # Get guest profile
        profile = memory_service.get_guest_profile(conversation.guest_id) if memory_service else {}

        # Get property info if available
        property_info = conversation.property.to_dict() if conversation.property else None

        # Reservation context from locally-stored fields (no blocking live Smoobu
        # call — see _local_reservation_info).
        reservation_info = _local_reservation_info(conversation)

        # Load knowledge base entries for AI context
        knowledge_entries = []
        try:
            knowledge_entries = KnowledgeEntry.load_for_conversation_context(conversation)
        except Exception as e:
            logger.warning(f"Failed to load knowledge entries: {e}")

        # Load corrections
        corrections = []
        try:
            corrections = KnowledgeEntry.load_corrections_for(conversation)
        except Exception as e:
            logger.warning(f"Failed to load corrections: {e}")

        # Load conversation summary
        conversation_summary = conversation.ai_summary

        # Apply context filter
        from .services.context_filter import ContextFilter
        filtered = ContextFilter.filter(
            latest_message=question_text,
            conversation_history=[m.to_dict() for m in messages],
            knowledge_entries=knowledge_entries,
            guest_profile=profile,
            property_info=property_info,
            corrections=corrections,
            reservation_info=reservation_info,
        )
        logger.debug(f"[CONTEXT FILTER] generate: {filtered.filter_log}")

        # Generate AI response
        ai_response = ai_service.generate_guest_response(
            guest_profile=filtered.guest_profile,
            conversation_history=[m.to_dict() for m in messages],
            latest_message=question_text,
            property_info=filtered.property_info,
            tone=tone,
            host_instructions=host_instructions,
            conversation_subject=conversation.subject,
            max_history=max_history,
            reservation_info=filtered.reservation_info,
            knowledge_entries=filtered.knowledge_entries,
            conversation_summary=conversation_summary,
            corrections=filtered.corrections,
            resolved_topics=filtered.resolved_topics,
            is_closing=filtered.is_closing,
        )
        if ai_response:
            ai_response, _ = ai_service.parse_escalation(ai_response)

        if not ai_response:
            return jsonify({'error': 'AI response timed out. The model may be loading - try again.'}), 504

        # Save AI message
        ai_message = Message(
            conversation_id=conversation_id,
            sender_type='ai',
            content=ai_response,
            sent_at=datetime.utcnow()
        )
        db.session.add(ai_message)
        now_ts = datetime.utcnow()
        conversation.updated_at = now_ts
        ai_sent_at = ai_message.sent_at or now_ts
        if not conversation.last_message_at or ai_sent_at > conversation.last_message_at:
            conversation.last_message_at = ai_sent_at
        db.session.commit()

        # Check if approval queue is enabled (respects per-conversation auto-approve)
        approval_queue_enabled = AISettings.get('approval_queue_enabled', 'true') == 'true'

        if draft_only or (approval_queue_enabled and not conversation.auto_approve):
            ai_message.approval_status = 'pending'
            db.session.commit()
            return jsonify({
                'success': True,
                'approval_status': 'pending',
                'message': ai_message.to_dict()
            })
        else:
            # Queue disabled: send immediately via platform
            email_sent = False
            smoobu_sent = False
            if conversation.platform == 'email':
                try:
                    from .services.gmail_service import get_gmail_service
                    gmail = get_gmail_service()
                    if gmail.is_authenticated():
                        guest = conversation.guest
                        send_result = gmail.send_email(
                            to=guest.email,
                            subject=conversation.subject or 'Re: Your inquiry',
                            body=ai_response,
                            thread_id=conversation.platform_id,
                            reply_to_message_id=latest_guest_message.platform_message_id if latest_guest_message.platform_message_id else None
                        )
                        email_sent = bool(send_result)
                        if not email_sent:
                            logger.warning(f"Failed to send AI response via Gmail for conversation {conversation_id}")
                except Exception as e:
                    logger.error(f"Error sending AI response via Gmail: {e}")
            elif conversation.platform == 'smoobu' and conversation.smoobu_reservation_id:
                try:
                    from .services.smoobu_service import get_smoobu_service_for
                    smoobu = get_smoobu_service_for(conversation)
                    if smoobu and smoobu.is_configured():
                        send_result = smoobu.send_message(conversation.smoobu_reservation_id, ai_response)
                        smoobu_sent = bool(send_result)
                        if smoobu_sent and isinstance(send_result, dict):
                            # Set platform_message_id to prevent duplicate on next sync
                            smoobu_msg_id = str(send_result.get('id') or send_result.get('message_id')
                                               or send_result.get('messageId') or '')
                            if smoobu_msg_id:
                                ai_message.platform_message_id = (
                                    f"smoobu-{conversation.smoobu_reservation_id}-{smoobu_msg_id}")
                                db.session.commit()
                        if not smoobu_sent:
                            logger.warning(f"Failed to send AI response via Smoobu for conversation {conversation_id}")
                except Exception as e:
                    logger.error(f"Error sending AI response via Smoobu: {e}")

            response = ai_message.to_dict()
            response['email_sent'] = email_sent
            response['smoobu_sent'] = smoobu_sent
            return jsonify(response), 201

    except MemoryError:
        logger.error("MemoryError during AI response generation - model may be too large")
        db.session.rollback()
        return jsonify({'error': 'Out of memory. The AI model may be too large for your system. Try a smaller model in Settings.'}), 503
    except Exception as e:
        logger.error(f"Unexpected error generating AI response: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'error': f'AI generation failed: {str(e)}'}), 500


from .services.ai_service import local_reservation_info as _local_reservation_info


def _ai_timing_log(line: str):
    """Append an AI-timing line to instance/ai_timing.log via a direct file
    write. The Python logging file-handler isn't attached in the Waitress
    production process (chatbot.log goes stale), so we reuse the same
    direct-append channel that smoobu_webhooks.log uses — proven to write in
    prod. ponytail: direct write; drop it if logger-to-disk ever gets fixed.
    """
    try:
        log_path = os.path.join(current_app.instance_path, 'ai_timing.log')
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"{datetime.utcnow().isoformat()} {line}\n")
    except Exception:
        pass


@chatbot_bp.route('/api/conversations/<int:conversation_id>/ai-suggest', methods=['POST'])
def api_suggest_ai_response(conversation_id):
    """Generate an AI response suggestion without saving it"""
    conversation = Conversation.query.get_or_404(conversation_id)

    if not conversation.ai_enabled:
        return jsonify({'error': 'AI is disabled for this conversation'}), 400

    ai_service = get_ai_service()
    memory_service = get_memory_service()

    if not ai_service:
        return jsonify({'error': 'AI service not initialized'}), 503

    # Quick connection check
    if not ai_service.test_connection():
        return jsonify({'error': 'Cannot connect to Ollama. Is the server running?'}), 503

    # Check if debug info was requested
    request_data = request.get_json(silent=True) or {}
    include_debug = request_data.get('debug', False)

    _t_start = time.monotonic()
    try:
        # Read AI settings from DB
        tone = AISettings.get('ai_response_tone', 'friendly_professional')
        host_instructions = AISettings.get('host_instructions', '')
        max_history = int(AISettings.get('max_conversation_history', '10'))

        # Get conversation context
        messages = conversation.messages.filter(
            db.or_(Message.approval_status.is_(None), Message.approval_status == 'approved')
        ).order_by(Message.sent_at.desc()).limit(max_history).all()
        messages.reverse()

        if not messages:
            return jsonify({'error': 'No messages in conversation'}), 400

        # Query latest guest message directly (bypass relationship default ordering)
        latest_guest_message, question_text = pending_guest_question(conversation)
        logger.info(f"[AI SUGGEST] answering everything since our last reply: newest_id={latest_guest_message.id if latest_guest_message else None}, chars={len(question_text)}, text='{question_text[:80]}...'")

        if not latest_guest_message:
            return jsonify({'error': 'No guest message to respond to'}), 400

        # Check if the latest guest message is a pure acknowledgment (Ok, Gut, etc.)
        # Checked against the full pending text, not just the newest message: an
        # "Ok" after an unanswered question must not skip the question.
        if ai_service.is_acknowledgment(question_text):
            logger.info(f"[AI SKIP] Acknowledgment detected: '{question_text[:50]}' — no response needed")
            result = {'suggestion': None, 'skipped': True, 'reason': 'acknowledgment'}
            if include_debug:
                result['debug_context'] = {
                    'latest_guest_message': question_text,
                    'skip_reason': 'Message is a pure acknowledgment (e.g. Ok, Gut, Alright) — no response needed',
                }
            return jsonify(result)

        # Get guest profile
        profile = memory_service.get_guest_profile(conversation.guest_id) if memory_service else {}

        # Get property info if available
        property_info = conversation.property.to_dict() if conversation.property else None

        # Build reservation context from locally-stored fields instead of a live
        # Smoobu call — that call added ~11s of blocking prep on the suggest hot
        # path (see [SUGGEST TIMING]). Guest counts are synced onto the
        # conversation by the reservation sync/webhook.
        reservation_info = _local_reservation_info(conversation)

        # Load knowledge base entries for AI context
        knowledge_entries = []
        try:
            knowledge_entries = KnowledgeEntry.load_for_conversation_context(conversation)
        except Exception as e:
            logger.warning(f"Failed to load knowledge entries: {e}")

        # Load corrections
        corrections = []
        try:
            corrections = KnowledgeEntry.load_corrections_for(conversation)
        except Exception as e:
            logger.warning(f"Failed to load corrections: {e}")

        # Load conversation summary
        conversation_summary = conversation.ai_summary

        # Apply context filter
        from .services.context_filter import ContextFilter
        filtered = ContextFilter.filter(
            latest_message=question_text,
            conversation_history=[m.to_dict() for m in messages],
            knowledge_entries=knowledge_entries,
            guest_profile=profile,
            property_info=property_info,
            corrections=corrections,
            reservation_info=reservation_info,
        )
        logger.debug(f"[CONTEXT FILTER] suggest: {filtered.filter_log}")

        # Generate AI response (but don't save it)
        _t_prep_done = time.monotonic()
        ai_response = ai_service.generate_guest_response(
            guest_profile=filtered.guest_profile,
            conversation_history=[m.to_dict() for m in messages],
            latest_message=question_text,
            property_info=filtered.property_info,
            tone=tone,
            host_instructions=host_instructions,
            conversation_subject=conversation.subject,
            max_history=max_history,
            reservation_info=filtered.reservation_info,
            knowledge_entries=filtered.knowledge_entries,
            conversation_summary=conversation_summary,
            corrections=filtered.corrections,
            resolved_topics=filtered.resolved_topics,
            is_closing=filtered.is_closing,
        )
        _t_model_done = time.monotonic()
        if ai_response:
            ai_response, _ = ai_service.parse_escalation(ai_response)
        # prep = our code + DB + Smoobu fetch; model = generate_guest_response
        # (the Ollama round-trip, also logged as [AI CALL]); post = everything after.
        _ai_timing_log(
            f"[SUGGEST TIMING] conv={conversation_id} | "
            f"prep={_t_prep_done - _t_start:.1f}s "
            f"model={_t_model_done - _t_prep_done:.1f}s "
            f"post={time.monotonic() - _t_model_done:.1f}s "
            f"total={time.monotonic() - _t_start:.1f}s"
        )

        if not ai_response:
            return jsonify({'error': 'AI response timed out. The model may be loading - try again.'}), 504

        # Build response
        result = {'suggestion': ai_response}

        # Include debug context if requested (shows what the AI received)
        if include_debug:
            result['debug_context'] = {
                'latest_guest_message': question_text,
                'messages_count': len(messages),
                'messages_used': [
                    {'sender': m.sender_type, 'preview': m.content[:100]} for m in messages
                ],
                'guest_profile': filtered.guest_profile if profile else None,
                'property': property_info.get('name') if property_info else None,
                'reservation': bool(reservation_info),
                'tone': tone,
                'has_host_instructions': bool(host_instructions and host_instructions.strip()),
                'conversation_subject': conversation.subject,
                'context_filter': filtered.filter_log,
            }

        return jsonify(result)

    except MemoryError:
        logger.error("MemoryError during AI suggestion - model may be too large")
        return jsonify({'error': 'Out of memory. Try a smaller model in Settings.'}), 503
    except Exception as e:
        logger.error(f"Unexpected error generating AI suggestion: {e}", exc_info=True)
        return jsonify({'error': f'AI suggestion failed: {str(e)}'}), 500


@chatbot_bp.route('/api/conversations/<int:conversation_id>/ai-suggest-for-message', methods=['POST'])
def api_suggest_for_message(conversation_id):
    """Generate an AI suggestion targeting a specific guest message"""
    conversation = Conversation.query.get_or_404(conversation_id)

    if not conversation.ai_enabled:
        return jsonify({'error': 'AI is disabled for this conversation'}), 400

    request_data = request.get_json(silent=True) or {}
    message_id = request_data.get('message_id')
    if not message_id:
        return jsonify({'error': 'message_id is required'}), 400

    # Validate message belongs to this conversation and is from a guest
    target_message = Message.query.filter_by(
        id=message_id,
        conversation_id=conversation_id,
        sender_type='guest'
    ).first()
    if not target_message:
        return jsonify({'error': 'Guest message not found in this conversation'}), 404

    ai_service = get_ai_service()
    memory_service = get_memory_service()

    if not ai_service:
        return jsonify({'error': 'AI service not initialized'}), 503

    if not ai_service.test_connection():
        return jsonify({'error': 'Cannot connect to Ollama. Is the server running?'}), 503

    _t_start = time.monotonic()
    try:
        tone = AISettings.get('ai_response_tone', 'friendly_professional')
        host_instructions = AISettings.get('host_instructions', '')
        max_history = int(AISettings.get('max_conversation_history', '10'))

        # Get conversation history for read-only context
        messages = conversation.messages.filter(
            db.or_(Message.approval_status.is_(None), Message.approval_status == 'approved')
        ).order_by(Message.sent_at.desc()).limit(max_history).all()
        messages.reverse()

        # Get guest profile and property info
        profile = memory_service.get_guest_profile(conversation.guest_id) if memory_service else {}
        property_info = conversation.property.to_dict() if conversation.property else None

        # Clean target message content
        target_content = target_message.content or ''

        # Reservation context from locally-stored fields (no blocking live Smoobu
        # call — see _local_reservation_info).
        reservation_info = _local_reservation_info(conversation)

        # Knowledge base (exclude corrections)
        knowledge_entries = []
        try:
            knowledge_entries = KnowledgeEntry.load_for_conversation_context(conversation)
        except Exception as e:
            logger.warning(f"Failed to load knowledge entries for per-message suggest: {e}")

        # Past corrections
        corrections = []
        try:
            corrections = KnowledgeEntry.load_corrections_for(conversation)
        except Exception as e:
            logger.warning(f"Failed to load corrections: {e}")

        conversation_summary = conversation.ai_summary

        # Context filter narrows KB/profile to what's relevant to the target message
        from .services.context_filter import ContextFilter
        filtered = ContextFilter.filter(
            latest_message=target_content,
            conversation_history=[m.to_dict() for m in messages],
            knowledge_entries=knowledge_entries,
            guest_profile=profile,
            property_info=property_info,
            corrections=corrections,
            reservation_info=reservation_info,
        )

        # Generate, still targeting THIS specific message, now with full context.
        # resolved_topics is deliberately omitted: the host explicitly chose to
        # answer this message, so we must NOT suppress it as "already resolved".
        _t_prep_done = time.monotonic()
        ai_response = ai_service.generate_guest_response(
            guest_profile=filtered.guest_profile,
            conversation_history=[m.to_dict() for m in messages],
            latest_message=target_content,
            property_info=filtered.property_info,
            tone=tone,
            host_instructions=host_instructions,
            conversation_subject=conversation.subject,
            max_history=max_history,
            reservation_info=filtered.reservation_info,
            knowledge_entries=filtered.knowledge_entries,
            conversation_summary=conversation_summary,
            corrections=filtered.corrections,
            resolved_topics=None,
            is_closing=False,
            target_message_override=target_content,
        )
        _t_model_done = time.monotonic()
        if ai_response:
            ai_response, _ = ai_service.parse_escalation(ai_response)
        # prep = our code + DB + Smoobu fetch; model = generate_guest_response
        # (the Ollama round-trip, also logged as [AI CALL]); post = everything after.
        _ai_timing_log(
            f"[SUGGEST TIMING] conv={conversation_id} msg={message_id} | "
            f"prep={_t_prep_done - _t_start:.1f}s "
            f"model={_t_model_done - _t_prep_done:.1f}s "
            f"post={time.monotonic() - _t_model_done:.1f}s "
            f"total={time.monotonic() - _t_start:.1f}s"
        )

        if not ai_response:
            return jsonify({'error': 'AI response timed out. The model may be loading - try again.'}), 504

        return jsonify({
            'suggestion': ai_response,
            'target_message_id': message_id,
        })

    except MemoryError:
        logger.error("MemoryError during per-message AI suggestion")
        db.session.rollback()
        return jsonify({'error': 'Out of memory. Try a smaller model in Settings.'}), 503
    except Exception as e:
        logger.error(f"Error in per-message AI suggest: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'error': f'AI generation failed: {str(e)}'}), 500


@chatbot_bp.route('/api/guests/<int:guest_id>', methods=['GET'])
def api_get_guest(guest_id):
    """Get guest profile with all details"""
    guest = Guest.query.get_or_404(guest_id)
    memory_service = get_memory_service()
    profile = memory_service.get_guest_profile(guest_id) if memory_service else guest.to_dict()
    return jsonify(profile)


@chatbot_bp.route('/api/guests/<int:guest_id>', methods=['PATCH'])
def api_update_guest(guest_id):
    """Update guest basic info (name, email, phone)"""
    guest = Guest.query.get_or_404(guest_id)
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Check for email uniqueness if email is being updated
    if 'email' in data and data['email'] != guest.email:
        new_email = data['email'].strip() if data['email'] else None
        if new_email:
            existing = Guest.query.filter_by(email=new_email).first()
            if existing and existing.id != guest_id:
                return jsonify({'error': 'Email already in use'}), 409

    # Update allowed fields (partial update support)
    if 'name' in data:
        guest.name = data['name'].strip() if data['name'] else None
    if 'email' in data:
        guest.email = data['email'].strip() if data['email'] else None
    if 'phone' in data:
        guest.phone = data['phone'].strip() if data['phone'] else None
    if 'notes' in data:
        guest.notes = data['notes'].strip() if data['notes'] else None

    db.session.commit()
    return jsonify(guest.to_dict())


@chatbot_bp.route('/api/guests/<int:guest_id>/details', methods=['POST'])
def api_add_guest_detail(guest_id):
    """Manually add a guest detail"""
    guest = Guest.query.get_or_404(guest_id)
    data = request.get_json()

    required = ['detail_type', 'detail_key', 'detail_value']
    if not all(k in data for k in required):
        return jsonify({'error': 'Missing required fields'}), 400

    detail = GuestDetail(
        guest_id=guest_id,
        detail_type=data['detail_type'],
        detail_key=data['detail_key'],
        detail_value=data['detail_value'],
        confidence=1.0  # Manual entries have full confidence
    )
    db.session.add(detail)
    db.session.commit()

    return jsonify(detail.to_dict()), 201


@chatbot_bp.route('/api/guests/<int:guest_id>/details/<int:detail_id>', methods=['DELETE'])
def api_delete_guest_detail(guest_id, detail_id):
    """Delete a guest detail"""
    detail = GuestDetail.query.filter_by(id=detail_id, guest_id=guest_id).first_or_404()
    db.session.delete(detail)
    db.session.commit()
    return jsonify({'success': True})


@chatbot_bp.route('/api/guests/<int:guest_id>/details/<int:detail_id>', methods=['PATCH'])
def api_update_guest_detail(guest_id, detail_id):
    """Update a guest detail value"""
    detail = GuestDetail.query.filter_by(id=detail_id, guest_id=guest_id).first_or_404()
    data = request.get_json()

    if not data or 'detail_value' not in data:
        return jsonify({'error': 'detail_value is required'}), 400

    new_value = data['detail_value']
    if not new_value or not new_value.strip():
        return jsonify({'error': 'detail_value cannot be empty'}), 400

    detail.detail_value = new_value.strip()
    detail.confidence = 1.0  # Manual edits have full confidence

    db.session.commit()
    return jsonify(detail.to_dict())


@chatbot_bp.route('/api/guests/<int:guest_id>/merge-preview', methods=['POST'])
def api_merge_preview(guest_id):
    """Preview what would happen if two guests are merged (read-only)"""
    primary = Guest.query.get_or_404(guest_id)
    data = request.get_json()

    if not data or 'target_guest_id' not in data:
        return jsonify({'error': 'target_guest_id is required'}), 400

    target_id = data['target_guest_id']
    if target_id == guest_id:
        return jsonify({'error': 'Cannot merge guest with itself'}), 400

    target = Guest.query.get_or_404(target_id)

    # Count what would transfer
    conversations_count = target.conversations.count()
    details_count = target.details.count()

    # Count platform IDs that would transfer (only those the primary doesn't have)
    platform_ids = []
    for field in ['whatsapp_id', 'airbnb_id', 'booking_id', 'phone', 'email']:
        target_val = getattr(target, field)
        primary_val = getattr(primary, field)
        if target_val and not primary_val:
            platform_ids.append(field)

    return jsonify({
        'primary': {'id': primary.id, 'name': primary.name or primary.email or 'Unknown'},
        'target': {'id': target.id, 'name': target.name or target.email or 'Unknown'},
        'conversations': conversations_count,
        'details': details_count,
        'platform_ids': platform_ids
    })


@chatbot_bp.route('/api/guests/<int:guest_id>/merge', methods=['POST'])
def api_merge_guests(guest_id):
    """Merge target guest into primary guest"""
    primary = Guest.query.get_or_404(guest_id)
    data = request.get_json()

    if not data or 'target_guest_id' not in data:
        return jsonify({'error': 'target_guest_id is required'}), 400

    target_id = data['target_guest_id']
    if target_id == guest_id:
        return jsonify({'error': 'Cannot merge guest with itself'}), 400

    target = Guest.query.get_or_404(target_id)

    try:
        # 1. Reassign all conversations from target to primary
        conversations_moved = 0
        for conv in target.conversations.all():
            conv.guest_id = primary.id
            conversations_moved += 1

        # 2. Move GuestDetails, deduplicating by (type, key, value)
        existing_details = set()
        for d in primary.details.all():
            existing_details.add((d.detail_type, d.detail_key, d.detail_value))

        details_moved = 0
        for d in target.details.all():
            if (d.detail_type, d.detail_key, d.detail_value) not in existing_details:
                d.guest_id = primary.id
                details_moved += 1
            else:
                db.session.delete(d)

        # 3. Copy missing platform IDs
        for field in ['whatsapp_id', 'airbnb_id', 'booking_id', 'phone']:
            target_val = getattr(target, field)
            primary_val = getattr(primary, field)
            if target_val and not primary_val:
                setattr(primary, field, target_val)

        # Copy email only if primary has none (email is unique)
        if target.email and not primary.email:
            primary.email = target.email

        # 4. Update date ranges and stats
        if target.first_contact and (not primary.first_contact or target.first_contact < primary.first_contact):
            primary.first_contact = target.first_contact
        if target.last_contact and (not primary.last_contact or target.last_contact > primary.last_contact):
            primary.last_contact = target.last_contact
        primary.total_stays = (primary.total_stays or 0) + (target.total_stays or 0)

        # 5. Append notes
        if target.notes:
            if primary.notes:
                primary.notes = primary.notes + '\n\n--- Merged from ' + (target.name or target.email or 'Guest') + ' ---\n' + target.notes
            else:
                primary.notes = target.notes

        # 6. Flush reassignments before deleting target
        db.session.flush()

        # 7. Delete target guest (remaining orphan details cleaned up by cascade)
        db.session.delete(target)
        db.session.commit()

        return jsonify({
            'success': True,
            'conversations_moved': conversations_moved,
            'details_moved': details_moved
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@chatbot_bp.route('/api/settings', methods=['GET'])
@login_required
def api_get_settings():
    """Get all AI settings"""
    settings = AISettings.query.all()
    return jsonify({s.key: s.value for s in settings})


# Settings keys that only admins may change
ADMIN_ONLY_SETTINGS = {'ai_temperature', 'ai_max_tokens', 'ollama_model', 'reasoning_model'}


@chatbot_bp.route('/api/settings', methods=['PUT'])
@login_required
def api_update_settings():
    """Update AI settings"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Check if non-admin is trying to change admin-only settings
    if not current_user.is_admin:
        blocked = set(data.keys()) & ADMIN_ONLY_SETTINGS
        if blocked:
            return jsonify({'error': 'Admin rights required for these settings'}), 403

    for key, value in data.items():
        AISettings.set(key, str(value))

    return jsonify({'success': True})


@chatbot_bp.route('/api/ollama/models', methods=['GET'])
@admin_required
def api_get_ollama_models():
    """Get available Ollama models with resource info"""
    ai_service = get_ai_service()
    if not ai_service:
        return jsonify({'error': 'AI service not available'}), 503

    installed = ai_service.get_installed_models()
    current_model = ai_service.model

    # Well-known model recommendations with resource requirements
    model_info = {
        'mistral': {'vram': '~4 GB', 'ram': '~8 GB', 'quality': 'Good', 'speed': 'Fast'},
        'llama3.1:8b': {'vram': '~5 GB', 'ram': '~8 GB', 'quality': 'Very Good', 'speed': 'Fast'},
        'llama3.2:3b': {'vram': '~2 GB', 'ram': '~4 GB', 'quality': 'Basic', 'speed': 'Very Fast'},
        'gemma2:9b': {'vram': '~6 GB', 'ram': '~10 GB', 'quality': 'Very Good', 'speed': 'Medium'},
        'mistral-nemo': {'vram': '~7 GB', 'ram': '~12 GB', 'quality': 'Excellent', 'speed': 'Medium'},
        'qwen2.5:7b': {'vram': '~5 GB', 'ram': '~8 GB', 'quality': 'Very Good', 'speed': 'Fast'},
        'qwen2.5:14b': {'vram': '~9 GB', 'ram': '~14 GB', 'quality': 'Excellent', 'speed': 'Slow'},
        'llama3.1:70b': {'vram': '~40 GB', 'ram': '~48 GB', 'quality': 'Best', 'speed': 'Very Slow'},
        'phi3:mini': {'vram': '~2 GB', 'ram': '~4 GB', 'quality': 'Basic', 'speed': 'Very Fast'},
    }

    # Enrich installed models with resource info
    for m in installed:
        name = m['name']
        # Match by base name (e.g. "mistral:7b-instruct" matches "mistral")
        matched_info = None
        for key, info in model_info.items():
            if key in name:
                matched_info = info
                break
        if matched_info:
            m.update(matched_info)
        else:
            m.update({'vram': f'~{m["size_gb"]} GB', 'ram': f'~{round(m["size_gb"] * 1.5, 1)} GB', 'quality': 'Unknown', 'speed': 'Unknown'})

    # Suggested models that are not installed
    suggested = [
        {'name': 'llama3.1:8b-instruct', 'description': 'Best all-round for 8GB VRAM. Better than Mistral at following instructions.', **model_info['llama3.1:8b']},
        {'name': 'mistral-nemo:12b', 'description': 'Smarter but needs more VRAM. Great multilingual support.', **model_info['mistral-nemo']},
        {'name': 'qwen2.5:7b-instruct', 'description': 'Great at structured tasks and multilingual conversations.', **model_info['qwen2.5:7b']},
        {'name': 'llama3.2:3b-instruct', 'description': 'Lightweight option. Fastest but less accurate.', **model_info['llama3.2:3b']},
    ]

    # Filter out already installed
    installed_names = {m['name'] for m in installed}
    suggested = [s for s in suggested if not any(s['name'].split(':')[0] in inst for inst in installed_names)]

    reasoning_model = AISettings.get('reasoning_model') or ''

    return jsonify({
        'current_model': current_model,
        'reasoning_model': reasoning_model,
        'installed': installed,
        'suggested': suggested
    })


@chatbot_bp.route('/api/settings/model', methods=['PUT'])
@admin_required
def api_change_model():
    """Change the active AI model"""
    data = request.get_json()
    if not data or 'model' not in data:
        return jsonify({'error': 'Model name is required'}), 400

    model_name = data['model'].strip()
    ai_service = get_ai_service()
    if not ai_service:
        return jsonify({'error': 'AI service not available'}), 503

    # Verify model is installed
    installed = ai_service.get_installed_models()
    installed_names = [m['name'] for m in installed]
    if not any(model_name in name or name in model_name for name in installed_names):
        return jsonify({'error': f'Model "{model_name}" is not installed. Pull it first with: ollama pull {model_name}'}), 400

    # Don't re-switch to the same model
    if model_name == ai_service.model:
        return jsonify({'success': True, 'model': model_name})

    try:
        # Switch model without preload — just set the name.
        # The model will be loaded by Ollama on the next actual AI request,
        # which avoids the memory spike that crashes Flask during preload.
        result = ai_service.change_model(model_name, preload=False)

        if not result['success']:
            return jsonify({
                'error': f'Failed to switch to model "{model_name}": {result.get("error", "Unknown error")}',
                'current_model': ai_service.model
            }), 503

        # Persist to database
        AISettings.set('ollama_model', model_name, 'Active Ollama AI model')

        return jsonify({'success': True, 'model': model_name})

    except Exception as e:
        logger.error(f"Error changing model to {model_name}: {e}")
        return jsonify({
            'error': f'Error switching model: {str(e)}',
            'current_model': ai_service.model
        }), 500


@chatbot_bp.route('/api/settings/email-filter', methods=['GET'])
@admin_required
def api_get_email_filter():
    """Get email filter settings"""
    from .services.gmail_service import get_gmail_service
    gmail = get_gmail_service()
    return jsonify(gmail.get_filter_settings())


@chatbot_bp.route('/api/settings/email-filter', methods=['PUT'])
@admin_required
def api_update_email_filter():
    """Update email filter settings"""
    from .services.gmail_service import get_gmail_service
    import json

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    gmail = get_gmail_service()

    # Update filter settings
    gmail.update_filter_settings(
        allowed_domains=data.get('allowed_domains'),
        subject_keywords=data.get('subject_keywords'),
        filter_mode=data.get('filter_mode')
    )

    # Persist to database for future sessions
    AISettings.set('email_allowed_domains', json.dumps(gmail.allowed_domains))
    AISettings.set('email_subject_keywords', json.dumps(gmail.subject_keywords))
    AISettings.set('email_filter_mode', gmail.filter_mode)

    return jsonify({'success': True})


# ============================================================================
# NOTION KNOWLEDGE-BASE SYNC
# ============================================================================

@chatbot_bp.route('/api/settings/notion', methods=['GET'])
@admin_required
def api_get_notion_settings():
    """Return Notion sync config; the token VALUE is never returned."""
    from .services.notion_service import get_notion_config
    cfg = get_notion_config()
    return jsonify({
        'enabled': cfg['enabled'],
        'token_set': bool(cfg['token']),
        'root_page_id': cfg['root_page_id'],
        'block_keywords': ','.join(cfg['block_keywords']),
        'force_exclude_ids': ','.join(cfg['force_exclude_ids']),
        'force_include_ids': ','.join(cfg['force_include_ids']),
    })


@chatbot_bp.route('/api/settings/notion', methods=['PUT'])
@admin_required
def api_update_notion_settings():
    """Persist Notion sync settings. Token only overwritten if a value is sent."""
    data = request.get_json() or {}
    AISettings.set('notion_sync_enabled', str(data.get('notion_sync_enabled', 'false')))
    if data.get('notion_integration_token'):
        AISettings.set('notion_integration_token', data['notion_integration_token'])
    if data.get('notion_root_page_id') is not None:
        AISettings.set('notion_root_page_id', data['notion_root_page_id'])
    for key in ('notion_block_keywords', 'notion_force_exclude_ids', 'notion_force_include_ids'):
        if data.get(key) is not None:
            AISettings.set(key, data[key])
    return jsonify({'success': True})


@chatbot_bp.route('/api/notion/sync', methods=['POST'])
@admin_required
def api_notion_sync():
    """Run a Notion → knowledge-base sync and return the run stats."""
    from .services.notion_service import get_notion_service, get_notion_config
    cfg = get_notion_config()
    if not cfg['enabled'] or not cfg['token'] or not cfg['root_page_id']:
        return jsonify({'error': 'Notion sync is not enabled or not configured'}), 400
    service = get_notion_service()
    if service is None:
        return jsonify({'error': 'Notion service not initialized'}), 500
    try:
        stats = service.sync()
    except Exception:
        logger.exception("notion-sync route failed")
        return jsonify({'error': 'Sync failed; see server logs'}), 500
    return jsonify({'success': True, 'stats': stats})


# ============================================================================
# USER MANAGEMENT API
# ============================================================================

@chatbot_bp.route('/api/users/online', methods=['GET'])
@login_required
def api_get_online_users():
    """Get currently online users (active within last 5 minutes)."""
    from datetime import timedelta
    threshold = datetime.utcnow() - timedelta(minutes=5)
    online = User.query.filter(
        User.last_seen >= threshold
    ).order_by(User.display_name).all()
    return jsonify({'users': [
        {'id': u.id, 'display_name': u.display_name}
        for u in online
    ]})


@chatbot_bp.route('/api/users', methods=['GET'])
@admin_required
def api_get_users():
    """Get all users"""
    users = User.query.order_by(User.username).all()
    return jsonify({'users': [u.to_dict() for u in users]})


@chatbot_bp.route('/api/users', methods=['POST'])
@admin_required
def api_create_user():
    """Create a new user"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    username = (data.get('username') or '').strip()
    display_name = (data.get('display_name') or '').strip()
    password = data.get('password', '')

    if not username or not display_name or not password:
        return jsonify({'error': 'username, display_name, and password are required'}), 400

    if len(password) < 4:
        return jsonify({'error': 'Password must be at least 4 characters'}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Username already exists'}), 409

    user = User(username=username, display_name=display_name)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return jsonify(user.to_dict()), 201


@chatbot_bp.route('/api/users/<int:user_id>', methods=['DELETE'])
@admin_required
def api_delete_user(user_id):
    """Delete a user (cannot delete self or last user)"""
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        return jsonify({'error': 'Cannot delete yourself'}), 400

    if User.query.count() <= 1:
        return jsonify({'error': 'Cannot delete the last user'}), 400

    db.session.delete(user)
    db.session.commit()
    return jsonify({'success': True})


@chatbot_bp.route('/api/users/<int:user_id>/admin', methods=['PUT'])
@admin_required
def api_toggle_admin(user_id):
    """Toggle admin status for a user"""
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        return jsonify({'error': 'Cannot change your own admin status'}), 400

    user.is_admin = not user.is_admin
    db.session.commit()
    return jsonify({'success': True, 'is_admin': user.is_admin})


@chatbot_bp.route('/api/users/<int:user_id>/password', methods=['PUT'])
@admin_required
def api_reset_password(user_id):
    """Reset a user's password"""
    user = User.query.get_or_404(user_id)
    data = request.get_json()

    if not data or not data.get('password'):
        return jsonify({'error': 'password is required'}), 400

    password = data['password']
    if len(password) < 4:
        return jsonify({'error': 'Password must be at least 4 characters'}), 400

    user.set_password(password)
    db.session.commit()
    return jsonify({'success': True})


# ============================================================================
# CONVERSATION ASSIGNMENT API
# ============================================================================

@chatbot_bp.route('/api/conversations/<int:conversation_id>/assign', methods=['PATCH'])
@login_required
def api_assign_conversation(conversation_id):
    """Assign or unassign a conversation to a user"""
    conversation = Conversation.query.get_or_404(conversation_id)
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    user_id = data.get('user_id')
    if user_id is not None:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        conversation.user_id = user_id
    else:
        conversation.user_id = None

    db.session.commit()
    return jsonify({
        'success': True,
        'user_id': conversation.user_id,
        'assigned_user_name': conversation.assigned_user.display_name if conversation.assigned_user else None
    })


@chatbot_bp.route('/api/conversations/<int:conversation_id>/toggle-ai', methods=['POST'])
@login_required
def api_toggle_ai(conversation_id):
    """Toggle AI for a specific conversation"""
    conversation = Conversation.query.get_or_404(conversation_id)
    conversation.ai_enabled = not conversation.ai_enabled
    # Disable auto-respond when AI is turned off
    if not conversation.ai_enabled:
        conversation.auto_respond = False
    db.session.commit()
    return jsonify({'ai_enabled': conversation.ai_enabled, 'auto_respond': conversation.auto_respond})


@chatbot_bp.route('/api/conversations/<int:conversation_id>/toggle-auto-respond', methods=['POST'])
@login_required
def api_toggle_auto_respond(conversation_id):
    """Toggle automatic AI responses for a conversation"""
    conversation = Conversation.query.get_or_404(conversation_id)

    if not conversation.ai_enabled:
        return jsonify({'error': 'AI must be enabled first'}), 400

    conversation.auto_respond = not conversation.auto_respond
    db.session.commit()
    return jsonify({'auto_respond': conversation.auto_respond})


@chatbot_bp.route('/api/conversations/<int:conversation_id>/resolve', methods=['POST'])
@login_required
def api_resolve_escalation(conversation_id):
    """Resolve an escalated conversation. Does NOT re-enable auto-respond."""
    conversation = Conversation.query.get_or_404(conversation_id)

    # escalated_at is deliberately KEPT. Clearing it erased the only evidence a
    # chat was ever flagged, so "detection never fired" and "fired and someone
    # handled it" looked identical afterwards — untestable in production.
    # escalated_at set + escalated False now reads as "escalated, resolved".
    conversation.escalated = False
    db.session.commit()

    return jsonify({
        'success': True,
        'escalated': conversation.escalated,
        'auto_respond': conversation.auto_respond
    })


@chatbot_bp.route('/api/conversations/<int:conversation_id>/escalate', methods=['POST'])
@login_required
def api_escalate_conversation(conversation_id):
    """Manually flag a conversation as needing attention. Works regardless of
    whether UMI is answering — the team escalates by hand too."""
    conversation = Conversation.query.get_or_404(conversation_id)

    conversation.escalated = True
    conversation.escalated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'escalated': True,
        'escalated_at': conversation.escalated_at.isoformat()
    })


@lru_cache(maxsize=512)
def _translate_cached(text: str, target: str) -> str:
    """Translate a message body. See services/translate.py for why not deep-translator.

    Cached because the team re-opens the same chat repeatedly; the same message
    must not cost a round-trip every time. Failures raise and are never cached,
    so a transient Google hiccup doesn't poison the entry.
    ponytail: in-process LRU, not a DB column. Persist it only if translations
    ever need to be searchable.
    """
    from .services.translate import translate_text
    return translate_text(text, target)


@chatbot_bp.route('/api/translate', methods=['POST'])
@login_required
def api_translate_message():
    """Translate a single message body on demand (per-message button)."""
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    # Target follows the UI language; anything else falls back to German.
    target = 'en' if (data.get('target') or 'de').lower().startswith('en') else 'de'
    if not text:
        return jsonify({'error': 'no text'}), 400
    try:
        translated = _translate_cached(text, target)
    except Exception as e:
        logger.warning("Translation failed (%s chars, target=%s): %s", len(text), target, e)
        return jsonify({'error': 'translation_failed'}), 502
    translated = translated or text
    return jsonify({
        'translated': translated,
        'target': target,
        # Same text back = it was already in the target language.
        'was_translated': translated.strip().lower() != text.lower(),
    })


@chatbot_bp.route('/api/messages/<int:message_id>/approve', methods=['POST'])
@login_required
def api_approve_message(message_id):
    """Approve a pending AI draft and send it via platform."""
    message = Message.query.get_or_404(message_id)

    if message.approval_status != 'pending':
        return jsonify({'error': 'Message is not pending approval'}), 400

    conversation = Conversation.query.get(message.conversation_id)

    # Mark as approved
    message.approval_status = 'approved'
    message.approved_at = datetime.utcnow()
    db.session.commit()

    # Send via platform (same logic as api_generate_ai_response)
    email_sent = False
    smoobu_sent = False

    if conversation.platform == 'email' and conversation.guest:
        try:
            from .services.gmail_service import get_gmail_service
            gmail = get_gmail_service()
            if gmail and gmail.is_authenticated() and conversation.guest.email:
                latest_guest_msg = Message.query.filter_by(
                    conversation_id=conversation.id,
                    sender_type='guest'
                ).order_by(Message.sent_at.desc()).first()

                send_result = gmail.send_email(
                    to=conversation.guest.email,
                    subject=conversation.subject or 'Re: Your inquiry',
                    body=message.content,
                    thread_id=conversation.platform_id,
                    reply_to_message_id=latest_guest_msg.platform_message_id if latest_guest_msg and latest_guest_msg.platform_message_id else None
                )
                email_sent = bool(send_result)
        except Exception as e:
            logger.warning(f"Failed to send approved message via Gmail: {e}")

    elif conversation.platform == 'smoobu' and conversation.smoobu_reservation_id:
        try:
            from .services.smoobu_service import get_smoobu_service_for
            smoobu = get_smoobu_service_for(conversation)
            if smoobu and smoobu.is_configured():
                send_result = smoobu.send_message(conversation.smoobu_reservation_id, message.content)
                smoobu_sent = bool(send_result)
                # Set platform_message_id to prevent duplicate on next sync
                if smoobu_sent and isinstance(send_result, dict):
                    smoobu_msg_id = str(send_result.get('id') or send_result.get('message_id')
                                       or send_result.get('messageId') or '')
                    if smoobu_msg_id:
                        message.platform_message_id = (
                            f"smoobu-{conversation.smoobu_reservation_id}-{smoobu_msg_id}")
                        db.session.commit()
        except Exception as e:
            logger.warning(f"Failed to send approved message via Smoobu: {e}")

    return jsonify({
        'success': True,
        'email_sent': email_sent,
        'smoobu_sent': smoobu_sent,
        'message': message.to_dict()
    })


@chatbot_bp.route('/api/messages/<int:message_id>/reject', methods=['POST'])
@login_required
def api_reject_message(message_id):
    """Reject a pending AI draft."""
    message = Message.query.get_or_404(message_id)

    if message.approval_status != 'pending':
        return jsonify({'error': 'Message is not pending approval'}), 400

    message.approval_status = 'rejected'
    db.session.commit()

    return jsonify({'success': True})


@chatbot_bp.route('/api/conversations/<int:conv_id>/toggle-auto-approve', methods=['POST'])
def api_toggle_auto_approve(conv_id):
    """Toggle auto-approve for a conversation."""
    conversation = Conversation.query.get_or_404(conv_id)
    conversation.auto_approve = not conversation.auto_approve
    db.session.commit()

    return jsonify({'auto_approve': conversation.auto_approve})


@chatbot_bp.route('/api/settings/bulk-auto-approve', methods=['POST'])
@admin_required
def api_bulk_auto_approve():
    """Enable/disable auto-approve for all active conversations."""
    data = request.get_json()
    enabled = data.get('enabled', False)

    updated = Conversation.query.filter(
        Conversation.status != 'closed'
    ).update({Conversation.auto_approve: enabled})
    db.session.commit()

    return jsonify({'success': True, 'updated_count': updated})


@chatbot_bp.route('/api/conversations/<int:conversation_id>/property', methods=['PATCH'])
def api_set_conversation_property(conversation_id):
    """Assign or remove a property from a conversation"""
    conversation = Conversation.query.get_or_404(conversation_id)
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    property_id = data.get('property_id')

    if property_id is not None and property_id != '':
        property_id = int(property_id)
        prop = Property.query.get(property_id)
        if not prop:
            return jsonify({'error': 'Property not found'}), 404
        conversation.property_id = property_id
    else:
        conversation.property_id = None

    db.session.commit()
    return jsonify({
        'success': True,
        'property_id': conversation.property_id,
        'property_name': conversation.property.name if conversation.property else None
    })


# ============================================================================
# REPLY TEMPLATE API ROUTES
# ============================================================================

@chatbot_bp.route('/api/reply-templates', methods=['GET'])
def api_get_reply_templates():
    """Get all reply templates"""
    templates = ReplyTemplate.query.order_by(ReplyTemplate.category, ReplyTemplate.name).all()
    return jsonify({
        'templates': [t.to_dict() for t in templates]
    })


@chatbot_bp.route('/api/reply-templates', methods=['POST'])
def api_create_reply_template():
    """Create a new reply template"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    if not data.get('name') or not data.get('content'):
        return jsonify({'error': 'Name and content are required'}), 400

    template = ReplyTemplate(
        name=data['name'].strip(),
        content=data['content'].strip(),
        category=data.get('category', 'general').strip()
    )
    db.session.add(template)
    db.session.commit()

    return jsonify(template.to_dict()), 201


@chatbot_bp.route('/api/reply-templates/<int:template_id>', methods=['PUT'])
def api_update_reply_template(template_id):
    """Update a reply template"""
    template = ReplyTemplate.query.get_or_404(template_id)
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    if 'name' in data:
        template.name = data['name'].strip()
    if 'content' in data:
        template.content = data['content'].strip()
    if 'category' in data:
        template.category = data['category'].strip()

    db.session.commit()
    return jsonify(template.to_dict())


@chatbot_bp.route('/api/reply-templates/<int:template_id>', methods=['DELETE'])
def api_delete_reply_template(template_id):
    """Delete a reply template"""
    template = ReplyTemplate.query.get_or_404(template_id)
    db.session.delete(template)
    db.session.commit()
    return jsonify({'success': True})


# ============================================================================
# PROPERTY CRUD API ROUTES
# ============================================================================

@chatbot_bp.route('/api/properties', methods=['GET'])
def api_get_properties():
    """Get all properties"""
    properties = Property.query.order_by(Property.name).all()
    return jsonify({
        'properties': [p.to_dict() for p in properties]
    })


@chatbot_bp.route('/api/properties', methods=['POST'])
def api_create_property():
    """Create a new property"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    if not data.get('name'):
        return jsonify({'error': 'Name is required'}), 400

    prop = Property(
        name=data['name'].strip(),
        address=data.get('address', '').strip() or None,
        description=data.get('description', '').strip() or None,
        amenities=data.get('amenities', []),
        pet_friendly=data.get('pet_friendly', False),
        max_guests=data.get('max_guests', 4),
        bedrooms=data.get('bedrooms', 1),
        bathrooms=data.get('bathrooms', 1.0),
        price_per_night=data.get('price_per_night'),
        check_in_time=data.get('check_in_time', '3:00 PM'),
        check_out_time=data.get('check_out_time', '11:00 AM'),
        house_rules=data.get('house_rules', '').strip() or None
    )
    db.session.add(prop)
    db.session.commit()

    return jsonify(prop.to_dict()), 201


@chatbot_bp.route('/api/properties/<int:property_id>', methods=['PUT'])
def api_update_property(property_id):
    """Update a property"""
    prop = Property.query.get_or_404(property_id)
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    if 'name' in data:
        prop.name = data['name'].strip()
    if 'address' in data:
        prop.address = data['address'].strip() or None
    if 'description' in data:
        prop.description = data['description'].strip() or None
    if 'amenities' in data:
        prop.amenities = data['amenities']
    if 'pet_friendly' in data:
        prop.pet_friendly = data['pet_friendly']
    if 'max_guests' in data:
        prop.max_guests = data['max_guests']
    if 'bedrooms' in data:
        prop.bedrooms = data['bedrooms']
    if 'bathrooms' in data:
        prop.bathrooms = data['bathrooms']
    if 'price_per_night' in data:
        prop.price_per_night = data['price_per_night']
    if 'check_in_time' in data:
        prop.check_in_time = data['check_in_time']
    if 'check_out_time' in data:
        prop.check_out_time = data['check_out_time']
    if 'house_rules' in data:
        prop.house_rules = data['house_rules'].strip() or None

    db.session.commit()
    return jsonify(prop.to_dict())


@chatbot_bp.route('/api/properties/<int:property_id>', methods=['DELETE'])
def api_delete_property(property_id):
    """Delete a property"""
    prop = Property.query.get_or_404(property_id)
    db.session.delete(prop)
    db.session.commit()
    return jsonify({'success': True})


# ============================================================================
# DASHBOARD STATISTICS API
# ============================================================================

def _berlin_midnight_utc(days_ago=0):
    """00:00 Europe/Berlin `days_ago` days back, as naive UTC (how timestamps are
    stored). UTC midnight made "today" start at 02:00 local time."""
    from zoneinfo import ZoneInfo
    from datetime import timedelta
    local = (datetime.now(ZoneInfo('Europe/Berlin'))
             .replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_ago))
    return local.astimezone(timezone.utc).replace(tzinfo=None)


@chatbot_bp.route('/api/stats', methods=['GET'])
def api_get_stats():
    """Get dashboard statistics — combines counts into fewer queries"""
    from sqlalchemy import func

    today = _berlin_midnight_utc()

    # Single query for conversation counts
    conv_stats = db.session.query(
        func.count(Conversation.id).label('total'),
        func.sum(sa_case(
            (Conversation.is_read == False, 1), else_=0
        )).label('unread'),
        func.count(func.distinct(sa_case(
            (Conversation.status == 'active', Conversation.guest_id), else_=None
        ))).label('active_guests'),
        # Open escalations. Counted here so the inbox filter can carry a live
        # badge — escalations had no owner and no visible count, so the oldest
        # sat unanswered for months.
        func.sum(sa_case(
            ((Conversation.escalated == True) & (Conversation.status != 'closed'), 1),
            else_=0
        )).label('escalated')
    # Playtest chats are excluded from /api/conversations, so counting them here
    # produced numbers the inbox could never show — a badge reading 1 over an
    # empty list. Every stat must describe the same set of conversations the
    # list does.
    ).filter(Conversation.platform != 'playtest').first()

    # Guest messages only — team replies would inflate "how busy was today".
    messages_today = Message.query.filter(
        Message.sent_at >= today,
        Message.sender_type == 'guest',
        Message.conversation_id.in_(
            db.session.query(Conversation.id).filter(Conversation.platform != 'playtest')
        )
    ).count()
    total_guests = Guest.query.count()
    # Same set /api/conversations?status=pending_approval returns, so the tile
    # count matches the list it opens.
    pending_approval = db.session.query(func.count(func.distinct(Message.conversation_id))).filter(
        Message.approval_status == 'pending',
        Message.conversation_id.in_(
            db.session.query(Conversation.id).filter(Conversation.platform != 'playtest')
        )
    ).scalar()

    return jsonify({
        'pending_approval_count': int(pending_approval or 0),
        'total_conversations': conv_stats.total,
        'unread_count': int(conv_stats.unread or 0),
        'messages_today': messages_today,
        'active_guests': int(conv_stats.active_guests or 0),
        'escalated_count': int(conv_stats.escalated or 0),
        'total_guests': total_guests
    })


@chatbot_bp.route('/api/stats/detailed', methods=['GET'])
def api_get_detailed_stats():
    """Team-Leistung.

    Team-wide numbers include replies written in Smoobu: ~98% of the team's
    replies never pass through UMI, and Smoobu doesn't say who wrote them. So
    per-person numbers are limited to what UMI itself sees — online time and
    replies sent from UMI.
    """
    from sqlalchemy import func
    from datetime import timedelta
    from statistics import median
    from zoneinfo import ZoneInfo

    berlin = ZoneInfo('Europe/Berlin')
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    today_local = datetime.now(berlin).date()

    # One pass over the last 7 calendar days feeds the chart, the reply time and
    # the waiting count.
    rows = db.session.query(Message.conversation_id, Message.sender_type, Message.sent_at).filter(
        Message.sent_at >= _berlin_midnight_utc(6),
        Message.conversation_id.in_(
            db.session.query(Conversation.id).filter(Conversation.platform != 'playtest')),
    ).order_by(Message.sent_at).all()

    daily = {(today_local - timedelta(days=i)).isoformat(): {'guest': 0, 'team': 0}
             for i in range(6, -1, -1)}
    reply_minutes = []
    waiting = {}  # conversation -> its oldest guest message nobody has answered yet
    for conv_id, sender, sent_at in rows:
        if sender not in ('guest', 'owner', 'ai'):
            continue
        side = 'guest' if sender == 'guest' else 'team'
        day = sent_at.replace(tzinfo=timezone.utc).astimezone(berlin).date().isoformat()
        if day in daily:
            daily[day][side] += 1
        if side == 'guest':
            waiting.setdefault(conv_id, sent_at)
        elif conv_id in waiting:
            minutes = (sent_at - waiting.pop(conv_id)).total_seconds() / 60
            # ponytail: a message >24h after the guest's is treated as new outreach
            # (guest "Danke!", days later check-in info), not a reply — ~1 in 4 on
            # live data, and it dragged the median from ~4.5h to ~12h. Upgrade path:
            # ignore guest messages that need no answer, if that ever gets detected.
            if minutes <= 24 * 60:
                reply_minutes.append(minutes)

    escalated = db.session.query(func.count(Conversation.id)).filter(
        Conversation.platform != 'playtest',
        Conversation.escalated == True,
        Conversation.status != 'closed',
    ).scalar()

    # --- Per person ---
    umi_sent = dict(db.session.query(Message.user_id, func.count(Message.id)).filter(
        Message.user_id.isnot(None),
        Message.sent_via_app == True,
        Message.sent_at >= week_ago,
    ).group_by(Message.user_id).all())

    today_start = _berlin_midnight_utc()
    online_week, online_today = {}, {}
    for s in UserSession.query.filter(UserSession.started_at >= week_ago).all():
        mins = (s.last_active_at - s.started_at).total_seconds() / 60.0
        online_week[s.user_id] = online_week.get(s.user_id, 0) + mins
        if s.started_at >= today_start:
            online_today[s.user_id] = online_today.get(s.user_id, 0) + mins

    online_cutoff = now - timedelta(minutes=5)  # same rule as /api/users/online
    team = [{
        'user_id': u.id,
        'display_name': u.display_name,
        'online': bool(u.last_seen and u.last_seen >= online_cutoff),
        'last_seen': u.last_seen.isoformat() if u.last_seen else None,
        'online_minutes_today': round(online_today.get(u.id, 0)),
        'online_minutes_week': round(online_week.get(u.id, 0)),
        'umi_messages_week': umi_sent.get(u.id, 0),
    } for u in User.query.all()]
    team.sort(key=lambda u: u['last_seen'] or '', reverse=True)

    return jsonify({
        'today': daily[today_local.isoformat()],
        'reply_minutes_median': round(median(reply_minutes)) if reply_minutes else None,
        'waiting_count': len(waiting),
        'escalated_count': int(escalated or 0),
        'daily': [{'date': d, **counts} for d, counts in daily.items()],
        'team': team,
    })


# ============================================================================
# WEB PUSH NOTIFICATION ROUTES
# ============================================================================

@chatbot_bp.route('/sw.js')
def service_worker():
    """Serve the service worker from /chatbot/sw.js so its scope covers /chatbot/"""
    import os
    from flask import send_file, make_response
    sw_path = os.path.join(chatbot_bp.static_folder, 'sw.js')
    response = make_response(send_file(sw_path, mimetype='application/javascript'))
    response.headers['Service-Worker-Allowed'] = '/chatbot/'
    response.headers['Cache-Control'] = 'no-cache'
    return response


@chatbot_bp.route('/manifest.webmanifest')
def manifest():
    """Web app manifest — makes the messenger installable as 'UMI-Chat'."""
    from flask import make_response, url_for
    # url_for, not hardcoded — the blueprint serves static at /chatbot/chatbot/static
    # (url_prefix + static_url_path both carry /chatbot). Hardcoding 404s the icons,
    # which silently makes the PWA non-installable.
    def icon(name, size, purpose):
        return {"src": url_for('chatbot.static', filename='img/pwa/' + name),
                "sizes": size, "type": "image/png", "purpose": purpose}
    data = {
        "name": "UMI-Chat",
        "short_name": "UMI-Chat",
        "start_url": "/chatbot/",
        "scope": "/chatbot/",
        "display": "standalone",
        "orientation": "portrait",
        "theme_color": "#7B2332",
        "background_color": "#7B2332",
        "icons": [
            icon("icon-192.png", "192x192", "any"),
            icon("icon-512.png", "512x512", "any"),
            icon("icon-maskable-192.png", "192x192", "maskable"),
            icon("icon-maskable-512.png", "512x512", "maskable"),
        ],
    }
    resp = make_response(jsonify(data))
    resp.headers['Content-Type'] = 'application/manifest+json'
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


@chatbot_bp.route('/api/push/vapid-key', methods=['GET'])
def api_push_vapid_key():
    """Return the VAPID public key for the frontend"""
    from .services.push_service import get_push_service
    push = get_push_service()
    if not push:
        return jsonify({'error': 'Push service not available'}), 503
    return jsonify({'publicKey': push.get_public_key()})


@chatbot_bp.route('/api/push/subscribe', methods=['POST'])
@login_required
def api_push_subscribe():
    """Store a push subscription (upsert by endpoint)"""
    from .models import PushSubscription
    data = request.get_json()
    if not data or 'endpoint' not in data or 'keys' not in data:
        return jsonify({'error': 'Invalid subscription data'}), 400

    endpoint = data['endpoint']
    p256dh = data['keys'].get('p256dh', '')
    auth = data['keys'].get('auth', '')
    user_agent = data.get('user_agent', request.headers.get('User-Agent', '')[:500])

    if not p256dh or not auth:
        return jsonify({'error': 'Missing keys'}), 400

    # Upsert: update existing or create new
    existing = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if existing:
        existing.user_id = current_user.id
        existing.p256dh = p256dh
        existing.auth = auth
        existing.user_agent = user_agent
    else:
        sub = PushSubscription(
            user_id=current_user.id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            user_agent=user_agent
        )
        db.session.add(sub)

    db.session.commit()
    return jsonify({'success': True})


@chatbot_bp.route('/api/push/unsubscribe', methods=['POST'])
@login_required
def api_push_unsubscribe():
    """Remove a push subscription"""
    from .models import PushSubscription
    data = request.get_json()
    if not data or 'endpoint' not in data:
        return jsonify({'error': 'endpoint is required'}), 400

    sub = PushSubscription.query.filter_by(
        endpoint=data['endpoint'],
        user_id=current_user.id
    ).first()
    if sub:
        db.session.delete(sub)
        db.session.commit()

    return jsonify({'success': True})


@chatbot_bp.route('/api/push/test', methods=['POST'])
@login_required
def api_push_test():
    """Send a test push notification with detailed diagnostics per subscription"""
    import json as _json
    from pywebpush import webpush, WebPushException
    from .services.push_service import get_push_service
    from .models import PushSubscription

    push = get_push_service()
    if not push:
        return jsonify({'error': 'Push service not initialized'}), 503

    push._ensure_keys()

    subs = PushSubscription.query.filter_by(user_id=current_user.id).all()
    if not subs:
        return jsonify({'error': 'No push subscriptions found. Enable push notifications first.', 'subscriptions': 0}), 400

    payload = _json.dumps({
        'title': 'ChatBotAI Test',
        'body': 'Push notifications are working!',
        'url': '/chatbot/',
        'tag': 'test-push'
    })

    results = []
    for sub in subs:
        endpoint_short = sub.endpoint[:80] + '...' if len(sub.endpoint) > 80 else sub.endpoint
        try:
            response = webpush(
                subscription_info={
                    'endpoint': sub.endpoint,
                    'keys': {
                        'p256dh': sub.p256dh,
                        'auth': sub.auth
                    }
                },
                data=payload,
                vapid_private_key=push._private_key,
                vapid_claims={'sub': push.claim_email}
            )
            results.append({
                'endpoint': endpoint_short,
                'status': response.status_code if response else 'no_response',
                'ok': True
            })
        except WebPushException as e:
            status_code = e.response.status_code if e.response is not None else None
            body = ''
            if e.response is not None:
                try:
                    body = e.response.text[:200]
                except Exception:
                    body = str(e.response.status_code)
            # Clean up expired subscriptions
            if status_code in (404, 410):
                db.session.delete(sub)
                db.session.commit()
            results.append({
                'endpoint': endpoint_short,
                'status': status_code,
                'error': str(e)[:200],
                'response_body': body,
                'ok': False
            })
        except Exception as e:
            results.append({
                'endpoint': endpoint_short,
                'status': None,
                'error': f'{type(e).__name__}: {e}',
                'ok': False
            })

    any_ok = any(r['ok'] for r in results)
    return jsonify({
        'success': any_ok,
        'subscriptions': len(subs),
        'results': results
    })


@chatbot_bp.route('/api/push/reset', methods=['POST'])
@login_required
def api_push_reset():
    """Delete all push subscriptions for the current user"""
    from .models import PushSubscription
    deleted = PushSubscription.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({'success': True, 'deleted': deleted})


@chatbot_bp.route('/api/push/status', methods=['GET'])
def api_push_status():
    """Return push notification status for debug dashboard"""
    from .services.push_service import get_push_service
    from .models import PushSubscription

    push = get_push_service()
    if not push:
        return jsonify({'initialized': False, 'subscriptions': []})

    subs = PushSubscription.query.filter_by(user_id=current_user.id).all()
    return jsonify({
        'initialized': True,
        'has_vapid_keys': bool(push._private_key or push._public_key),
        'subscriptions': [{
            'id': s.id,
            'endpoint_domain': s.endpoint.split('/')[2] if '/' in s.endpoint else 'unknown',
            'user_agent': (s.user_agent or '')[:80],
            'created_at': s.created_at.isoformat() if s.created_at else None,
        } for s in subs]
    })


# ============================================================================
# WEBHOOK ROUTES (Platform Integrations)
# ============================================================================

@chatbot_bp.route('/webhook/gmail', methods=['POST'])
def webhook_gmail():
    """Webhook endpoint for Gmail push notifications"""
    # TODO: Implement Gmail webhook handling
    return jsonify({'status': 'received'}), 200


@chatbot_bp.route('/webhook/whatsapp', methods=['POST'])
def webhook_whatsapp():
    """Inbound message from the local Baileys bridge (whatsapp_bridge/).

    Endpoint name starts with 'webhook_' so the before_request hook in
    routes.py:114 skips login_required — the sidecar has no session. It is
    reachable without a login, so the shared secret is the only gate and is
    mandatory: an unset WHATSAPP_BRIDGE_SECRET rejects everything rather than
    leaving an open message-injection endpoint on a public tunnel.
    """
    from .services.message_router import get_message_router

    expected = os.environ.get('WHATSAPP_BRIDGE_SECRET', '')
    if not expected or not hmac.compare_digest(request.headers.get('X-Bridge-Secret', ''), expected):
        return jsonify({'error': 'forbidden'}), 403

    data = request.get_json(silent=True) or {}
    jid = (data.get('jid') or '').strip()
    text = (data.get('text') or '').strip()
    if not jid or not text:
        return jsonify({'error': 'jid and text are required'}), 400

    sent_at = None
    if data.get('timestamp'):
        try:
            # Naive UTC like every stored timestamp — plain fromtimestamp() gave
            # server-local time, 2h ahead, which floated WhatsApp chats up the inbox.
            sent_at = datetime.fromtimestamp(int(data['timestamp']), timezone.utc).replace(tzinfo=None)
        except (TypeError, ValueError, OSError):
            sent_at = None

    msg_id = f"whatsapp-{data.get('message_id')}" if data.get('message_id') else None
    router = get_message_router()
    try:
        if data.get('from_me'):
            # Typed by the team on the phone. Stored under the same
            # `whatsapp-<id>` a UMI send stores, so a stray echo dedups.
            result = router.process_external_owner_message(
                platform='whatsapp',
                platform_conversation_id=f"whatsapp-{jid}",
                platform_user_id=jid,
                sender_phone=data.get('phone') or None,
                content=text,
                subject='WhatsApp',
                platform_message_id=msg_id,
                sent_at=sent_at,
            )
        else:
            result = router.process_incoming_message(
                platform='whatsapp',
                platform_conversation_id=f"whatsapp-{jid}",
                # No fallback to the jid's user part: a `@lid` jid is an opaque id,
                # not a phone number, and storing it as one creates a junk guest and
                # breaks matching against the Smoobu guest with the same number.
                sender_phone=data.get('phone') or None,
                sender_name=data.get('name') or None,
                platform_user_id=jid,
                message_content=text,
                subject='WhatsApp',
                platform_message_id=msg_id,
                # UMI never answers WhatsApp unattended: this channel exists to put
                # the chat in the inbox, a human writes the reply.
                auto_respond=False,
                sent_at=sent_at,
            )
    except Exception:
        logger.exception("WhatsApp webhook failed for %s", jid)
        # 200 anyway: the bridge must not retry-storm, and the message is lost
        # only from UMI — it is still on the phone.
        return jsonify({'status': 'error'}), 200

    return jsonify({'status': 'received', 'conversation_id': result.get('conversation_id')}), 200


@chatbot_bp.route('/api/whatsapp/status', methods=['GET'])
@login_required
def api_whatsapp_status():
    """Is the WhatsApp bridge linked? Drives the composer's send path.

    The pairing QR is a login credential (whoever scans it links a device), so it
    never leaves through this non-admin route — admins get it from /pairing.
    """
    from .services.whatsapp_service import get_whatsapp_service
    status = get_whatsapp_service().get_status()
    status.pop('qr', None)
    return jsonify(status)


@chatbot_bp.route('/api/whatsapp/pairing', methods=['GET'])
@admin_required
def api_whatsapp_pairing():
    """Bridge status plus the pairing QR (a data: URL) for the Settings page."""
    from .services.whatsapp_service import get_whatsapp_service
    return jsonify(get_whatsapp_service().get_status())


@chatbot_bp.route('/api/whatsapp/start', methods=['POST'])
@admin_required
def api_whatsapp_start():
    """Start the bridge sidecar from Settings when it isn't answering."""
    from .services.whatsapp_service import get_whatsapp_service
    whatsapp = get_whatsapp_service()
    if not whatsapp.is_configured():
        return jsonify({'error': 'WhatsApp bridge not configured'}), 400
    if whatsapp.is_running():
        return jsonify({'started': False, 'already_running': True})
    try:
        pid = whatsapp.start_bridge()
    except OSError as e:
        logger.exception("Starting the WhatsApp bridge failed")
        return jsonify({'error': f'Bridge konnte nicht gestartet werden: {e}'}), 500
    if pid is None:
        return jsonify({'started': False, 'starting': True})
    return jsonify({'started': True, 'pid': pid})


@chatbot_bp.route('/api/whatsapp/reply/<int:conversation_id>', methods=['POST'])
@login_required
def api_whatsapp_reply(conversation_id):
    """Send a reply through the WhatsApp bridge.

    Mirrors api_smoobu_reply: same per-conversation lock and duplicate guard,
    and the message is stored only after the send succeeds.
    """
    from .services.whatsapp_service import get_whatsapp_service

    conversation = Conversation.query.get_or_404(conversation_id)
    if conversation.platform != 'whatsapp':
        return jsonify({'error': 'Not a WhatsApp conversation'}), 400

    jid = (conversation.guest.whatsapp_id if conversation.guest else None) or ''
    if not jid:
        return jsonify({'error': 'No WhatsApp ID on this guest'}), 400

    data = request.get_json() or {}
    content = (data.get('message') or '').strip()
    if not content:
        return jsonify({'error': 'Message is required'}), 400

    whatsapp = get_whatsapp_service()
    if not whatsapp.is_configured():
        return jsonify({'error': 'WhatsApp bridge not configured'}), 400

    with _conversation_send_lock(conversation.id):
        if _recent_duplicate_owner_reply(conversation.id, content):
            logger.info("Duplicate WhatsApp reply blocked for conversation %s", conversation.id)
            return jsonify({'success': True, 'duplicate_skipped': True, 'content': content}), 200

        send_result = whatsapp.send_message(jid, content)
        if not send_result:
            return jsonify({'error': 'Failed to send message via WhatsApp'}), 502

        msg_id = send_result.get('message_id')
        owner_result = get_message_router().process_owner_message(
            conversation_id=conversation.id, content=content, extract_memory=True,
            platform_message_id=f"whatsapp-{msg_id}" if msg_id else None,
            sent_via_app=True)

    if current_user.is_authenticated and conversation.user_id is None:
        conversation.user_id = current_user.id
        db.session.commit()

    original_ai_content = data.get('original_ai_content')
    if original_ai_content:
        _store_correction_if_needed(original_ai_content, content, conversation)

    return jsonify({'success': True, 'message_id': owner_result.get('message_id'),
                    'content': content})


@chatbot_bp.route('/webhook/airbnb', methods=['POST'])
def webhook_airbnb():
    """Webhook endpoint for Airbnb messages"""
    # TODO: Implement Airbnb webhook handling
    return jsonify({'status': 'received'}), 200


@chatbot_bp.route('/webhook/booking', methods=['POST'])
def webhook_booking():
    """Webhook endpoint for Booking.com messages"""
    # TODO: Implement Booking.com webhook handling
    return jsonify({'status': 'received'}), 200


# ============================================================================
# HEALTH & UTILITY ROUTES
# ============================================================================

@chatbot_bp.route('/health')
def health_check():
    """Health check endpoint"""
    ai_service = get_ai_service()
    ai_status = ai_service.test_connection() if ai_service else False

    return jsonify({
        'status': 'healthy',
        'database': True,
        'ai_service': ai_status,
        'timestamp': datetime.utcnow().isoformat()
    })


@chatbot_bp.route('/api/keepalive')
def api_keepalive():
    """Lightweight endpoint hit by the keepalive daemon every few minutes.

    Touches the DB so SQLite pages stay in the OS file cache; does NOT call
    Ollama or any external service. Safe to hit from monitoring tools too.
    """
    # Tiny DB query — warms the most-used table without doing real work
    try:
        db.session.execute(db.text('SELECT 1 FROM user LIMIT 1'))
    except Exception:
        pass
    return jsonify({'status': 'ok', 'ts': datetime.utcnow().isoformat() + 'Z'}), 200


@chatbot_bp.route('/api/test-ai', methods=['POST'])
def api_test_ai():
    """Test AI with a sample message"""
    ai_service = get_ai_service()
    if not ai_service:
        return jsonify({'error': 'AI service not available'}), 503

    data = request.get_json()
    message = data.get('message', 'Hello, I am interested in booking your property.')

    # Test extraction
    extracted = ai_service.extract_guest_info(message)

    return jsonify({
        'original_message': message,
        'extracted_info': extracted,
        'ai_status': ai_service.test_connection()
    })


# ============================================================================
# DEBUG ROUTES
# ============================================================================

@chatbot_bp.route('/api/debug/ai-prompt/<int:conversation_id>')
def api_debug_ai_prompt(conversation_id):
    """Debug: show exactly what the AI receives for a conversation"""
    conversation = Conversation.query.get_or_404(conversation_id)
    messages = conversation.messages.order_by(Message.sent_at.asc()).all()

    # Show raw DB content
    db_messages = []
    for m in messages:
        db_messages.append({
            'id': m.id,
            'sender_type': m.sender_type,
            'content': m.content,
            'content_length': len(m.content) if m.content else 0,
            'platform_message_id': m.platform_message_id,
            'sent_at': m.sent_at.isoformat() if m.sent_at else None,
        })

    # Build the actual prompt that would go to the AI
    ai_service = get_ai_service()
    memory_service = get_memory_service()
    profile = memory_service.get_guest_profile(conversation.guest_id) if memory_service else {}
    property_info = conversation.property.to_dict() if conversation.property else None

    # Query latest guest message directly (bypass relationship default ordering)
    latest_guest_message, question_text = pending_guest_question(conversation)

    # Read AI settings for debug display
    tone = AISettings.get('ai_response_tone', 'friendly_professional')
    host_instructions = AISettings.get('host_instructions', '')
    max_history = int(AISettings.get('max_conversation_history', '10'))

    chat_messages = []
    if ai_service and latest_guest_message:
        chat_messages = ai_service._build_chat_messages(
            guest_profile=profile,
            conversation_history=[m.to_dict() for m in messages],
            latest_message=question_text,
            property_info=property_info,
            tone=tone,
            host_instructions=host_instructions,
            conversation_subject=conversation.subject,
            max_history=max_history
        )

    return jsonify({
        'conversation_id': conversation_id,
        'platform': conversation.platform,
        'subject': conversation.subject,
        'guest_profile': profile,
        'db_messages': db_messages,
        'ai_chat_messages': chat_messages,
        'total_prompt_chars': sum(len(m['content']) for m in chat_messages),
        'settings': {
            'tone': tone,
            'host_instructions': host_instructions,
            'max_history': max_history,
        }
    })


# ============================================================================
# TEST & DEMO ROUTES
# ============================================================================

@chatbot_bp.route('/api/test/create-conversation', methods=['POST'])
def api_create_test_conversation():
    """
    Create a test conversation with sample data.
    Useful for testing without real platform integrations.
    """
    from .services.message_router import get_message_router

    data = request.get_json() or {}

    router = get_message_router()
    result = router.create_test_conversation(
        guest_name=data.get('guest_name', 'Test Guest'),
        guest_email=data.get('guest_email', f'guest_{datetime.utcnow().strftime("%H%M%S")}@example.com'),
        platform=data.get('platform', 'email'),
        subject=data.get('subject', 'Booking Inquiry'),
        initial_message=data.get('message', 'Hello! I am interested in booking your property for next weekend.')
    )

    return jsonify(result), 201 if result['success'] else 500


@chatbot_bp.route('/api/test/simulate-message', methods=['POST'])
def api_simulate_incoming_message():
    """
    Simulate an incoming message from a guest.
    Used for testing the full message flow.
    """
    from .services.message_router import get_message_router

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    required = ['conversation_id', 'message']
    if not all(k in data for k in required):
        return jsonify({'error': 'Missing required fields: conversation_id, message'}), 400

    # Get conversation to find the platform info
    conversation = Conversation.query.get(data['conversation_id'])
    if not conversation:
        return jsonify({'error': 'Conversation not found'}), 404

    guest = conversation.guest

    router = get_message_router()
    result = router.process_incoming_message(
        platform=conversation.platform,
        platform_conversation_id=conversation.platform_id,
        sender_email=guest.email,
        sender_phone=guest.phone,
        sender_name=guest.name,
        message_content=data['message'],
        auto_respond=data.get('auto_respond', True)
    )

    return jsonify(result), 200 if result['success'] else 500


@chatbot_bp.route('/api/test/bulk-create', methods=['POST'])
def api_bulk_create_test_data():
    """
    Create multiple test conversations with sample data.
    Great for populating the inbox for UI testing.
    """
    from .services.message_router import get_message_router
    import uuid

    # Sample test data
    test_scenarios = [
        {
            'guest_name': 'Maria Schmidt',
            'guest_email': 'maria.schmidt@example.com',
            'platform': 'email',
            'subject': 'Familienurlaub im August',
            'message': 'Hallo! Wir planen einen Familienurlaub vom 15. bis 22. August. Wir sind 4 Personen: mein Mann, ich und unsere zwei Kinder (8 und 12 Jahre). Ist die Wohnung in diesem Zeitraum verfügbar?'
        },
        {
            'guest_name': 'Thomas Weber',
            'guest_email': 'thomas.weber@example.com',
            'platform': 'whatsapp',
            'subject': 'Wanderurlaub',
            'message': 'Hi! I am looking for accommodation for a hiking trip. We are coming with our dog Max (a Golden Retriever). Is your property pet-friendly? We would need it from March 10-15.'
        },
        {
            'guest_name': 'Sophie Martin',
            'guest_email': 'sophie.m@example.com',
            'platform': 'airbnb',
            'subject': 'Romantic Weekend',
            'message': 'Hello! My partner and I are planning a romantic weekend getaway. Do you have any special amenities? Also, I have a severe peanut allergy - is the kitchen peanut-free?'
        },
        {
            'guest_name': 'James Wilson',
            'guest_email': 'j.wilson@example.com',
            'platform': 'booking',
            'subject': 'Business Trip',
            'message': 'Good day, I need accommodation for a business trip next month. Is there reliable WiFi for video conferences? I will be alone and need a quiet workspace.'
        },
        {
            'guest_name': 'Anna Kowalski',
            'guest_email': 'anna.k@example.com',
            'platform': 'email',
            'subject': 'Accessibility Question',
            'message': 'Hello, my mother uses a wheelchair. Is your property wheelchair accessible? We are looking for accommodation for 5 nights in April. Thank you!'
        }
    ]

    router = get_message_router()
    results = []

    for scenario in test_scenarios:
        result = router.create_test_conversation(
            guest_name=scenario['guest_name'],
            guest_email=scenario['guest_email'],
            platform=scenario['platform'],
            subject=scenario['subject'],
            initial_message=scenario['message']
        )
        results.append({
            'guest': scenario['guest_name'],
            'success': result['success'],
            'conversation_id': result.get('conversation_id'),
            'ai_responded': result.get('ai_response') is not None
        })

    return jsonify({
        'created': len([r for r in results if r['success']]),
        'total': len(test_scenarios),
        'results': results
    })


@chatbot_bp.route('/api/conversations/<int:conversation_id>/status', methods=['PUT'])
def api_update_conversation_status(conversation_id):
    """Update conversation status (active, closed, pending_owner)"""
    conversation = Conversation.query.get_or_404(conversation_id)
    data = request.get_json()

    if 'status' not in data:
        return jsonify({'error': 'Status is required'}), 400

    valid_statuses = ['active', 'closed', 'pending_owner']
    if data['status'] not in valid_statuses:
        return jsonify({'error': f'Invalid status. Must be one of: {valid_statuses}'}), 400

    conversation.status = data['status']

    # Auto-reject pending drafts when closing a conversation
    if data['status'] == 'closed':
        pending_messages = Message.query.filter_by(
            conversation_id=conversation_id,
            approval_status='pending'
        ).all()
        for msg in pending_messages:
            msg.approval_status = 'rejected'

    db.session.commit()

    return jsonify({'success': True, 'status': conversation.status})


@chatbot_bp.route('/api/guests', methods=['GET'])
def api_get_all_guests():
    """Get all guests with basic info"""
    guests = Guest.query.order_by(Guest.last_contact.desc()).all()
    return jsonify({
        'guests': [g.to_dict() for g in guests],
        'total': len(guests)
    })


# ============================================================================
# GMAIL INTEGRATION ROUTES
# ============================================================================

def _get_gmail_callback_url():
    """Build the Gmail OAuth callback URL.
    Uses GMAIL_REDIRECT_URI config if set, otherwise builds from request.
    Replaces private/LAN IPs with localhost (Google rejects private IPs for OAuth).
    """
    configured = current_app.config.get('GMAIL_REDIRECT_URI')
    if configured:
        return configured

    import ipaddress
    from urllib.parse import urlparse, urlunparse
    host_url = request.host_url.rstrip('/')
    parsed = urlparse(host_url)
    hostname = parsed.hostname

    # Replace private IPs with localhost (Google OAuth rejects private IPs)
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private and not ip.is_loopback:
            # Replace e.g. 192.168.178.36 with localhost, keep scheme/port
            netloc = 'localhost'
            if parsed.port and parsed.port not in (80, 443):
                netloc = f'localhost:{parsed.port}'
            host_url = urlunparse(parsed._replace(netloc=netloc))
    except ValueError:
        pass  # hostname is not an IP (it's a domain name), that's fine

    return host_url + '/chatbot/gmail/callback'


@chatbot_bp.route('/gmail/status')
def gmail_status():
    """Get Gmail connection status"""
    from .services.gmail_service import get_gmail_service
    gmail = get_gmail_service()
    return jsonify(gmail.get_status())


@chatbot_bp.route('/gmail/authorize')
@admin_required
def gmail_authorize():
    """Start Gmail OAuth flow"""
    from .services.gmail_service import get_gmail_service

    gmail = get_gmail_service()

    if not gmail.is_configured():
        return jsonify({
            'error': 'Gmail not configured',
            'message': 'Please add credentials.json file to ChatBotAI folder. '
                       'Download it from Google Cloud Console after creating OAuth credentials.'
        }), 400

    callback_url = _get_gmail_callback_url()

    try:
        auth_url, state, code_verifier = gmail.get_authorization_url(callback_url)
        from flask import session
        session['gmail_callback_url'] = callback_url
        session['gmail_code_verifier'] = code_verifier

        return jsonify({
            'authorization_url': auth_url,
            'message': 'Redirect user to authorization_url to complete OAuth'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@chatbot_bp.route('/gmail/authorize/redirect')
def gmail_authorize_redirect():
    """Redirect to Google OAuth (for browser-based flow)"""
    from .services.gmail_service import get_gmail_service

    gmail = get_gmail_service()

    if not gmail.is_configured():
        return render_template('chatbot/gmail_error.html',
                               error='Gmail not configured. Please add credentials.json file.')

    callback_url = _get_gmail_callback_url()

    try:
        auth_url, state, code_verifier = gmail.get_authorization_url(callback_url)
        # Store the callback URL + PKCE verifier in session so the callback
        # route uses the same redirect_uri and can complete the token exchange.
        from flask import session
        session['gmail_callback_url'] = callback_url
        session['gmail_code_verifier'] = code_verifier
        return redirect(auth_url)
    except Exception as e:
        return render_template('chatbot/gmail_error.html', error=str(e))


@chatbot_bp.route('/gmail/callback')
def gmail_callback():
    """Handle Gmail OAuth callback"""
    from .services.gmail_service import get_gmail_service

    gmail = get_gmail_service()

    # Use the same callback URL that was used to start the OAuth flow
    from flask import session
    fallback_url = _get_gmail_callback_url()
    callback_url = session.pop('gmail_callback_url', fallback_url)
    code_verifier = session.pop('gmail_code_verifier', None)
    authorization_response = request.url

    # If the callback came on a different host/port than expected, fix the authorization_response URL
    # This handles the case where Google redirects to localhost but we need the configured URI
    if current_app.config.get('GMAIL_REDIRECT_URI'):
        from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
        configured = urlparse(current_app.config['GMAIL_REDIRECT_URI'])
        actual = urlparse(authorization_response)
        # Replace scheme, host, port, path with the configured redirect URI
        fixed = actual._replace(scheme=configured.scheme, netloc=configured.netloc, path=configured.path)
        authorization_response = urlunparse(fixed)

    try:
        gmail.handle_oauth_callback(
            authorization_response=authorization_response,
            redirect_uri=callback_url,
            code_verifier=code_verifier
        )
        # Redirect to settings with success message
        return redirect(url_for('chatbot.settings') + '?gmail=connected')
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Gmail OAuth callback failed: {error_msg}\n  callback_url={callback_url}\n  authorization_response={authorization_response}")
        if 'redirect_uri_mismatch' in error_msg.lower():
            return render_template('chatbot/gmail_error.html',
                                   error='Redirect URI mismatch. Make sure this exact URI is added in Google Cloud Console:',
                                   redirect_uri=callback_url)
        return render_template('chatbot/gmail_error.html',
                               error=f'OAuth failed: {error_msg}',
                               redirect_uri=callback_url)


@chatbot_bp.route('/gmail/disconnect', methods=['POST'])
@admin_required
def gmail_disconnect():
    """Disconnect Gmail account"""
    from .services.gmail_service import get_gmail_service

    gmail = get_gmail_service()
    success = gmail.disconnect()

    return jsonify({'success': success})


@chatbot_bp.route('/api/gmail/emails', methods=['GET'])
def api_get_emails():
    """Fetch recent emails from Gmail"""
    from .services.gmail_service import get_gmail_service

    gmail = get_gmail_service()

    if not gmail.is_authenticated():
        return jsonify({'error': 'Gmail not connected'}), 401

    max_results = request.args.get('max_results', 10, type=int)
    query = request.args.get('query', 'in:inbox')

    emails = gmail.get_recent_emails(max_results=max_results, query=query)

    return jsonify({
        'emails': emails,
        'count': len(emails)
    })


@chatbot_bp.route('/api/gmail/emails/unread', methods=['GET'])
def api_get_unread_emails():
    """Fetch unread emails from Gmail"""
    from .services.gmail_service import get_gmail_service

    gmail = get_gmail_service()

    if not gmail.is_authenticated():
        return jsonify({'error': 'Gmail not connected'}), 401

    max_results = request.args.get('max_results', 20, type=int)
    emails = gmail.get_unread_emails(max_results=max_results)

    return jsonify({
        'emails': emails,
        'count': len(emails)
    })


@chatbot_bp.route('/api/gmail/emails/<message_id>', methods=['GET'])
def api_get_email(message_id):
    """Fetch a single email by ID"""
    from .services.gmail_service import get_gmail_service

    gmail = get_gmail_service()

    if not gmail.is_authenticated():
        return jsonify({'error': 'Gmail not connected'}), 401

    email = gmail.get_email_by_id(message_id)

    if email:
        return jsonify(email)
    else:
        return jsonify({'error': 'Email not found'}), 404


@chatbot_bp.route('/api/gmail/threads/<thread_id>', methods=['GET'])
def api_get_thread(thread_id):
    """Fetch all emails in a thread"""
    from .services.gmail_service import get_gmail_service

    gmail = get_gmail_service()

    if not gmail.is_authenticated():
        return jsonify({'error': 'Gmail not connected'}), 401

    messages = gmail.get_thread(thread_id)

    return jsonify({
        'thread_id': thread_id,
        'messages': messages,
        'count': len(messages)
    })


@chatbot_bp.route('/api/gmail/send', methods=['POST'])
def api_send_email():
    """Send an email via Gmail"""
    from .services.gmail_service import get_gmail_service

    gmail = get_gmail_service()

    if not gmail.is_authenticated():
        return jsonify({'error': 'Gmail not connected'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    required = ['to', 'subject', 'body']
    if not all(k in data for k in required):
        return jsonify({'error': 'Missing required fields: to, subject, body'}), 400

    result = gmail.send_email(
        to=data['to'],
        subject=data['subject'],
        body=data['body'],
        thread_id=data.get('thread_id'),
        reply_to_message_id=data.get('reply_to_message_id')
    )

    if result:
        return jsonify({
            'success': True,
            'message_id': result.get('id'),
            'thread_id': result.get('threadId')
        })
    else:
        return jsonify({'error': 'Failed to send email'}), 500


# Airbnb/Booking send guest-message *notifications* from these domains (and
# subdomains like reply.airbnb.com / guest.booking.com). Those conversations
# already live in Smoobu, so importing the emails as standalone conversations
# creates confusing duplicates. The reconciliation feature still reads these
# emails separately (read-only) to backfill messages Smoobu dropped.
PLATFORM_NOTIFICATION_DOMAINS = (
    'airbnb.com', 'airbnb.de', 'airbnb.es', 'airbnb.fr', 'airbnb.it', 'airbnb.co.uk',
    'booking.com',
)


def _is_platform_notification(sender_email: str) -> bool:
    """True if the sender is an Airbnb/Booking platform notification address."""
    domain = (sender_email or '').lower().rsplit('@', 1)[-1]
    return any(domain == d or domain.endswith('.' + d) for d in PLATFORM_NOTIFICATION_DOMAINS)


@chatbot_bp.route('/api/gmail/process', methods=['POST'])
def api_process_gmail_emails():
    """
    Process unread Gmail emails through the message router.
    This imports emails into ChatBotAI as conversations.
    """
    from .services.gmail_service import get_gmail_service
    from .services.message_router import get_message_router

    gmail = get_gmail_service()
    router = get_message_router()

    # Gmail->inbox import is OFF by default. Airbnb/Booking guest messages
    # already arrive via Smoobu (the real channel), and importing arbitrary
    # Gmail creates noise (platform-notification duplicates, newsletters, vendor
    # mail). Gmail stays connected for the reconciliation safety-net, which runs
    # independently. Re-enable by setting AISettings 'email_import_enabled'=true.
    if (AISettings.get('email_import_enabled', 'false') or 'false').lower() not in ('1', 'true', 'yes', 'on'):
        return jsonify({'processed': 0, 'disabled': True,
                        'message': 'Gmail inbox import is disabled (Smoobu is the message channel)'})

    if not gmail.is_authenticated():
        return jsonify({'error': 'Gmail not connected'}), 401

    max_results = request.args.get('max_results', 10, type=int)
    auto_respond = request.args.get('auto_respond', 'false').lower() == 'true'

    # Get unread emails
    emails = gmail.get_unread_emails(max_results=max_results)

    # Cache user email to avoid repeated API call per email
    user_email = gmail.get_user_email()

    results = []
    for email in emails:
        # Skip emails from ourselves
        if email['sender_email'].lower() == user_email.lower():
            gmail.mark_as_read(email['id'])
            continue

        # Skip Airbnb/Booking notification emails — they duplicate the Smoobu
        # conversation for the same guest. Reconciliation handles dropped
        # messages separately. Mark read so they aren't re-fetched each poll.
        if _is_platform_notification(email['sender_email']):
            gmail.mark_as_read(email['id'])
            results.append({
                'email_id': email['id'],
                'from': email['sender_email'],
                'subject': email['subject'],
                'skipped': 'platform_notification'
            })
            continue

        # Skip emails already imported (check by platform_message_id)
        existing = Message.query.filter_by(
            platform_message_id=email['id']
        ).first()
        if existing:
            gmail.mark_as_read(email['id'])
            continue

        # Process through message router
        result = router.process_incoming_message(
            platform='email',
            platform_conversation_id=email['thread_id'],
            sender_email=email['sender_email'],
            sender_name=email['sender_name'],
            message_content=email['body'],
            subject=email['subject'],
            platform_message_id=email['id'],
            auto_respond=auto_respond
        )

        # Mark as read
        gmail.mark_as_read(email['id'])

        results.append({
            'email_id': email['id'],
            'from': email['sender_email'],
            'subject': email['subject'],
            'processed': result['success'],
            'conversation_id': result.get('conversation_id'),
            'ai_responded': result.get('ai_response') is not None
        })

    return jsonify({
        'processed': len(results),
        'results': results
    })


@chatbot_bp.route('/api/gmail/reply/<int:conversation_id>', methods=['POST'])
def api_gmail_reply(conversation_id):
    """
    Send a reply via Gmail for a conversation.
    Uses the AI response or a custom message.
    """
    from .services.gmail_service import get_gmail_service
    from .services.message_router import get_message_router

    gmail = get_gmail_service()

    if not gmail.is_authenticated():
        return jsonify({'error': 'Gmail not connected'}), 401

    conversation = Conversation.query.get_or_404(conversation_id)

    if conversation.platform != 'email':
        return jsonify({'error': 'Conversation is not an email conversation'}), 400

    data = request.get_json() or {}

    # Get the message to send
    if 'message' in data:
        message_content = data['message']
    else:
        # Generate AI response
        router = get_message_router()
        result = router.generate_ai_response_for_conversation(conversation_id)
        if not result['success']:
            return jsonify({'error': result.get('error', 'Failed to generate response')}), 500
        message_content = result['response']

    # Get the original email details for threading
    last_guest_message = Message.query.filter_by(
        conversation_id=conversation_id,
        sender_type='guest'
    ).order_by(Message.sent_at.desc()).first()

    # Send email
    guest = conversation.guest
    send_result = gmail.send_email(
        to=guest.email,
        subject=conversation.subject or 'Re: Your inquiry',
        body=message_content,
        thread_id=conversation.platform_id,
        reply_to_message_id=last_guest_message.platform_message_id if last_guest_message else None
    )

    if send_result:
        # Store as owner message
        router = get_message_router()
        owner_result = router.process_owner_message(
            conversation_id=conversation_id,
            content=message_content,
            extract_memory=True,
            sent_via_app=True
        )

        # Assign conversation to the user who is responding
        if current_user.is_authenticated and conversation.user_id is None:
            conversation.user_id = current_user.id
            db.session.commit()

        # Store correction if host edited an AI draft
        original_ai_content = data.get('original_ai_content')
        if original_ai_content:
            _store_correction_if_needed(original_ai_content, message_content, conversation)

        return jsonify({
            'success': True,
            'gmail_message_id': send_result.get('id'),
            'message_id': owner_result.get('message_id'),
            'content': message_content
        })
    else:
        return jsonify({'error': 'Failed to send email'}), 500


# ============================================================================
# SMOOBU INTEGRATION ROUTES
# ============================================================================

def _smoobu_slot_service(default_slot=1):
    """Service for the ?slot=N account (slot 1 = the original account)."""
    from .services.smoobu_service import (MAX_SMOOBU_ACCOUNTS, _smoobu_services)
    try:
        slot = int(request.args.get('slot') or (request.get_json(silent=True) or {}).get('slot')
                   or default_slot)
    except (TypeError, ValueError):
        slot = default_slot
    if slot < 1 or slot > MAX_SMOOBU_ACCOUNTS:
        return None
    return _smoobu_services.get(slot)


@chatbot_bp.route('/smoobu/status')
def smoobu_status():
    """Get Smoobu connection status for one account slot."""
    smoobu = _smoobu_slot_service()
    if not smoobu:
        return jsonify({'configured': False, 'authenticated': False, 'api_key_masked': ''})
    return jsonify(smoobu.get_status())


@chatbot_bp.route('/smoobu/connect', methods=['POST'])
@admin_required
def smoobu_connect():
    """Save a Smoobu API key for one account slot and verify the connection."""
    data = request.get_json()
    api_key = data.get('api_key', '').strip() if data else ''
    # Smoobu's newer tokens are a pair: the label (X-API-Key) plus a secret used
    # to sign each request. Legacy keys have no secret and stay single-header.
    api_secret = data.get('api_secret', '').strip() if data else ''

    if not api_key:
        return jsonify({'error': 'API key is required'}), 400

    from .services.smoobu_service import (settings_key, secret_settings_key,
                                          get_smoobu_service_by_account)
    smoobu = _smoobu_slot_service()
    if not smoobu:
        return jsonify({'error': 'Unknown Smoobu account slot'}), 400

    # Save to DB and invalidate the in-memory cache so the next request reads the new key
    AISettings.set(settings_key(smoobu.slot), api_key,
                   description=f'Smoobu API key (slot {smoobu.slot})')
    AISettings.set(secret_settings_key(smoobu.slot), api_secret,
                   description=f'Smoobu HMAC secret (slot {smoobu.slot})')
    smoobu.reload_api_key()

    # Identify the account behind this key — the id webhooks arrive with.
    account_id = smoobu.fetch_account_id()
    if not account_id:
        AISettings.set(settings_key(smoobu.slot), '',
                       description=f'Smoobu API key (slot {smoobu.slot})')
        AISettings.set(secret_settings_key(smoobu.slot), '',
                       description=f'Smoobu HMAC secret (slot {smoobu.slot})')
        smoobu.reload_api_key()
        return jsonify({'error': 'Invalid API key — could not connect to Smoobu'}), 400

    # Reject the same account twice: two slots sharing one account id would make
    # webhook routing ambiguous and duplicate every sync.
    other = next((svc for svc in _smoobu_services_all()
                  if svc.slot != smoobu.slot and svc.is_configured()
                  and str(svc.account_id or '') == account_id), None)
    if other is not None:
        AISettings.set(settings_key(smoobu.slot), '',
                       description=f'Smoobu API key (slot {smoobu.slot})')
        AISettings.set(secret_settings_key(smoobu.slot), '',
                       description=f'Smoobu HMAC secret (slot {smoobu.slot})')
        smoobu.reload_api_key()
        return jsonify({'error': f'This Smoobu account is already connected (slot {other.slot})'}), 400

    # A brand-new account starts from now: the team wants the messages that
    # arrive from here on, not years of imported history. Reconnecting an account
    # we already have chats for (e.g. rotating its key) keeps its existing scope.
    from .services.smoobu_service import sync_from_settings_key
    already_synced = Conversation.query.filter_by(smoobu_account_id=account_id).first()
    if not already_synced and not AISettings.get(sync_from_settings_key(smoobu.slot)):
        AISettings.set(sync_from_settings_key(smoobu.slot),
                       datetime.utcnow().isoformat(),
                       description=f'Smoobu sync cutoff (slot {smoobu.slot})')
        smoobu.reload_api_key()

    return jsonify({'success': True, 'message': 'Connected to Smoobu',
                    'account_id': account_id, 'slot': smoobu.slot,
                    'sync_from': AISettings.get(sync_from_settings_key(smoobu.slot))})


def _smoobu_services_all():
    from .services.smoobu_service import _smoobu_services
    return list(_smoobu_services.values())


@chatbot_bp.route('/smoobu/disconnect', methods=['POST'])
@admin_required
def smoobu_disconnect():
    """Clear the Smoobu API key of one account slot."""
    smoobu = _smoobu_slot_service()
    if smoobu:
        smoobu.disconnect()
    return jsonify({'success': True})


@chatbot_bp.route('/api/webhooks/smoobu', methods=['POST', 'GET'])
def webhook_smoobu_discovery():
    """Smoobu webhook endpoint.

    Two responsibilities, in order:
      1. ALWAYS log the full payload to instance/smoobu_webhooks.log.
         This was originally a pure-discovery endpoint and we keep that
         behaviour so any new/unknown Smoobu event type still gets captured
         and we can extend the handler later.
      2. Dispatch on the `action` field for known events:
           - "newMessage" → trigger sync_conversation_messages(booking.id)
             in a background thread so we respond fast (Smoobu retries if
             we take >5s).
           - "onlineCheckInUpdate" → logged only (no DB writes yet).
           - anything else → logged only.

    Endpoint name starts with 'webhook_' so the before_request hook in
    routes.py:114 skips login_required.

    Always returns 200 so Smoobu doesn't mark the webhook as failing.
    Errors during dispatch are swallowed + logged — they must not block
    the response to Smoobu.

    Spec-reference: WEBHOOK_IMPLEMENTATION.md Step 2 (2026-05-18).
    """
    import hashlib
    import hmac
    import json
    import os
    import threading
    from datetime import datetime
    from flask import request, current_app

    # ---- 0. Optional HMAC signature verification ----
    # If SMOOBU_WEBHOOK_SECRET is set, every webhook must carry a valid
    # signature header — otherwise we reject with 401 to block forgeries.
    # If the secret is NOT set, we accept all webhooks (back-compat with
    # the live deployment) but log a one-time warning so the user knows
    # this surface is unauthenticated.
    raw_body_bytes = request.get_data(cache=True)
    webhook_secret = (os.environ.get('SMOOBU_WEBHOOK_SECRET')
                      or current_app.config.get('SMOOBU_WEBHOOK_SECRET'))
    if webhook_secret and request.method == 'POST':
        sig_header = (
            request.headers.get('X-Smoobu-Signature')
            or request.headers.get('X-Webhook-Signature')
            or request.headers.get('X-Signature')
            or ''
        ).strip()
        expected = hmac.new(
            webhook_secret.encode('utf-8'),
            raw_body_bytes,
            hashlib.sha256,
        ).hexdigest()
        # Accept either "sha256=<hex>" or bare hex.
        candidate = sig_header.split('=', 1)[-1] if '=' in sig_header else sig_header
        if not candidate or not hmac.compare_digest(candidate, expected):
            current_app.logger.warning(
                'Smoobu webhook signature MISMATCH from %s — rejecting',
                request.remote_addr,
            )
            return jsonify({'error': 'invalid signature'}), 401
    elif request.method == 'POST':
        current_app.logger.warning(
            'Smoobu webhook accepted WITHOUT signature verification — '
            'set SMOOBU_WEBHOOK_SECRET env var to enable HMAC check.'
        )

    # ---- 1. Discovery logging (unchanged from original endpoint) ----
    try:
        raw_body = raw_body_bytes.decode('utf-8', errors='replace')
    except Exception:
        raw_body = '<unreadable>'

    try:
        parsed_json = request.get_json(silent=True)
    except Exception:
        parsed_json = None

    entry = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'method': request.method,
        'remote_addr': request.remote_addr,
        'path': request.path,
        'query_string': request.query_string.decode('utf-8', errors='replace'),
        'headers': {k: v for k, v in request.headers.items()},
        'raw_body': raw_body,
        'parsed_json': parsed_json,
    }

    log_dir = os.path.join(current_app.instance_path, '')
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, 'smoobu_webhooks.log')
    try:
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + '\n')
    except Exception:
        current_app.logger.exception('Failed to write Smoobu webhook log entry')

    current_app.logger.info(
        'Smoobu webhook received: method=%s bytes=%d json=%s',
        request.method, len(raw_body), 'yes' if parsed_json is not None else 'no'
    )

    # ---- 2. Dispatch on action (only for valid POST JSON) ----
    # Wrapped in try/except so any handler bug NEVER prevents the 200 response.
    try:
        if request.method == 'POST' and isinstance(parsed_json, dict):
            action = parsed_json.get('action')
            data = parsed_json.get('data') or {}
            # Which Smoobu account fired this — 'user' is the same id GET /me
            # returns for that account's API key. Routes the work to the right key.
            account_id = parsed_json.get('user')

            if action == 'newMessage':
                # Smoobu payload: {"action":"newMessage","user":...,
                #                  "data":{"id":<msgid>,"sender":"host"|"guest",
                #                          "booking":{"id":<bookingid>}}}
                booking = data.get('booking') or {}
                booking_id = booking.get('id') or data.get('bookingId')
                if booking_id:
                    app_obj = current_app._get_current_object()
                    threading.Thread(
                        target=_run_webhook_message_sync,
                        args=(app_obj, str(booking_id), account_id),
                        daemon=True,
                        name=f'smoobu-webhook-{booking_id}',
                    ).start()
                    current_app.logger.info(
                        'Smoobu newMessage webhook dispatched: booking=%s msg=%s sender=%s',
                        booking_id, data.get('id'), data.get('sender')
                    )
                else:
                    current_app.logger.warning(
                        'Smoobu newMessage webhook missing booking id: %s', parsed_json
                    )

            elif action == 'cancelReservation':
                # Smoobu payload likely mirrors newReservation (full reservation
                # inline) but we only need the reservation id. Mark the linked
                # Conversation as cancelled so the UI can show a "Storniert"
                # label. NO change to AI behavior, history, or visibility —
                # the team decides whether to keep chatting.
                cancel_id = data.get('id') or data.get('bookingId')
                if cancel_id:
                    app_obj = current_app._get_current_object()
                    threading.Thread(
                        target=_run_webhook_cancel_reservation,
                        args=(app_obj, cancel_id, account_id),
                        daemon=True,
                        name=f'smoobu-webhook-cancel-{cancel_id}',
                    ).start()
                    current_app.logger.info(
                        'Smoobu cancelReservation webhook dispatched: res=%s', cancel_id
                    )
                else:
                    current_app.logger.warning(
                        'Smoobu cancelReservation webhook missing id: %s', parsed_json
                    )

            elif action == 'updateReservation':
                # Silent refresh of Conversation.check_in/check_out and
                # GuestDetail records (adults, children, language, etc.).
                # No team notification — user wants this invisible, just
                # the data kept current.
                if data.get('id'):
                    app_obj = current_app._get_current_object()
                    threading.Thread(
                        target=_run_webhook_update_reservation,
                        args=(app_obj, data, account_id),
                        daemon=True,
                        name=f'smoobu-webhook-update-{data.get("id")}',
                    ).start()
                    current_app.logger.info(
                        'Smoobu updateReservation webhook dispatched: res=%s', data.get('id')
                    )
                else:
                    current_app.logger.warning(
                        'Smoobu updateReservation webhook missing data.id: %s', parsed_json
                    )

            elif action == 'newReservation':
                # Smoobu fires this with the FULL reservation inline (dates,
                # adults/children, channel, language, phone, notice, etc.).
                # We pre-create/match the Guest and populate GuestDetail so the
                # very first AI response to the first guest message already
                # has rich context (party size, channel, language preference,
                # booking note). No Conversation is created yet — that happens
                # via MessageRouter when the first message actually arrives.
                if data.get('id'):
                    app_obj = current_app._get_current_object()
                    threading.Thread(
                        target=_run_webhook_reservation_enrich,
                        args=(app_obj, data, account_id),
                        daemon=True,
                        name=f'smoobu-webhook-res-{data.get("id")}',
                    ).start()
                    current_app.logger.info(
                        'Smoobu newReservation webhook dispatched: res=%s channel=%s',
                        data.get('id'),
                        (data.get('channel') or {}).get('name') if isinstance(data.get('channel'), dict) else data.get('channel')
                    )
                else:
                    current_app.logger.warning(
                        'Smoobu newReservation webhook missing data.id: %s', parsed_json
                    )

            # Other action types fall through — logged only via the
            # discovery write above. Add more `elif action == ...:` branches
            # as new event types appear.
    except Exception:
        # Never let a handler bug break the 200 response to Smoobu.
        current_app.logger.exception('Smoobu webhook dispatch failed')

    # Always 200 so Smoobu doesn't mark the webhook as failing and back off
    return jsonify({'success': True, 'received': True}), 200


def _webhook_service(account_id):
    """Configured SmoobuService for a webhook's account id, or None.

    Falls back to the primary account when the payload carries no id (older
    Smoobu payloads / manual replays) so behaviour matches the single-account era.
    """
    from .services.smoobu_service import get_smoobu_service, get_smoobu_service_by_account
    svc = get_smoobu_service_by_account(account_id) if account_id else None
    if svc is None and not account_id:
        svc = get_smoobu_service()
    return svc if (svc and svc.is_configured()) else None


def _run_webhook_message_sync(app, booking_id, account_id=None):
    """Background worker: sync messages for one Smoobu reservation.

    Spawned as a daemon thread by webhook_smoobu_discovery on newMessage events.
    Reuses the existing, well-tested SmoobuService.sync_conversation_messages
    path — same dedup logic (p14 unique index + IntegrityError guard), same
    last_message_at / is_read semantics as the periodic daemon sync. No new
    business logic introduced by the webhook.

    Errors are logged and swallowed (we cannot signal failure back to Smoobu
    after the route has already returned).
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        with app.app_context():
            smoobu = _webhook_service(account_id)
            if not smoobu:
                logger.warning('Webhook sync skipped: no Smoobu account %s (booking=%s)',
                               account_id, booking_id)
                return
            result = smoobu.sync_conversation_messages(booking_id)
            imported = result.get('imported', 0)
            if imported:
                logger.info('Webhook sync imported %d message(s) for booking=%s', imported, booking_id)
            else:
                logger.debug('Webhook sync no-op for booking=%s (already in sync)', booking_id)
    except Exception:
        logger.exception('Webhook background sync failed for booking=%s', booking_id)


def _run_webhook_cancel_reservation(app, reservation_id, account_id=None):
    """Background worker: mark the Conversation for one Smoobu reservation as cancelled.

    Spawned as a daemon thread by webhook_smoobu_discovery on cancelReservation events.
    Delegates to SmoobuService.mark_reservation_cancelled which is idempotent.
    Errors are logged and swallowed.
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        with app.app_context():
            smoobu = _webhook_service(account_id)
            if not smoobu:
                logger.warning(
                    'Webhook cancel skipped: no Smoobu account %s (res=%s)',
                    account_id, reservation_id
                )
                return
            ok = smoobu.mark_reservation_cancelled(reservation_id)
            if not ok:
                logger.debug('Webhook cancel: no Conversation matched res=%s', reservation_id)
    except Exception:
        logger.exception('Webhook cancel-reservation failed for res=%s', reservation_id)


def _run_webhook_update_reservation(app, res_data, account_id=None):
    """Background worker: silently refresh Conversation/Guest data from updateReservation.

    Spawned as a daemon thread by webhook_smoobu_discovery on updateReservation events.
    Delegates to SmoobuService.update_reservation_from_webhook. Errors are logged
    and swallowed.
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        with app.app_context():
            smoobu = _webhook_service(account_id)
            if not smoobu:
                logger.warning(
                    'Webhook update skipped: no Smoobu account %s (res=%s)',
                    account_id, res_data.get('id'),
                )
                return
            smoobu.update_reservation_from_webhook(res_data)
    except Exception:
        logger.exception(
            'Webhook update-reservation failed for res=%s', res_data.get('id')
        )


def _run_webhook_reservation_enrich(app, res_data, account_id=None):
    """Background worker: pre-enrich Guest from a Smoobu newReservation payload.

    Spawned as a daemon thread by webhook_smoobu_discovery on newReservation
    events. Delegates to SmoobuService.process_new_reservation, which uses
    the existing find_or_create_guest + _enrich_guest_from_reservation upsert
    helpers. Errors are logged and swallowed.
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        with app.app_context():
            smoobu = _webhook_service(account_id)
            if not smoobu:
                logger.warning(
                    'Webhook reservation enrich skipped: no Smoobu account %s (res=%s)',
                    account_id, res_data.get('id'),
                )
                return
            guest = smoobu.process_new_reservation(res_data)
            if guest:
                logger.info(
                    'Webhook reservation pre-enrich complete: res=%s guest_id=%s',
                    res_data.get('id'), guest.id,
                )
            else:
                logger.debug(
                    'Webhook reservation pre-enrich no-op: res=%s', res_data.get('id')
                )
    except Exception:
        logger.exception(
            'Webhook reservation enrich failed for res=%s', res_data.get('id')
        )


@chatbot_bp.route('/api/smoobu/sync', methods=['POST'])
def api_smoobu_sync():
    """Trigger a Smoobu sync in the background and return immediately.

    The sync itself can take 2+ minutes for accounts with many properties,
    which exceeds the Cloudflare tunnel's 100s HTTP timeout and ties up a
    Waitress thread. We hand off to the daemon's _run_one_sync (which has
    a lock that prevents overlap with the periodic 2-min cycle) and return
    right away. New messages appear via the inbox's regular polling.
    """
    import threading
    from flask import current_app
    from .services.smoobu_service import get_smoobu_service

    smoobu = get_smoobu_service()
    if not smoobu or not smoobu.is_configured():
        return jsonify({'error': 'Smoobu not connected'}), 400

    trigger = getattr(current_app._get_current_object(), 'smoobu_trigger_sync', None)
    if trigger is None:
        # Fallback for dev mode where the background daemon didn't start.
        result = smoobu.sync_messages(force=True)
        return jsonify(result)

    # force=True so a human click always does real work, even if the daemon
    # just ran within the 30s cooldown. The daemon itself leaves force=False
    # to avoid duplicate work between adjacent cycles.
    threading.Thread(
        target=lambda: trigger(force=True),
        daemon=True,
        name='smoobu-manual-sync',
    ).start()
    return jsonify({'success': True, 'started': True})


_email_sweep_state = {'running': False, 'last': None}


@chatbot_bp.route('/api/email/sweep', methods=['POST'])
@login_required
def email_sweep():
    """Inbox button: pull Booking guest messages straight out of Gmail.

    Fire-and-forget — a full sweep fetches hundreds of message bodies and would
    blow past the Cloudflare tunnel's 100s timeout and tie up a Waitress thread.
    Inserted messages surface through the inbox's normal polling; the result of
    the last run is readable via GET so the UI can report it.
    """
    import threading
    from flask import current_app

    if _email_sweep_state['running']:
        return jsonify({'success': True, 'started': False, 'reason': 'already_running'})

    from .services.gmail_service import get_gmail_service
    gmail = get_gmail_service()
    if not gmail or not gmail.is_authenticated():
        return jsonify({'success': False, 'error': 'Gmail nicht verbunden'}), 400

    try:
        days = int((request.get_json(silent=True) or {}).get('days', 30))
    except (TypeError, ValueError):
        days = 30
    days = max(1, min(days, 365))

    app_obj = current_app._get_current_object()

    def _run():
        from .services.email_reconcile import sweep_booking_emails
        _email_sweep_state['running'] = True
        try:
            with app_obj.app_context():
                _email_sweep_state['last'] = sweep_booking_emails(gmail, days=days)
        except Exception:
            app_obj.logger.exception("email sweep failed")
            _email_sweep_state['last'] = {'error': True}
        finally:
            _email_sweep_state['running'] = False
            with app_obj.app_context():
                db.session.remove()

    threading.Thread(target=_run, daemon=True, name='email-sweep').start()
    return jsonify({'success': True, 'started': True, 'days': days})


@chatbot_bp.route('/api/email/sweep', methods=['GET'])
@login_required
def email_sweep_status():
    """Progress/result of the last inbox-wide email sweep."""
    return jsonify({'running': _email_sweep_state['running'],
                    'last': _email_sweep_state['last']})


@chatbot_bp.route('/api/smoobu/sync/<int:conversation_id>', methods=['POST'])
def api_smoobu_sync_conversation(conversation_id):
    """Sync messages for a single Smoobu conversation (lightweight)"""
    from .services.smoobu_service import get_smoobu_service_for

    conversation = Conversation.query.get_or_404(conversation_id)
    if not conversation.smoobu_reservation_id:
        return jsonify({'error': 'Not a Smoobu conversation'}), 400

    smoobu = get_smoobu_service_for(conversation)
    if not smoobu or not smoobu.is_configured():
        return jsonify({'error': 'Smoobu not connected'}), 400

    result = smoobu.sync_conversation_messages(conversation.smoobu_reservation_id)
    return jsonify(result)


@chatbot_bp.route('/api/smoobu/sync-properties', methods=['POST'])
def api_smoobu_sync_properties():
    """Sync properties (rooms, guests, check-in times) from one Smoobu account."""
    smoobu = _smoobu_slot_service()
    if not smoobu or not smoobu.is_configured():
        return jsonify({'error': 'Smoobu not connected'}), 400

    result = smoobu.sync_properties()
    return jsonify(result)


@chatbot_bp.route('/api/smoobu/backfill-historical', methods=['POST'])
@admin_required
def api_smoobu_backfill_historical():
    """One-time historical backfill: walk ALL Smoobu /threads pages and import any
    missing conversations/messages. Idempotent (dedup by platform_message_id).

    Runs in a background thread so the request returns immediately — a full walk
    of hundreds of pages takes minutes and would exceed the Cloudflare 100s HTTP
    timeout. Reuses SmoobuService.sync_recent_threads(max_pages=None), which is
    rate-limit aware via the shared _request 429 handling.
    """
    from .services.smoobu_service import get_smoobu_service
    smoobu = get_smoobu_service()
    if not smoobu or not smoobu.is_configured():
        return jsonify({'error': 'Smoobu not connected'}), 400

    import threading
    from flask import current_app
    app_obj = current_app._get_current_object()

    def _run():
        with app_obj.app_context():
            try:
                res = smoobu.sync_recent_threads(max_pages=None)
                logger.info("Smoobu historical backfill complete: %s", res)
                print(
                    f"[ChatBotAI] Smoobu historical backfill complete: "
                    f"{res.get('synced')} threads synced, {res.get('imported')} msg(s) imported",
                    flush=True)
            except Exception:
                logger.exception("Smoobu historical backfill failed")

    threading.Thread(target=_run, daemon=True, name='smoobu-backfill').start()
    return jsonify({'success': True, 'started': True,
                    'message': 'Historical backfill started in background'})


@chatbot_bp.route('/api/smoobu/fix-timestamps', methods=['POST'])
def api_smoobu_fix_timestamps():
    """One-time fix: re-fetch Smoobu messages and update sent_at timestamps."""
    from .services.smoobu_service import get_smoobu_service, _parse_smoobu_timestamp
    from datetime import datetime as dt

    smoobu = get_smoobu_service()
    if not smoobu or not smoobu.is_configured():
        return jsonify({'error': 'Smoobu not connected'}), 400

    # Find all Smoobu conversations
    conversations = Conversation.query.filter_by(platform='smoobu').all()
    fixed = 0
    checked = 0
    conv_count = 0

    for conv in conversations:
        if not conv.smoobu_reservation_id:
            continue
        conv_count += 1
        msg_data = smoobu.get_reservation_messages(conv.smoobu_reservation_id)
        if not msg_data:
            continue

        api_messages = []
        if isinstance(msg_data, list):
            api_messages = msg_data
        elif isinstance(msg_data, dict):
            api_messages = msg_data.get('messages') or msg_data.get('data') or []

        # Load all DB messages for this conversation for content-based matching
        db_messages = Message.query.filter_by(conversation_id=conv.id).all()

        for msg in api_messages:
            msg_id = str(msg.get('id', ''))
            checked += 1

            created_at = msg.get('created_at') or msg.get('createdAt') or msg.get('date')
            if not created_at:
                continue
            msg_time = _parse_smoobu_timestamp(created_at)
            if not msg_time:
                continue

            # Try matching by platform_message_id first
            platform_msg_id = f"smoobu-{conv.smoobu_reservation_id}-{msg_id}" if msg_id else None
            existing = None
            if platform_msg_id:
                existing = next((m for m in db_messages if m.platform_message_id == platform_msg_id), None)

            # Fallback: match by content (stripped) if no platform_message_id match
            if not existing:
                msg_content = (msg.get('message') or msg.get('htmlMessage')
                               or msg.get('message_body') or msg.get('body') or '').strip()
                if msg_content:
                    existing = next((m for m in db_messages
                                     if m.content and m.content.strip() == msg_content), None)

            if existing and existing.sent_at != msg_time:
                existing.sent_at = msg_time
                fixed += 1

    # Also fix conversation timestamps to match the latest message.
    # last_message_at is authoritative for sort; updated_at is the polling
    # tripwire and we align it to the latest message during a full fix.
    for conv in conversations:
        latest_msg = Message.query.filter_by(
            conversation_id=conv.id
        ).order_by(Message.sent_at.desc()).first()
        if latest_msg and latest_msg.sent_at:
            changed = False
            if not conv.last_message_at or conv.last_message_at != latest_msg.sent_at:
                conv.last_message_at = latest_msg.sent_at
                changed = True
            if not conv.updated_at or conv.updated_at != latest_msg.sent_at:
                conv.updated_at = latest_msg.sent_at
                changed = True
            if changed:
                fixed += 1

    db.session.commit()
    return jsonify({
        'success': True,
        'fixed': fixed,
        'conversations_checked': conv_count,
        'messages_checked': checked
    })


@chatbot_bp.route('/api/smoobu/debug-messages/<int:conversation_id>')
def api_smoobu_debug_messages(conversation_id):
    """Debug: show raw Smoobu API response + DB timestamps for a conversation."""
    from .services.smoobu_service import get_smoobu_service_for

    conversation = Conversation.query.get_or_404(conversation_id)
    if not conversation.smoobu_reservation_id:
        return jsonify({'error': 'No Smoobu reservation linked'}), 400

    smoobu = get_smoobu_service_for(conversation)
    if not smoobu or not smoobu.is_configured():
        return jsonify({'error': 'Smoobu not connected'}), 400

    # Raw API response
    raw = smoobu.get_reservation_messages(conversation.smoobu_reservation_id)

    # DB messages for comparison
    db_msgs = Message.query.filter_by(
        conversation_id=conversation_id
    ).order_by(Message.sent_at.asc()).all()

    return jsonify({
        'reservation_id': conversation.smoobu_reservation_id,
        'smoobu_raw_response': raw,
        'db_messages': [{
            'id': m.id,
            'sender_type': m.sender_type,
            'sent_at': m.sent_at.isoformat() if m.sent_at else None,
            'platform_message_id': m.platform_message_id,
            'content_preview': (m.content or '')[:80]
        } for m in db_msgs]
    })


@chatbot_bp.route('/api/smoobu/dedup-fix', methods=['POST'])
def api_smoobu_dedup_fix():
    """One-time cleanup: remove duplicate owner messages created by sync.

    For each Smoobu conversation, if two owner messages have the same normalized
    content and one has a platform_message_id while the other doesn't, the one
    with the platform_message_id is the sync-imported duplicate — delete it and
    backfill the platform_message_id onto the original.
    """
    from .services.smoobu_service import _normalize_content

    fixed = 0
    conversations = Conversation.query.filter_by(platform='smoobu').all()
    for conv in conversations:
        # Get all owner/ai messages, ordered by sent_at
        msgs = Message.query.filter(
            Message.conversation_id == conv.id,
            Message.sender_type.in_(['owner', 'ai'])
        ).order_by(Message.sent_at.asc()).all()

        # Group: messages WITHOUT platform_message_id (originals from our app)
        originals = [m for m in msgs if not m.platform_message_id]
        # Group: messages WITH smoobu platform_message_id (from sync)
        synced = [m for m in msgs if m.platform_message_id
                  and m.platform_message_id.startswith('smoobu-')]

        for dup in synced:
            dup_norm = _normalize_content(dup.content or '')
            for orig in originals:
                orig_norm = _normalize_content(orig.content or '')
                if dup_norm == orig_norm:
                    # Time check: within 2 hours
                    if orig.sent_at and dup.sent_at:
                        diff = abs((dup.sent_at - orig.sent_at).total_seconds())
                        if diff > 7200:
                            continue
                    # Backfill the platform_message_id, delete the duplicate
                    orig.platform_message_id = dup.platform_message_id
                    db.session.delete(dup)
                    db.session.commit()
                    originals.remove(orig)
                    fixed += 1
                    break

    return jsonify({'success': True, 'duplicates_removed': fixed})


def _recent_duplicate_owner_reply(conversation_id, content, within_seconds=120):
    """True if an identical outgoing message already went to this conversation in
    the last `within_seconds`. Guards against double-send: Smoobu's send API
    returns no message id, so a slow/timed-out or 429'd send can be re-issued
    (by a retry or a staff re-click after a false 'failed' error) and deliver the
    same text to the guest twice. Exact normalized-text match only — a genuinely
    different reply is never blocked.
    ponytail: 2-min window blocks identical rapid re-sends; a real repeat can wait."""
    from datetime import timedelta
    from .services.smoobu_service import _normalize_content
    cutoff = datetime.utcnow() - timedelta(seconds=within_seconds)
    target = _normalize_content(content)
    recent = Message.query.filter(
        Message.conversation_id == conversation_id,
        Message.sender_type.in_(['owner', 'ai']),
        Message.sent_at >= cutoff,
    ).all()
    return any(_normalize_content(m.content or '') == target for m in recent)


# Per-conversation send locks. The duplicate guard above only reads *committed*
# rows, so the old check-then-send-then-store sequence had a TOCTOU race: the
# (sometimes slow, 20-40s) Smoobu send sat between the check and the store, so two
# overlapping sends of the same text both passed the guard before either persisted
# — delivering the reply to the guest twice. Holding a per-conversation lock across
# check+send+store makes them atomic, so the second send sees the first's stored
# row and is blocked. Production is single-process Waitress, so an in-process lock
# is sufficient.
# ponytail: unbounded dict, one lock per conversation ever replied to — trivially
# small for a few thousand chats on one process; add eviction only if it grows.
_conversation_send_locks = {}
_conversation_send_locks_guard = threading.Lock()


def _conversation_send_lock(conversation_id):
    with _conversation_send_locks_guard:
        lock = _conversation_send_locks.get(conversation_id)
        if lock is None:
            lock = threading.Lock()
            _conversation_send_locks[conversation_id] = lock
        return lock


def _guarded_smoobu_reply(conversation, content, send_fn):
    """Atomically (per conversation) guard-check, send, and store an owner reply.

    send_fn() performs the actual Smoobu send and returns its raw result (falsy on
    failure). The per-conversation lock spans check+send+store so a second identical
    send to the same chat cannot slip past the duplicate guard while this one's
    (possibly slow) send is in flight. Stores the message only on a successful send,
    so a failed send leaves nothing behind. Returns exactly one of:
      {'duplicate_skipped': True} | {'message_id': <id>} | {'error': <msg>}"""
    with _conversation_send_lock(conversation.id):
        if _recent_duplicate_owner_reply(conversation.id, content):
            logger.info(f"Duplicate reply blocked for conversation {conversation.id}")
            return {'duplicate_skipped': True}
        send_result = send_fn()
        if not send_result:
            return {'error': 'Failed to send message via Smoobu'}
        smoobu_msg_id = None
        if isinstance(send_result, dict):
            smoobu_msg_id = str(send_result.get('id') or send_result.get('message_id')
                                or send_result.get('messageId') or '')
        platform_msg_id = (f"smoobu-{conversation.smoobu_reservation_id}-{smoobu_msg_id}"
                           if smoobu_msg_id else None)
        owner_result = get_message_router().process_owner_message(
            conversation_id=conversation.id, content=content, extract_memory=True,
            platform_message_id=platform_msg_id, sent_via_app=True)
        return {'message_id': owner_result.get('message_id')}


@chatbot_bp.route('/api/messages/<int:message_id>/retry', methods=['POST'])
def api_retry_message(message_id):
    """Re-send an owner message whose platform send failed.

    Deliberately bypasses `_recent_duplicate_owner_reply`: the stored failed copy
    would otherwise block its own retry. The guest could in theory receive it twice
    if the original send actually landed despite reporting failure, so this is only
    ever reached by an explicit human click on a message marked "not delivered".
    """
    from .services.smoobu_service import get_smoobu_service_for

    message = Message.query.get_or_404(message_id)
    if message.delivery_state != 'failed':
        return jsonify({'error': 'Message is not marked as failed'}), 400

    conversation = Conversation.query.get_or_404(message.conversation_id)
    if conversation.platform != 'smoobu' or not conversation.smoobu_reservation_id:
        return jsonify({'error': 'Conversation has no Smoobu reservation to retry through'}), 400

    smoobu = get_smoobu_service_for(conversation)
    if not smoobu or not smoobu.is_configured():
        return jsonify({'error': 'Smoobu not connected'}), 400

    with _conversation_send_lock(conversation.id):
        try:
            send_result = smoobu.send_message(conversation.smoobu_reservation_id, message.content)
        except Exception:
            logger.exception("Retry send failed for message %s", message_id)
            send_result = None
        if not send_result:
            return jsonify({'error': 'Failed to send message via Smoobu'}), 502

        smoobu_msg_id = None
        if isinstance(send_result, dict):
            smoobu_msg_id = str(send_result.get('id') or send_result.get('message_id')
                                or send_result.get('messageId') or '')
        # Clearing the sentinel is what flips the bubble back to "delivered".
        message.platform_message_id = (
            f"smoobu-{conversation.smoobu_reservation_id}-{smoobu_msg_id}"
            if smoobu_msg_id else None)
        db.session.commit()

    return jsonify({'success': True, 'delivery': message.delivery_state,
                    'message_id': message.id})


@chatbot_bp.route('/api/smoobu/reply/<int:conversation_id>', methods=['POST'])
def api_smoobu_reply(conversation_id):
    """Send a reply through Smoobu API"""
    from .services.smoobu_service import get_smoobu_service_for
    from .services.message_router import get_message_router

    conversation = Conversation.query.get_or_404(conversation_id)

    if conversation.platform != 'smoobu':
        return jsonify({'error': 'Not a Smoobu conversation'}), 400

    if not conversation.smoobu_reservation_id:
        return jsonify({'error': 'No Smoobu reservation linked'}), 400

    data = request.get_json()
    message_content = data.get('message', '').strip() if data else ''
    if not message_content:
        return jsonify({'error': 'Message is required'}), 400

    smoobu = get_smoobu_service_for(conversation)
    if not smoobu or not smoobu.is_configured():
        return jsonify({'error': 'Smoobu not connected'}), 400

    # Atomic per-conversation guard+send+store: never deliver the same reply twice,
    # even when two sends race across a slow Smoobu call (see helper docstring).
    result = _guarded_smoobu_reply(
        conversation, message_content,
        lambda: smoobu.send_message(conversation.smoobu_reservation_id, message_content))

    if result.get('duplicate_skipped'):
        return jsonify({
            'success': True, 'duplicate_skipped': True, 'content': message_content,
        }), 200
    if result.get('error'):
        return jsonify({'error': result['error']}), 500

    # Assign conversation to the user who is responding
    if current_user.is_authenticated and conversation.user_id is None:
        conversation.user_id = current_user.id
        db.session.commit()

    # Store correction if host edited an AI draft
    original_ai_content = data.get('original_ai_content')
    if original_ai_content:
        _store_correction_if_needed(original_ai_content, message_content, conversation)

    return jsonify({
        'success': True,
        'message_id': result.get('message_id'),
        'content': message_content
    })


# ============================================================================
# KNOWLEDGE BASE API ROUTES
# ============================================================================

def _normalize_kb_label(label):
    """Fold a knowledge label to its comparison form.

    Python, not SQL: SQLite's LOWER() is ASCII-only, so it would treat
    'Gaestekarte' and 'gaestekarte' as different once umlauts are involved.
    """
    return ' '.join((label or '').split()).casefold().rstrip('.,;:!?')


def _find_duplicate_knowledge(category, label, property_id, street, exclude_id=None):
    """An existing entry with the same normalised label in the same scope, or None.

    Scope is (category, property_id, street) matched exactly — the same fact
    stored globally and for one room are deliberately different entries.
    """
    target = _normalize_kb_label(label)
    if not target:
        return None
    candidates = KnowledgeEntry.query.filter_by(
        category=category, property_id=property_id, street=street
    ).all()
    for entry in candidates:
        if exclude_id is not None and entry.id == exclude_id:
            continue
        if _normalize_kb_label(entry.label) == target:
            return entry
    return None


def _resolve_kb_scope(conversation, scope):
    """(property_id, street, error_response) for a save scope picked in the chat.

    'room' → this apartment, 'street' → every room on its street, 'general' → all.
    """
    prop = Property.query.get(conversation.property_id) if conversation and conversation.property_id else None
    if scope == 'room':
        if not prop:
            return None, None, (jsonify({'error': 'Kein Zimmer für diese Unterhaltung — nur "Allgemein" möglich.'}), 400)
        return prop.id, None, None
    if scope == 'street':
        if not prop or not prop.street:
            return None, None, (jsonify({'error': 'Keine Straße für dieses Zimmer bekannt.'}), 400)
        return None, prop.street, None
    if scope == 'general':
        return None, None, None
    return None, None, (jsonify({'error': f'Invalid scope: {scope}'}), 400)


@chatbot_bp.route('/api/messages/<int:message_id>/save-example', methods=['POST'])
@login_required
def api_save_reply_example(message_id):
    """Save a host reply + the guest message it answered as a style example.

    Stored as a `correction` entry so it rides along in the reply prompt that
    already loads them — no new category, no new plumbing. The FRAGE:/ANTWORT:
    shape is what AIService._format_corrections renders as an example pair.
    """
    message = Message.query.get_or_404(message_id)
    if message.sender_type == 'guest':
        return jsonify({'error': 'Nur eigene Antworten können als Beispiel gespeichert werden.'}), 400

    conversation = Conversation.query.get(message.conversation_id)

    # The guest message this reply answered: the last guest message before it.
    # Ordered by sent_at with id as tiebreaker — Smoobu imports land out of order.
    guest_msg = (Message.query
                 .filter_by(conversation_id=message.conversation_id, sender_type='guest')
                 .filter(Message.sent_at <= message.sent_at)
                 .filter(Message.id != message.id)
                 .order_by(Message.sent_at.desc(), Message.id.desc())
                 .first())
    if not guest_msg:
        return jsonify({'error': 'Keine Gästenachricht davor gefunden.'}), 400

    ai = get_ai_service()
    clean = ai._strip_html if ai else (lambda t: t)
    question = (clean(guest_msg.content) or '').strip()
    answer = (clean(message.content) or '').strip()
    if not question or not answer:
        return jsonify({'error': 'Nachricht ist leer.'}), 400

    data = request.get_json(silent=True) or {}
    property_id, street, error = _resolve_kb_scope(conversation, data.get('scope', 'room'))
    if error:
        return error

    label = question[:60] + ('…' if len(question) > 60 else '')
    value = f'FRAGE: {question[:600]}\nANTWORT: {answer[:600]}'

    existing = _find_duplicate_knowledge('correction', label, property_id, street)
    if existing:
        if existing.value == value:
            return jsonify({'saved': 0, 'message': 'Dieses Beispiel ist bereits gespeichert.'}), 200
        # Different pair, similar opening line — keep both, disambiguate the label.
        label = f'{label[:50]} #{message_id}'

    entry = KnowledgeEntry(
        property_id=property_id,
        street=street,
        category='correction',
        label=label,
        value=value,
        source='manual',
    )
    db.session.add(entry)
    db.session.commit()
    logger.info(f"[EXAMPLE] Saved reply example {entry.id} from message {message_id} "
                f"(property_id={property_id}, street={street})")
    return jsonify({'saved': 1, 'entry': entry.to_dict()}), 201


@chatbot_bp.route('/api/knowledge')
def api_list_knowledge():
    """List knowledge entries with optional property filter"""
    property_filter = request.args.get('property_id')

    query = KnowledgeEntry.query

    if property_filter == 'global':
        query = query.filter_by(property_id=None)
    elif property_filter:
        try:
            pid = int(property_filter)
            query = query.filter_by(property_id=pid)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid property_id'}), 400

    entries = query.order_by(KnowledgeEntry.category, KnowledgeEntry.sort_order).all()
    return jsonify([e.to_dict() for e in entries])


@chatbot_bp.route('/api/messages/<int:message_id>/extract-knowledge', methods=['POST'])
@login_required
def api_extract_knowledge_from_message(message_id):
    """Use AI to extract knowledge from an owner/AI message and save to KB."""
    message = Message.query.get_or_404(message_id)

    if message.sender_type == 'guest':
        return jsonify({'error': 'Only owner/AI messages supported'}), 400

    ai_service = get_ai_service()
    if not ai_service:
        return jsonify({'error': 'AI service not available'}), 503

    entries = ai_service.extract_knowledge_from_message(message.content)
    if entries is None:
        return jsonify({'error': 'AI extraction failed'}), 500
    if not entries:
        return jsonify({'saved': 0, 'skipped': 0, 'entries': [], 'message': 'No useful knowledge found in this message'}), 200

    # Resolve scope: room (default) | street | general
    data = request.get_json(silent=True) or {}
    scope = data.get('scope', 'room')
    internal = bool(data.get('is_internal'))
    conversation = Conversation.query.get(message.conversation_id)
    target_property_id, target_street, error = _resolve_kb_scope(conversation, scope)
    if error:
        return error

    saved = []
    skipped = 0
    # Deliberate guard, not redundant with autoflush: SQLAlchemy autoflush would
    # already surface entry n as a "duplicate" for entry n+1 via _find_duplicate_knowledge,
    # but within-batch dedup must not silently depend on that flush timing.
    batch_seen = set()
    for entry in entries:
        scope_key = (entry['category'], _normalize_kb_label(entry['label']))
        if scope_key in batch_seen or _find_duplicate_knowledge(
                entry['category'], entry['label'], target_property_id, target_street):
            skipped += 1
            continue
        batch_seen.add(scope_key)
        ke = KnowledgeEntry(
            property_id=target_property_id,
            street=target_street,
            category=entry['category'],
            label=entry['label'],
            value=entry['value'],
            source='ai',
            # Applies to the whole batch: one message yields several entries and
            # the team judges the message, not each extracted fact.
            is_internal=internal,
        )
        db.session.add(ke)
        saved.append(entry)
    db.session.commit()

    return jsonify({'saved': len(saved), 'skipped': skipped, 'entries': saved}), 201


@chatbot_bp.route('/api/knowledge', methods=['POST'])
@login_required
def api_create_knowledge():
    """Create a knowledge entry"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    category = data.get('category', '').strip()
    label = data.get('label', '').strip()
    value = data.get('value', '').strip()
    property_id = data.get('property_id')

    # Validation
    if category not in KnowledgeEntry.VALID_CATEGORIES:
        return jsonify({'error': f'Invalid category. Must be one of: {", ".join(KnowledgeEntry.VALID_CATEGORIES)}'}), 400
    if not label:
        return jsonify({'error': 'Label is required'}), 400
    if len(label) > 200:
        return jsonify({'error': 'Label must be 200 characters or less'}), 400
    # Escalation topics are category + label + trigger words; the note is
    # optional. Every other category still needs its information text.
    if not value and not category.startswith('esc'):
        return jsonify({'error': 'Value is required'}), 400
    if len(value) > 2000:
        return jsonify({'error': 'Value must be 2000 characters or less'}), 400

    trigger_words = (data.get('trigger_words') or '').strip()
    if len(trigger_words) > 2000:
        return jsonify({'error': 'Trigger words must be 2000 characters or less'}), 400

    if property_id is not None:
        prop = Property.query.get(property_id)
        if not prop:
            return jsonify({'error': 'Property not found'}), 400

    # The form has no street field, so manual entries are always street=None.
    duplicate = _find_duplicate_knowledge(category, label, property_id, None)
    if duplicate:
        return jsonify({
            'error': f'Es gibt bereits einen Eintrag "{duplicate.label}" in dieser Kategorie.',
            'existing': {
                'id': duplicate.id,
                'label': duplicate.label,
                'value': duplicate.value,
                'source': duplicate.source,
            },
        }), 409

    # Auto-increment sort_order
    max_order = db.session.query(db.func.max(KnowledgeEntry.sort_order)).filter_by(
        property_id=property_id, category=category
    ).scalar() or 0

    entry = KnowledgeEntry(
        property_id=property_id,
        category=category,
        label=label,
        value=value,
        trigger_words=trigger_words or None,
        is_internal=bool(data.get('is_internal')),
        sort_order=max_order + 1
    )
    db.session.add(entry)
    db.session.commit()

    return jsonify(entry.to_dict()), 201


@chatbot_bp.route('/api/knowledge/<int:entry_id>', methods=['PUT'])
@login_required
def api_update_knowledge(entry_id):
    """Update a knowledge entry"""
    entry = KnowledgeEntry.query.get_or_404(entry_id)
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Validate every incoming field into locals first, without touching
    # `entry`, so a rejected update (incl. the duplicate check below) leaves
    # the row untouched.
    category = entry.category
    if 'category' in data:
        category = data['category'].strip()
        if category not in KnowledgeEntry.VALID_CATEGORIES:
            return jsonify({'error': 'Invalid category'}), 400

    if 'label' in data:
        label = data['label'].strip()
        if not label:
            return jsonify({'error': 'Label is required'}), 400
        if len(label) > 200:
            return jsonify({'error': 'Label must be 200 characters or less'}), 400
    else:
        label = entry.label

    if 'value' in data:
        value = data['value'].strip()
        if not value and not category.startswith('esc'):
            return jsonify({'error': 'Value is required'}), 400
        if len(value) > 2000:
            return jsonify({'error': 'Value must be 2000 characters or less'}), 400

    if 'trigger_words' in data:
        trigger_words = (data['trigger_words'] or '').strip()
        if len(trigger_words) > 2000:
            return jsonify({'error': 'Trigger words must be 2000 characters or less'}), 400

    property_id = entry.property_id
    if 'property_id' in data:
        pid = data['property_id']
        if pid is not None:
            prop = Property.query.get(pid)
            if not prop:
                return jsonify({'error': 'Property not found'}), 400
        property_id = pid

    if 'sort_order' in data:
        try:
            so = int(data['sort_order'])
        except (TypeError, ValueError):
            return jsonify({'error': 'sort_order must be an integer'}), 400
        if so < 0 or so > 10000:
            return jsonify({'error': 'sort_order must be between 0 and 10000'}), 400

    # Renaming/moving an entry onto an existing (category, label, property)
    # is a duplicate too. Use the incoming category/property_id (may differ
    # from entry's) so a category or property move can't slip past. Only
    # check when scope actually changed — legacy duplicate pairs (pre-dating
    # this guard) must stay editable for fields like `value`, or every edit
    # to either twin 409s forever.
    new_scope = (category, _normalize_kb_label(label), property_id, entry.street)
    old_scope = (entry.category, _normalize_kb_label(entry.label), entry.property_id, entry.street)
    if new_scope != old_scope:
        duplicate = _find_duplicate_knowledge(category, label, property_id,
                                              entry.street, exclude_id=entry.id)
        if duplicate:
            return jsonify({
                'error': f'Es gibt bereits einen Eintrag "{duplicate.label}" in dieser Kategorie.',
                'existing': {
                    'id': duplicate.id,
                    'label': duplicate.label,
                    'value': duplicate.value,
                    'source': duplicate.source,
                },
            }), 409

    if 'category' in data:
        entry.category = category
    if 'label' in data:
        entry.label = label
    if 'value' in data:
        entry.value = value
    if 'trigger_words' in data:
        entry.trigger_words = trigger_words or None
    if 'property_id' in data:
        entry.property_id = pid
    if 'sort_order' in data:
        entry.sort_order = so
    if 'is_internal' in data:
        entry.is_internal = bool(data['is_internal'])

    db.session.commit()
    return jsonify(entry.to_dict())


@chatbot_bp.route('/api/knowledge/<int:entry_id>', methods=['DELETE'])
@login_required
def api_delete_knowledge(entry_id):
    """Delete a knowledge entry"""
    entry = KnowledgeEntry.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    return jsonify({'success': True})


@chatbot_bp.route('/api/problem-reports', methods=['POST'])
@login_required
def api_create_problem_report():
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    category = (data.get('category') or '').strip()
    if not message:
        return jsonify({'error': 'message required'}), 400
    if category not in ProblemReport.CATEGORIES:
        return jsonify({'error': 'invalid category'}), 400
    conv_id = data.get('conversation_id')
    report = ProblemReport(
        user_id=current_user.id,
        category=category,
        message=message,
        conversation_id=int(conv_id) if conv_id else None,
        page_url=(data.get('page_url') or None),
    )
    db.session.add(report)
    db.session.commit()
    return jsonify({'id': report.id}), 201


@chatbot_bp.route('/api/problem-reports/pending-count')
@login_required
def api_problem_report_pending_count():
    count = ProblemReport.query.filter_by(status='open').count()
    return jsonify({'count': count})


@chatbot_bp.route('/problem-reports')
@admin_required
def problem_reports_page():
    reports = ProblemReport.query.order_by(
        ProblemReport.status.asc(),  # 'open' before 'resolved'
        ProblemReport.created_at.desc()).all()
    return render_template('chatbot/problem_reports.html', reports=reports)


@chatbot_bp.route('/api/problem-reports/<int:report_id>/resolve', methods=['POST'])
@admin_required
def api_resolve_problem_report(report_id):
    report = ProblemReport.query.get_or_404(report_id)
    if report.status == 'open':
        report.status = 'resolved'
        report.resolved_at = datetime.utcnow()
        report.resolved_by = current_user.id
    else:
        report.status = 'open'
        report.resolved_at = None
        report.resolved_by = None
    db.session.commit()
    return jsonify({'status': report.status})


@chatbot_bp.route('/api/email-reconcile/flush-all', methods=['POST'])
@admin_required
def email_reconcile_flush_all():
    """File all pending email candidates (>= configured floor) into their matched
    chats at once, without manual confirmation."""
    from .services.email_reconcile import promote_all_email_candidates, get_reconcile_config
    threshold = get_reconcile_config()['threshold']
    result = promote_all_email_candidates(threshold)
    return jsonify({'success': True, **result})


@chatbot_bp.route('/api/email-reconcile/undo-flush', methods=['POST'])
@admin_required
def email_reconcile_undo_flush():
    """Remove the messages inserted by the last flush and restore their candidates."""
    from .services.email_reconcile import undo_last_flush
    removed = undo_last_flush()
    return jsonify({'success': True, 'removed': removed})


@chatbot_bp.route('/api/email-reconcile/pending-count')
@login_required
def email_reconcile_pending_count():
    """Count pending candidates at/above the configured floor that have a chat to
    file into (what the flush button would insert)."""
    from .services.email_reconcile import get_reconcile_config
    threshold = get_reconcile_config()['threshold']
    count = EmailBackfillCandidate.query.filter_by(status='pending').filter(
        EmailBackfillCandidate.confidence >= threshold,
        EmailBackfillCandidate.guessed_conversation_id.isnot(None),
    ).count()
    return jsonify({'count': count})


@chatbot_bp.route('/api/conversation/<int:conversation_id>/recover-emails', methods=['POST'])
@login_required
def conversation_recover_emails(conversation_id):
    """Find this chat's missing guest messages in Gmail, on demand.

    Two passes, because the messages can be stranded in two different places:
      1. A live Gmail search for this reservation (by Buchungsnummer when we
         have one, so it is not capped by the daemon's date window).
      2. Candidates the daemon already parsed but left pending below the
         auto-insert threshold.

    The button used to do only (2), which is why it found nothing for chats the
    daemon had never scanned. `force` bypasses the on-open throttle: a human
    clicking must never be a no-op.
    """
    from .services.email_reconcile import (promote_email_candidates,
                                           get_reconcile_config,
                                           fetch_booking_for_conversation)
    Conversation.query.get_or_404(conversation_id)
    threshold = get_reconcile_config()['threshold']

    live = 0
    from .services.gmail_service import get_gmail_service
    gmail = get_gmail_service()
    if gmail and gmail.is_authenticated():
        try:
            stats = fetch_booking_for_conversation(gmail, conversation_id, force=True)
            live = stats.get('auto_inserted', 0)
        except Exception:
            current_app.logger.exception(
                "recover-emails: live Gmail fetch failed for conv %s", conversation_id)

    promoted = len(promote_email_candidates(conversation_id, threshold))
    return jsonify({'success': True, 'inserted': live + promoted,
                    'from_gmail': live, 'from_queue': promoted})


@chatbot_bp.route('/api/conversation/<int:conversation_id>/fetch-booking-live', methods=['POST'])
@login_required
def conversation_fetch_booking_live(conversation_id):
    """Live per-chat Booking email fetch, called on chat open. Booking-only,
    throttled server-side, auto-inserts positive matches. Never raises to the
    client — a failed fetch must not block the conversation view."""
    Conversation.query.get_or_404(conversation_id)
    from .services.gmail_service import get_gmail_service
    from .services.email_reconcile import fetch_booking_for_conversation
    gmail = get_gmail_service()
    if not gmail or not gmail.is_authenticated():
        return jsonify({'success': True, 'inserted': 0, 'reason': 'gmail_disconnected'})
    try:
        stats = fetch_booking_for_conversation(gmail, conversation_id)
    except Exception:
        current_app.logger.exception(
            "fetch-booking-live failed for conv %s", conversation_id)
        return jsonify({'success': True, 'inserted': 0, 'reason': 'error'})
    return jsonify({'success': True, 'inserted': stats.get('auto_inserted', 0),
                    'reason': stats.get('reason')})


@chatbot_bp.route('/api/conversation/<int:conversation_id>/import-email-thread', methods=['POST'])
@login_required
def conversation_import_email_thread(conversation_id: int):
    """Backfill an existing conversation from the guest's two-sided Gmail thread."""
    from .services.email_thread_backfill import backfill_conversation_from_email
    from .services.gmail_service import get_gmail_service
    Conversation.query.get_or_404(conversation_id)
    gmail = get_gmail_service()
    if not gmail or not gmail.is_authenticated():
        return jsonify({'success': False, 'error': 'Gmail not connected'}), 503
    payload = request.get_json(silent=True) or {}
    res = backfill_conversation_from_email(
        gmail, conversation_id,
        allow_name_fallback=bool(payload.get('allow_name_fallback')),
        confirm_thread_id=payload.get('confirm_thread_id'),
    )
    return jsonify({'success': True, 'inserted': res['inserted'],
                    'skipped_dupes': res['skipped_dupes'],
                    'skipped_unauth': res['skipped_unauth'],
                    'candidates': res['candidates']})


@chatbot_bp.route('/debug/prompt-compare')
@admin_required
def debug_prompt_compare():
    """Render compact and rich guest-reply prompts side-by-side for a conversation."""
    import os
    from .services.prompt_tier import detect_tier

    conversation_id = request.args.get('conversation_id', type=int)
    if not conversation_id:
        return jsonify({'error': 'Missing conversation_id query param'}), 400

    conversation = Conversation.query.get(conversation_id)
    if not conversation:
        return jsonify({'error': f'Conversation {conversation_id} not found'}), 404

    ai = get_ai_service()
    if not ai:
        return jsonify({'error': 'AI service not initialized'}), 500

    guest = conversation.guest
    guest_profile = {
        'name': guest.name if guest else 'guest',
        'language': getattr(guest, 'language', None) if guest else None,
    }

    msgs = (
        Message.query
        .filter_by(conversation_id=conversation_id)
        .order_by(Message.timestamp.asc())
        .limit(20)
        .all()
    )
    history = [{'sender_type': m.sender_type, 'content': m.content} for m in msgs]
    last_guest_msg = next(
        (m['content'] for m in reversed(history) if m['sender_type'] == 'guest'),
        '',
    )

    kwargs = dict(
        guest_profile=guest_profile,
        conversation_history=history,
        clean_latest=last_guest_msg,
        unanswered_count=1,
        tone='friendly_professional',
        host_instructions=None,
        reservation_info=None,
        knowledge_entries=None,
    )

    saved = os.environ.get('FORCE_PROMPT_TIER')
    try:
        os.environ['FORCE_PROMPT_TIER'] = 'compact'
        compact_prompt = ai._build_guest_reply_prompt(**kwargs)
        os.environ['FORCE_PROMPT_TIER'] = 'rich'
        rich_prompt = ai._build_guest_reply_prompt(**kwargs)
    finally:
        if saved is None:
            os.environ.pop('FORCE_PROMPT_TIER', None)
        else:
            os.environ['FORCE_PROMPT_TIER'] = saved

    return jsonify({
        'conversation_id': conversation_id,
        'detected_tier_for_current_model': detect_tier(ai.model),
        'current_model': ai.model,
        'compact_prompt': compact_prompt,
        'rich_prompt': rich_prompt,
        'compact_token_estimate': len(compact_prompt) // 4,
        'rich_token_estimate': len(rich_prompt) // 4,
    })
