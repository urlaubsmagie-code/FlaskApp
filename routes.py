"""
Routes for ChatBotAI
Defines all URL endpoints for the messaging system
"""

import difflib
import logging
import threading

from flask import render_template, request, jsonify, redirect, url_for, current_app
from flask_login import login_user, logout_user, current_user
from datetime import datetime
from sqlalchemy import case as sa_case
from sqlalchemy.orm import joinedload

from . import chatbot_bp

logger = logging.getLogger(__name__)
from .models import db, User, Guest, GuestDetail, Conversation, Message, Property, AISettings, ReplyTemplate, KnowledgeEntry, preload_last_messages, preload_unread_counts
from .services.ai_service import get_ai_service
from .services.memory_service import get_memory_service


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
        or request.endpoint in ('chatbot.login', 'chatbot.setup', 'chatbot.service_worker')
        or (request.endpoint and request.endpoint.startswith('chatbot.webhook_'))
        or request.endpoint == 'chatbot.health_check'
    ):
        return None

    # If not authenticated, check if setup is needed or redirect to login
    if not current_user.is_authenticated:
        # Use EXISTS for efficiency instead of COUNT (stops at first row)
        has_users = db.session.query(User.id).first() is not None
        if not has_users:
            if request.endpoint != 'chatbot.setup':
                return redirect(url_for('chatbot.setup'))
            return None
        return redirect(url_for('chatbot.login'))

    return None


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

        user = User(username=username, display_name=display_name)
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

@chatbot_bp.route('/')
def index():
    """Main inbox/dashboard view - shows first page of conversations"""
    conversations = Conversation.query.options(
        joinedload(Conversation.guest),
        joinedload(Conversation.property)
    ).order_by(Conversation.updated_at.desc()).limit(50).all()
    preload_last_messages(conversations)
    preload_unread_counts(conversations)
    return render_template('chatbot/inbox.html', conversations=conversations)


@chatbot_bp.route('/conversation/<int:conversation_id>')
def conversation_view(conversation_id):
    """Single conversation view with message thread"""
    PAGE_SIZE = 50

    conversation = Conversation.query.options(
        joinedload(Conversation.guest)
    ).get_or_404(conversation_id)

    # Count total messages for "load older" indicator
    total_messages = Message.query.filter_by(conversation_id=conversation_id).count()

    # Load only the last PAGE_SIZE messages (most recent)
    messages = Message.query.filter_by(
        conversation_id=conversation_id
    ).order_by(Message.sent_at.desc()).limit(PAGE_SIZE).all()
    messages.reverse()  # Back to chronological order for display

    has_older = total_messages > len(messages)
    guest = conversation.guest

    # Check platform connection status (only for the relevant platform)
    gmail_connected = False
    smoobu_connected = False
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

    approval_queue_enabled = AISettings.get('approval_queue_enabled', 'true') != 'false'

    return render_template(
        'chatbot/conversation.html',
        conversation=conversation,
        messages=messages,
        guest=guest,
        gmail_connected=gmail_connected,
        smoobu_connected=smoobu_connected,
        has_older=has_older,
        total_messages=total_messages,
        approval_queue_enabled=approval_queue_enabled
    )


@chatbot_bp.route('/guest/<int:guest_id>')
def guest_profile(guest_id):
    """Guest profile view showing all stored memories"""
    from sqlalchemy import func
    guest = Guest.query.get_or_404(guest_id)
    memory_service = get_memory_service()
    profile = memory_service.get_guest_profile(guest_id) if memory_service else {}
    conversations = Conversation.query.filter_by(
        guest_id=guest_id
    ).order_by(Conversation.updated_at.desc()).all()
    preload_last_messages(conversations)
    preload_unread_counts(conversations)

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
def statistics():
    """Statistics dashboard page"""
    return render_template('chatbot/statistics.html')


@chatbot_bp.route('/settings')
def settings():
    """AI settings configuration page"""
    all_settings = AISettings.query.all()
    properties = Property.query.all()
    return render_template('chatbot/settings.html', settings=all_settings, properties=properties)


@chatbot_bp.route('/knowledge')
def knowledge_base():
    """Knowledge Base management page"""
    properties = Property.query.order_by(Property.name).all()
    return render_template('chatbot/knowledge.html', properties=properties)


@chatbot_bp.route('/debug')
def debug_page():
    """Debug dashboard — admin only (first user = admin)."""
    if not current_user.is_authenticated or current_user.id != 1:
        return redirect(url_for('chatbot.index'))
    return render_template('chatbot/debug.html')


@chatbot_bp.route('/api/debug/logs')
def api_debug_logs():
    """API: get recent log entries."""
    if not current_user.is_authenticated or current_user.id != 1:
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
    if not current_user.is_authenticated or current_user.id != 1:
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
    if not current_user.is_authenticated or current_user.id != 1:
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
# API ROUTES (JSON Responses)
# ============================================================================

@chatbot_bp.route('/api/conversations/last-updated', methods=['GET'])
def api_conversations_last_updated():
    """Lightweight check: returns the most recent updated_at and unread count.
    Used by the inbox poller to decide whether a full fetch is needed."""
    from sqlalchemy import func
    ts_result = db.session.query(func.max(Conversation.updated_at)).scalar()
    unread = db.session.query(func.count(Conversation.id)).filter(
        Conversation.is_read == False
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
        query = query.filter_by(escalated=True)

    pagination = query.order_by(Conversation.updated_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Preload last messages and unread counts in batch queries instead of N+1
    preload_last_messages(pagination.items)
    preload_unread_counts(pagination.items)

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
    for r in results:
        conv_id = r['conversation_id']
        if conv_id not in grouped:
            grouped[conv_id] = {
                'conversation_id': conv_id,
                'guest_name': r['guest_name'],
                'guest_id': r['guest_id'],
                'subject': r['subject'],
                'platform': r['platform'],
                'match_count': 0,
                'first_snippet': None
            }
        grouped[conv_id]['match_count'] += 1
        if grouped[conv_id]['first_snippet'] is None:
            grouped[conv_id]['first_snippet'] = r.get('snippet')

    return jsonify({
        'results': list(grouped.values()),
        'query': query,
        'total': len(grouped)
    })


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
            'messages': [m.to_dict() for m in messages]
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
            'has_more': has_more
        })

    # Default: return last N messages
    messages = query.order_by(Message.sent_at.desc()).limit(limit).all()
    messages.reverse()
    return jsonify({
        'conversation_id': conversation_id,
        'messages': [m.to_dict() for m in messages]
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
        # Fall back to the latest message in the conversation
        latest = conversation.messages.order_by(Message.sent_at.desc()).first()
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


@chatbot_bp.route('/api/conversations/<int:conversation_id>/messages', methods=['POST'])
def api_send_message(conversation_id):
    """Send a new message in a conversation (owner message)"""
    conversation = Conversation.query.get_or_404(conversation_id)
    data = request.get_json()

    if not data or 'content' not in data:
        return jsonify({'error': 'Content is required'}), 400

    # Create owner message
    message = Message(
        conversation_id=conversation_id,
        sender_type='owner',
        content=data['content'],
        sent_at=datetime.utcnow()
    )
    db.session.add(message)
    conversation.updated_at = datetime.utcnow()
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

        latest_guest_message = None
        for msg in reversed(messages):
            if msg.sender_type == 'guest':
                latest_guest_message = msg
                break

        if not latest_guest_message:
            return jsonify({'error': 'No guest message to respond to'}), 400

        # Check if the latest guest message is a pure acknowledgment (Ok, Gut, etc.)
        if ai_service.is_acknowledgment(latest_guest_message.content):
            logger.info(f"[AI SKIP] Acknowledgment detected in auto-response: '{latest_guest_message.content[:50]}'")
            return jsonify({'skipped': True, 'reason': 'acknowledgment',
                           'message': 'No response needed — guest acknowledged your message.'}), 200

        # Get guest profile
        profile = memory_service.get_guest_profile(conversation.guest_id) if memory_service else {}

        # Get property info if available
        property_info = conversation.property.to_dict() if conversation.property else None

        # Fetch Smoobu reservation details if applicable
        reservation_info = None
        if conversation.platform == 'smoobu' and conversation.smoobu_reservation_id:
            try:
                from .services.smoobu_service import get_smoobu_service
                smoobu = get_smoobu_service()
                if smoobu and smoobu.is_configured():
                    reservation_info = smoobu.get_reservation(conversation.smoobu_reservation_id)
            except Exception as e:
                logger.warning(f"Failed to fetch Smoobu reservation for AI response: {e}")

        # Load knowledge base entries for AI context
        knowledge_entries = []
        try:
            if conversation.property_id:
                knowledge_entries = [e.to_dict() for e in
                                    KnowledgeEntry.query.filter(
                                        db.or_(
                                            KnowledgeEntry.property_id.is_(None),
                                            KnowledgeEntry.property_id == conversation.property_id
                                        )
                                    ).order_by(KnowledgeEntry.category, KnowledgeEntry.sort_order).all()]
            else:
                knowledge_entries = [e.to_dict() for e in
                                    KnowledgeEntry.query.filter_by(property_id=None)
                                    .order_by(KnowledgeEntry.category, KnowledgeEntry.sort_order).all()]
        except Exception as e:
            logger.warning(f"Failed to load knowledge entries: {e}")

        # Generate AI response
        ai_response = ai_service.generate_guest_response(
            guest_profile=profile,
            conversation_history=[m.to_dict() for m in messages],
            latest_message=latest_guest_message.content,
            property_info=property_info,
            tone=tone,
            host_instructions=host_instructions,
            conversation_subject=conversation.subject,
            max_history=max_history,
            reservation_info=reservation_info,
            knowledge_entries=knowledge_entries
        )

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
        conversation.updated_at = datetime.utcnow()
        db.session.commit()

        # Check if approval queue is enabled
        # Manual button ALWAYS creates a pending draft when queue is enabled
        approval_queue_enabled = AISettings.get('approval_queue_enabled', 'true') == 'true'

        if approval_queue_enabled:
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
                    from .services.smoobu_service import get_smoobu_service
                    smoobu = get_smoobu_service()
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

    try:
        # Read AI settings from DB
        tone = AISettings.get('ai_response_tone', 'friendly_professional')
        host_instructions = AISettings.get('host_instructions', '')
        max_history = int(AISettings.get('max_conversation_history', '10'))

        # Get conversation context
        messages = conversation.messages.order_by(Message.sent_at.desc()).limit(max_history).all()
        messages.reverse()

        if not messages:
            return jsonify({'error': 'No messages in conversation'}), 400

        latest_guest_message = None
        for msg in reversed(messages):
            if msg.sender_type == 'guest':
                latest_guest_message = msg
                break

        if not latest_guest_message:
            return jsonify({'error': 'No guest message to respond to'}), 400

        # Check if the latest guest message is a pure acknowledgment (Ok, Gut, etc.)
        if ai_service.is_acknowledgment(latest_guest_message.content):
            logger.info(f"[AI SKIP] Acknowledgment detected: '{latest_guest_message.content[:50]}' — no response needed")
            result = {'suggestion': None, 'skipped': True, 'reason': 'acknowledgment'}
            if include_debug:
                result['debug_context'] = {
                    'latest_guest_message': latest_guest_message.content,
                    'skip_reason': 'Message is a pure acknowledgment (e.g. Ok, Gut, Alright) — no response needed',
                }
            return jsonify(result)

        # Get guest profile
        profile = memory_service.get_guest_profile(conversation.guest_id) if memory_service else {}

        # Get property info if available
        property_info = conversation.property.to_dict() if conversation.property else None

        # Fetch Smoobu reservation details if applicable
        reservation_info = None
        if conversation.platform == 'smoobu' and conversation.smoobu_reservation_id:
            try:
                from .services.smoobu_service import get_smoobu_service
                smoobu = get_smoobu_service()
                if smoobu and smoobu.is_configured():
                    reservation_info = smoobu.get_reservation(conversation.smoobu_reservation_id)
            except Exception as e:
                logger.warning(f"Failed to fetch Smoobu reservation for AI suggest: {e}")

        # Load knowledge base entries for AI context
        knowledge_entries = []
        try:
            if conversation.property_id:
                knowledge_entries = [e.to_dict() for e in
                                    KnowledgeEntry.query.filter(
                                        db.or_(
                                            KnowledgeEntry.property_id.is_(None),
                                            KnowledgeEntry.property_id == conversation.property_id
                                        )
                                    ).order_by(KnowledgeEntry.category, KnowledgeEntry.sort_order).all()]
            else:
                knowledge_entries = [e.to_dict() for e in
                                    KnowledgeEntry.query.filter_by(property_id=None)
                                    .order_by(KnowledgeEntry.category, KnowledgeEntry.sort_order).all()]
        except Exception as e:
            logger.warning(f"Failed to load knowledge entries: {e}")

        # Generate AI response (but don't save it)
        ai_response = ai_service.generate_guest_response(
            guest_profile=profile,
            conversation_history=[m.to_dict() for m in messages],
            latest_message=latest_guest_message.content,
            property_info=property_info,
            tone=tone,
            host_instructions=host_instructions,
            conversation_subject=conversation.subject,
            max_history=max_history,
            reservation_info=reservation_info,
            knowledge_entries=knowledge_entries
        )

        if not ai_response:
            return jsonify({'error': 'AI response timed out. The model may be loading - try again.'}), 504

        # Build response
        result = {'suggestion': ai_response}

        # Include debug context if requested (shows what the AI received)
        if include_debug:
            result['debug_context'] = {
                'latest_guest_message': latest_guest_message.content,
                'messages_count': len(messages),
                'messages_used': [
                    {'sender': m.sender_type, 'preview': m.content[:100]} for m in messages
                ],
                'guest_profile': profile if profile else None,
                'property': property_info.get('name') if property_info else None,
                'reservation': bool(reservation_info),
                'tone': tone,
                'has_host_instructions': bool(host_instructions and host_instructions.strip()),
                'conversation_subject': conversation.subject,
            }

        return jsonify(result)

    except MemoryError:
        logger.error("MemoryError during AI suggestion - model may be too large")
        return jsonify({'error': 'Out of memory. Try a smaller model in Settings.'}), 503
    except Exception as e:
        logger.error(f"Unexpected error generating AI suggestion: {e}", exc_info=True)
        return jsonify({'error': f'AI suggestion failed: {str(e)}'}), 500


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
def api_get_settings():
    """Get all AI settings"""
    settings = AISettings.query.all()
    return jsonify({s.key: s.value for s in settings})


@chatbot_bp.route('/api/settings', methods=['PUT'])
def api_update_settings():
    """Update AI settings"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    for key, value in data.items():
        AISettings.set(key, str(value))

    return jsonify({'success': True})


@chatbot_bp.route('/api/ollama/models', methods=['GET'])
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

    return jsonify({
        'current_model': current_model,
        'installed': installed,
        'suggested': suggested
    })


@chatbot_bp.route('/api/settings/model', methods=['PUT'])
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
def api_get_email_filter():
    """Get email filter settings"""
    from .services.gmail_service import get_gmail_service
    gmail = get_gmail_service()
    return jsonify(gmail.get_filter_settings())


@chatbot_bp.route('/api/settings/email-filter', methods=['PUT'])
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
# USER MANAGEMENT API
# ============================================================================

@chatbot_bp.route('/api/users', methods=['GET'])
def api_get_users():
    """Get all users"""
    users = User.query.order_by(User.username).all()
    return jsonify({'users': [u.to_dict() for u in users]})


@chatbot_bp.route('/api/users', methods=['POST'])
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


@chatbot_bp.route('/api/users/<int:user_id>/password', methods=['PUT'])
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
def api_toggle_auto_respond(conversation_id):
    """Toggle automatic AI responses for a conversation"""
    conversation = Conversation.query.get_or_404(conversation_id)

    if not conversation.ai_enabled:
        return jsonify({'error': 'AI must be enabled first'}), 400

    conversation.auto_respond = not conversation.auto_respond
    db.session.commit()
    return jsonify({'auto_respond': conversation.auto_respond})


@chatbot_bp.route('/api/conversations/<int:conversation_id>/resolve', methods=['POST'])
def api_resolve_escalation(conversation_id):
    """Resolve an escalated conversation. Does NOT re-enable auto-respond."""
    conversation = Conversation.query.get_or_404(conversation_id)

    conversation.escalated = False
    conversation.escalated_at = None
    db.session.commit()

    return jsonify({
        'success': True,
        'escalated': conversation.escalated,
        'auto_respond': conversation.auto_respond
    })


@chatbot_bp.route('/api/messages/<int:message_id>/approve', methods=['POST'])
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
            from .services.smoobu_service import get_smoobu_service
            smoobu = get_smoobu_service()
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

@chatbot_bp.route('/api/stats', methods=['GET'])
def api_get_stats():
    """Get dashboard statistics — combines counts into fewer queries"""
    from sqlalchemy import func

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # Single query for conversation counts
    conv_stats = db.session.query(
        func.count(Conversation.id).label('total'),
        func.sum(sa_case(
            (Conversation.is_read == False, 1), else_=0
        )).label('unread'),
        func.count(func.distinct(sa_case(
            (Conversation.status == 'active', Conversation.guest_id), else_=None
        ))).label('active_guests')
    ).first()

    messages_today = Message.query.filter(Message.sent_at >= today).count()
    total_guests = Guest.query.count()

    return jsonify({
        'total_conversations': conv_stats.total,
        'unread_count': int(conv_stats.unread or 0),
        'messages_today': messages_today,
        'active_guests': int(conv_stats.active_guests or 0),
        'total_guests': total_guests
    })


@chatbot_bp.route('/api/stats/detailed', methods=['GET'])
def api_get_detailed_stats():
    """Get team performance statistics for the statistics dashboard"""
    from sqlalchemy import func
    from datetime import timedelta

    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # --- Team totals (overview) ---
    total_conversations = Conversation.query.count()
    conversations_week = Conversation.query.filter(Conversation.created_at >= week_ago).count()
    total_owner_messages = Message.query.filter_by(sender_type='owner').count()
    owner_messages_week = Message.query.filter(
        Message.sender_type == 'owner',
        Message.sent_at >= week_ago
    ).count()
    total_guests = Guest.query.count()
    avg_response = _compute_avg_response_time()

    overview = {
        'total_conversations': total_conversations,
        'conversations_this_week': conversations_week,
        'total_owner_messages': total_owner_messages,
        'owner_messages_this_week': owner_messages_week,
        'total_guests': total_guests,
        'avg_response_minutes': avg_response,
    }

    # --- Per-user detailed stats (batched queries to avoid N+1) ---
    users = User.query.all()
    user_ids = [u.id for u in users]
    weekday_names = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

    # Batch: assigned conversation counts per user (total and active) — 1 query
    conv_counts = db.session.query(
        Conversation.user_id,
        func.count(Conversation.id).label('total'),
        func.sum(sa_case((Conversation.status == 'active', 1), else_=0)).label('active')
    ).filter(Conversation.user_id.in_(user_ids)).group_by(Conversation.user_id).all()
    conv_map = {r.user_id: {'total': r.total, 'active': r.active} for r in conv_counts}

    # Batch: owner message counts per user (total, week, month) — 1 query
    msg_counts = db.session.query(
        Conversation.user_id,
        func.count(Message.id).label('total'),
        func.sum(sa_case((Message.sent_at >= week_ago, 1), else_=0)).label('week'),
        func.sum(sa_case((Message.sent_at >= month_ago, 1), else_=0)).label('month')
    ).join(Conversation, Message.conversation_id == Conversation.id).filter(
        Conversation.user_id.in_(user_ids),
        Message.sender_type == 'owner'
    ).group_by(Conversation.user_id).all()
    msg_map = {r.user_id: {'total': r.total, 'week': r.week, 'month': r.month} for r in msg_counts}

    # Batch: last activity per user — 1 query
    last_activity_q = db.session.query(
        Conversation.user_id,
        func.max(Message.sent_at).label('last_at')
    ).join(Conversation, Message.conversation_id == Conversation.id).filter(
        Conversation.user_id.in_(user_ids),
        Message.sender_type == 'owner'
    ).group_by(Conversation.user_id).all()
    last_activity_map = {r.user_id: r.last_at for r in last_activity_q}

    # Batch: daily breakdown for all users (last 7 days) — 1 query
    week_start = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    daily_counts = db.session.query(
        Conversation.user_id,
        func.date(Message.sent_at).label('day'),
        func.count(Message.id).label('count')
    ).join(Conversation, Message.conversation_id == Conversation.id).filter(
        Conversation.user_id.in_(user_ids),
        Message.sender_type == 'owner',
        Message.sent_at >= week_start
    ).group_by(Conversation.user_id, func.date(Message.sent_at)).all()

    # Build daily map: {user_id: {date_str: count}}
    daily_map = {}
    for r in daily_counts:
        if r.user_id not in daily_map:
            daily_map[r.user_id] = {}
        day_str = str(r.day)
        daily_map[r.user_id][day_str] = r.count

    team = []
    for user in users:
        uid = user.id
        conv_data = conv_map.get(uid, {'total': 0, 'active': 0})
        msg_data = msg_map.get(uid, {'total': 0, 'week': 0, 'month': 0})
        last_at = last_activity_map.get(uid)
        user_daily = daily_map.get(uid, {})

        # Per-user avg response time (kept as separate query — complex logic)
        user_avg_response = _compute_avg_response_time_for_user(uid)

        # Build daily breakdown
        daily = []
        for i in range(6, -1, -1):
            day = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_str = day.strftime('%Y-%m-%d')
            daily.append({
                'date': day_str,
                'weekday': weekday_names[day.weekday()],
                'count': user_daily.get(day_str, 0),
            })

        team.append({
            'user_id': uid,
            'display_name': user.display_name,
            'assigned_total': conv_data['total'],
            'assigned_active': int(conv_data['active'] or 0),
            'messages_total': msg_data['total'],
            'messages_week': int(msg_data['week'] or 0),
            'messages_month': int(msg_data['month'] or 0),
            'avg_response_minutes': user_avg_response,
            'last_activity': last_at.isoformat() if last_at else None,
            'daily': daily,
        })

    # Sort by messages this week descending (most active first)
    team.sort(key=lambda u: u['messages_week'], reverse=True)

    return jsonify({
        'overview': overview,
        'team': team,
    })


def _compute_avg_response_time():
    """Compute average response time (in minutes) from last 50 active conversations.
    Finds guest message → next owner/ai reply pairs and averages the deltas.
    Caps individual deltas at 24h to exclude outliers."""
    return _compute_avg_response_time_for_user(None)


def _compute_avg_response_time_for_user(user_id):
    """Compute average response time for a specific user's conversations,
    or all conversations if user_id is None.
    Uses a single query to fetch all messages for the batch of conversations."""
    from datetime import timedelta

    query = Conversation.query.filter_by(status='active')
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    conversations = query.order_by(Conversation.updated_at.desc()).limit(50).all()

    if not conversations:
        return None

    # Fetch all messages for these conversations in ONE query
    conv_ids = [c.id for c in conversations]
    all_messages = Message.query.filter(
        Message.conversation_id.in_(conv_ids)
    ).order_by(Message.conversation_id, Message.sent_at.asc()).all()

    # Group messages by conversation
    from collections import defaultdict
    msgs_by_conv = defaultdict(list)
    for msg in all_messages:
        msgs_by_conv[msg.conversation_id].append(msg)

    deltas = []
    max_delta = timedelta(hours=24)

    for conv_id, messages in msgs_by_conv.items():
        for i, msg in enumerate(messages):
            if msg.sender_type == 'guest':
                for j in range(i + 1, len(messages)):
                    if messages[j].sender_type in ('owner', 'ai'):
                        delta = messages[j].sent_at - msg.sent_at
                        if timedelta(0) < delta <= max_delta:
                            deltas.append(delta.total_seconds() / 60.0)
                        break

    if not deltas:
        return None
    return round(sum(deltas) / len(deltas), 1)


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


@chatbot_bp.route('/api/push/vapid-key', methods=['GET'])
def api_push_vapid_key():
    """Return the VAPID public key for the frontend"""
    from .services.push_service import get_push_service
    push = get_push_service()
    if not push:
        return jsonify({'error': 'Push service not available'}), 503
    return jsonify({'publicKey': push.get_public_key()})


@chatbot_bp.route('/api/push/subscribe', methods=['POST'])
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
    """Webhook endpoint for WhatsApp messages"""
    # TODO: Implement WhatsApp webhook handling
    return jsonify({'status': 'received'}), 200


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

    latest_guest_message = None
    for msg in reversed(messages):
        if msg.sender_type == 'guest':
            latest_guest_message = msg
            break

    # Read AI settings for debug display
    tone = AISettings.get('ai_response_tone', 'friendly_professional')
    host_instructions = AISettings.get('host_instructions', '')
    max_history = int(AISettings.get('max_conversation_history', '10'))

    chat_messages = []
    if ai_service and latest_guest_message:
        chat_messages = ai_service._build_chat_messages(
            guest_profile=profile,
            conversation_history=[m.to_dict() for m in messages],
            latest_message=latest_guest_message.content,
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
        auth_url, state = gmail.get_authorization_url(callback_url)

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
        auth_url, state = gmail.get_authorization_url(callback_url)
        # Store the callback URL in session so the callback route uses the same one
        from flask import session
        session['gmail_callback_url'] = callback_url
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
            redirect_uri=callback_url
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
            extract_memory=True
        )

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

@chatbot_bp.route('/smoobu/status')
def smoobu_status():
    """Get Smoobu connection status"""
    from .services.smoobu_service import get_smoobu_service
    smoobu = get_smoobu_service()
    if not smoobu:
        return jsonify({'configured': False, 'authenticated': False, 'api_key_masked': ''})
    return jsonify(smoobu.get_status())


@chatbot_bp.route('/smoobu/connect', methods=['POST'])
def smoobu_connect():
    """Save Smoobu API key and verify connection"""
    data = request.get_json()
    api_key = data.get('api_key', '').strip() if data else ''

    if not api_key:
        return jsonify({'error': 'API key is required'}), 400

    # Save to DB
    AISettings.set('smoobu_api_key', api_key, description='Smoobu API key')

    # Verify by fetching apartments
    from .services.smoobu_service import get_smoobu_service
    smoobu = get_smoobu_service()
    if smoobu and smoobu.is_authenticated():
        return jsonify({'success': True, 'message': 'Connected to Smoobu'})
    else:
        # Clear invalid key
        AISettings.set('smoobu_api_key', '', description='Smoobu API key')
        return jsonify({'error': 'Invalid API key — could not connect to Smoobu'}), 400


@chatbot_bp.route('/smoobu/disconnect', methods=['POST'])
def smoobu_disconnect():
    """Clear Smoobu API key"""
    from .services.smoobu_service import get_smoobu_service
    smoobu = get_smoobu_service()
    if smoobu:
        smoobu.disconnect()
    return jsonify({'success': True})


@chatbot_bp.route('/api/smoobu/sync', methods=['POST'])
def api_smoobu_sync():
    """Sync messages from Smoobu"""
    from .services.smoobu_service import get_smoobu_service
    smoobu = get_smoobu_service()
    if not smoobu or not smoobu.is_configured():
        return jsonify({'error': 'Smoobu not connected'}), 400

    result = smoobu.sync_messages()
    return jsonify(result)


@chatbot_bp.route('/api/smoobu/sync/<int:conversation_id>', methods=['POST'])
def api_smoobu_sync_conversation(conversation_id):
    """Sync messages for a single Smoobu conversation (lightweight)"""
    from .services.smoobu_service import get_smoobu_service
    smoobu = get_smoobu_service()
    if not smoobu or not smoobu.is_configured():
        return jsonify({'error': 'Smoobu not connected'}), 400

    conversation = Conversation.query.get_or_404(conversation_id)
    if not conversation.smoobu_reservation_id:
        return jsonify({'error': 'Not a Smoobu conversation'}), 400

    result = smoobu.sync_conversation_messages(conversation.smoobu_reservation_id)
    return jsonify(result)


@chatbot_bp.route('/api/smoobu/sync-properties', methods=['POST'])
def api_smoobu_sync_properties():
    """Sync properties from Smoobu"""
    from .services.smoobu_service import get_smoobu_service
    smoobu = get_smoobu_service()
    if not smoobu or not smoobu.is_configured():
        return jsonify({'error': 'Smoobu not connected'}), 400

    result = smoobu.sync_properties()
    return jsonify(result)


@chatbot_bp.route('/api/smoobu/fix-timestamps', methods=['POST'])
def api_smoobu_fix_timestamps():
    """One-time fix: re-fetch Smoobu messages and update sent_at timestamps."""
    from .services.smoobu_service import get_smoobu_service
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
            try:
                msg_time = dt.fromisoformat(
                    str(created_at).replace('Z', '+00:00')
                ).replace(tzinfo=None)
            except (ValueError, TypeError):
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

    # Also fix conversation.updated_at to match the latest message
    for conv in conversations:
        latest_msg = Message.query.filter_by(
            conversation_id=conv.id
        ).order_by(Message.sent_at.desc()).first()
        if latest_msg and latest_msg.sent_at:
            if not conv.updated_at or conv.updated_at != latest_msg.sent_at:
                conv.updated_at = latest_msg.sent_at
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
    from .services.smoobu_service import get_smoobu_service

    conversation = Conversation.query.get_or_404(conversation_id)
    if not conversation.smoobu_reservation_id:
        return jsonify({'error': 'No Smoobu reservation linked'}), 400

    smoobu = get_smoobu_service()
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


@chatbot_bp.route('/api/smoobu/reply/<int:conversation_id>', methods=['POST'])
def api_smoobu_reply(conversation_id):
    """Send a reply through Smoobu API"""
    from .services.smoobu_service import get_smoobu_service
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

    smoobu = get_smoobu_service()
    if not smoobu or not smoobu.is_configured():
        return jsonify({'error': 'Smoobu not connected'}), 400

    send_result = smoobu.send_message(conversation.smoobu_reservation_id, message_content)

    if send_result:
        # Try to extract message ID from Smoobu response for duplicate prevention
        smoobu_msg_id = None
        if isinstance(send_result, dict):
            smoobu_msg_id = str(send_result.get('id') or send_result.get('message_id')
                               or send_result.get('messageId') or '')
        platform_msg_id = (f"smoobu-{conversation.smoobu_reservation_id}-{smoobu_msg_id}"
                           if smoobu_msg_id else None)

        # Store as owner message
        router = get_message_router()
        owner_result = router.process_owner_message(
            conversation_id=conversation_id,
            content=message_content,
            extract_memory=True,
            platform_message_id=platform_msg_id
        )

        # Store correction if host edited an AI draft
        original_ai_content = data.get('original_ai_content')
        if original_ai_content:
            _store_correction_if_needed(original_ai_content, message_content, conversation)

        return jsonify({
            'success': True,
            'message_id': owner_result.get('message_id'),
            'content': message_content
        })
    else:
        return jsonify({'error': 'Failed to send message via Smoobu'}), 500


# ============================================================================
# KNOWLEDGE BASE API ROUTES
# ============================================================================

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


@chatbot_bp.route('/api/knowledge', methods=['POST'])
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
    if not value:
        return jsonify({'error': 'Value is required'}), 400
    if len(value) > 2000:
        return jsonify({'error': 'Value must be 2000 characters or less'}), 400

    if property_id is not None:
        prop = Property.query.get(property_id)
        if not prop:
            return jsonify({'error': 'Property not found'}), 400

    # Auto-increment sort_order
    max_order = db.session.query(db.func.max(KnowledgeEntry.sort_order)).filter_by(
        property_id=property_id, category=category
    ).scalar() or 0

    entry = KnowledgeEntry(
        property_id=property_id,
        category=category,
        label=label,
        value=value,
        sort_order=max_order + 1
    )
    db.session.add(entry)
    db.session.commit()

    return jsonify(entry.to_dict()), 201


@chatbot_bp.route('/api/knowledge/<int:entry_id>', methods=['PUT'])
def api_update_knowledge(entry_id):
    """Update a knowledge entry"""
    entry = KnowledgeEntry.query.get_or_404(entry_id)
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    if 'category' in data:
        category = data['category'].strip()
        if category not in KnowledgeEntry.VALID_CATEGORIES:
            return jsonify({'error': 'Invalid category'}), 400
        entry.category = category

    if 'label' in data:
        label = data['label'].strip()
        if not label:
            return jsonify({'error': 'Label is required'}), 400
        if len(label) > 200:
            return jsonify({'error': 'Label must be 200 characters or less'}), 400
        entry.label = label

    if 'value' in data:
        value = data['value'].strip()
        if not value:
            return jsonify({'error': 'Value is required'}), 400
        if len(value) > 2000:
            return jsonify({'error': 'Value must be 2000 characters or less'}), 400
        entry.value = value

    if 'property_id' in data:
        pid = data['property_id']
        if pid is not None:
            prop = Property.query.get(pid)
            if not prop:
                return jsonify({'error': 'Property not found'}), 400
        entry.property_id = pid

    if 'sort_order' in data:
        entry.sort_order = int(data['sort_order'])

    db.session.commit()
    return jsonify(entry.to_dict())


@chatbot_bp.route('/api/knowledge/<int:entry_id>', methods=['DELETE'])
def api_delete_knowledge(entry_id):
    """Delete a knowledge entry"""
    entry = KnowledgeEntry.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    return jsonify({'success': True})
