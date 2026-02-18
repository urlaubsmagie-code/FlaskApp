"""
Routes for ChatBotAI
Defines all URL endpoints for the messaging system
"""

from flask import render_template, request, jsonify, redirect, url_for
from datetime import datetime

from . import chatbot_bp
from .models import db, Guest, GuestDetail, Conversation, Message, Property, AISettings
from .services.ai_service import get_ai_service
from .services.memory_service import get_memory_service


# ============================================================================
# PAGE ROUTES (HTML Templates)
# ============================================================================

@chatbot_bp.route('/')
def index():
    """Main inbox/dashboard view - shows all conversations"""
    conversations = Conversation.query.order_by(Conversation.updated_at.desc()).all()
    return render_template('chatbot/inbox.html', conversations=conversations)


@chatbot_bp.route('/conversation/<int:conversation_id>')
def conversation_view(conversation_id):
    """Single conversation view with message thread"""
    conversation = Conversation.query.get_or_404(conversation_id)
    messages = conversation.messages.order_by(Message.sent_at.asc()).all()
    guest = conversation.guest
    return render_template(
        'chatbot/conversation.html',
        conversation=conversation,
        messages=messages,
        guest=guest
    )


@chatbot_bp.route('/guest/<int:guest_id>')
def guest_profile(guest_id):
    """Guest profile view showing all stored memories"""
    guest = Guest.query.get_or_404(guest_id)
    memory_service = get_memory_service()
    profile = memory_service.get_guest_profile(guest_id) if memory_service else {}
    conversations = guest.conversations.order_by(Conversation.updated_at.desc()).all()
    return render_template(
        'chatbot/guest_profile.html',
        guest=guest,
        profile=profile,
        conversations=conversations
    )


@chatbot_bp.route('/settings')
def settings():
    """AI settings configuration page"""
    all_settings = AISettings.query.all()
    properties = Property.query.all()
    return render_template('chatbot/settings.html', settings=all_settings, properties=properties)


# ============================================================================
# API ROUTES (JSON Responses)
# ============================================================================

@chatbot_bp.route('/api/conversations', methods=['GET'])
def api_get_conversations():
    """Get all conversations with pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status')

    query = Conversation.query
    if status:
        query = query.filter_by(status=status)

    pagination = query.order_by(Conversation.updated_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'conversations': [c.to_dict() for c in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page
    })


@chatbot_bp.route('/api/conversations/<int:conversation_id>/messages', methods=['GET'])
def api_get_messages(conversation_id):
    """Get messages for a specific conversation"""
    conversation = Conversation.query.get_or_404(conversation_id)
    messages = conversation.messages.order_by(Message.sent_at.asc()).all()
    return jsonify({
        'conversation_id': conversation_id,
        'messages': [m.to_dict() for m in messages]
    })


@chatbot_bp.route('/api/conversations/<int:conversation_id>/read', methods=['PATCH'])
def api_mark_conversation_read(conversation_id):
    """Mark a conversation as read"""
    conversation = Conversation.query.get_or_404(conversation_id)
    conversation.is_read = True
    db.session.commit()
    return jsonify({'success': True, 'is_read': True})


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

    # Process for memory extraction
    memory_service = get_memory_service()
    if memory_service:
        memory_service.process_message_for_memory(message)

    return jsonify(message.to_dict()), 201


@chatbot_bp.route('/api/conversations/<int:conversation_id>/ai-response', methods=['POST'])
def api_generate_ai_response(conversation_id):
    """Generate an AI response for a conversation"""
    conversation = Conversation.query.get_or_404(conversation_id)

    if not conversation.ai_enabled:
        return jsonify({'error': 'AI is disabled for this conversation'}), 400

    ai_service = get_ai_service()
    memory_service = get_memory_service()

    if not ai_service:
        return jsonify({'error': 'AI service not available'}), 503

    # Get conversation context
    messages = conversation.messages.order_by(Message.sent_at.desc()).limit(10).all()
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

    # Get guest profile
    profile = memory_service.get_guest_profile(conversation.guest_id) if memory_service else {}

    # Get property info if available
    property_info = conversation.property.to_dict() if conversation.property else None

    # Generate AI response
    ai_response = ai_service.generate_guest_response(
        guest_profile=profile,
        conversation_history=[m.to_dict() for m in messages],
        latest_message=latest_guest_message.content,
        property_info=property_info
    )

    if not ai_response:
        return jsonify({'error': 'Failed to generate AI response'}), 500

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

    return jsonify(ai_message.to_dict()), 201


@chatbot_bp.route('/api/guests/<int:guest_id>', methods=['GET'])
def api_get_guest(guest_id):
    """Get guest profile with all details"""
    guest = Guest.query.get_or_404(guest_id)
    memory_service = get_memory_service()
    profile = memory_service.get_guest_profile(guest_id) if memory_service else guest.to_dict()
    return jsonify(profile)


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


@chatbot_bp.route('/api/conversations/<int:conversation_id>/toggle-ai', methods=['POST'])
def api_toggle_ai(conversation_id):
    """Toggle AI for a specific conversation"""
    conversation = Conversation.query.get_or_404(conversation_id)
    conversation.ai_enabled = not conversation.ai_enabled
    db.session.commit()
    return jsonify({'ai_enabled': conversation.ai_enabled})


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
    conversation.updated_at = datetime.utcnow()
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

    # Build callback URL
    callback_url = url_for('chatbot.gmail_callback', _external=True)

    try:
        auth_url, state = gmail.get_authorization_url(callback_url)

        # Store state in session for validation (optional security measure)
        from flask import session
        session['gmail_oauth_state'] = state

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

    callback_url = url_for('chatbot.gmail_callback', _external=True)

    try:
        auth_url, state = gmail.get_authorization_url(callback_url)
        from flask import session
        session['gmail_oauth_state'] = state
        return redirect(auth_url)
    except Exception as e:
        return render_template('chatbot/gmail_error.html', error=str(e))


@chatbot_bp.route('/gmail/callback')
def gmail_callback():
    """Handle Gmail OAuth callback"""
    from .services.gmail_service import get_gmail_service

    gmail = get_gmail_service()

    # Get the full callback URL
    authorization_response = request.url
    callback_url = url_for('chatbot.gmail_callback', _external=True)

    # Get state from session
    from flask import session
    state = session.get('gmail_oauth_state')

    success = gmail.handle_oauth_callback(
        authorization_response=authorization_response,
        redirect_uri=callback_url,
        state=state
    )

    if success:
        # Clear state
        session.pop('gmail_oauth_state', None)

        # Redirect to settings with success message
        return redirect(url_for('chatbot.settings') + '?gmail=connected')
    else:
        return render_template('chatbot/gmail_error.html',
                               error='OAuth failed. Please try again.')


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

    results = []
    for email in emails:
        # Skip emails from ourselves
        user_email = gmail.get_user_email()
        if email['sender_email'].lower() == user_email.lower():
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
        router.process_owner_message(
            conversation_id=conversation_id,
            content=message_content,
            extract_memory=True
        )

        return jsonify({
            'success': True,
            'message_id': send_result.get('id'),
            'content': message_content
        })
    else:
        return jsonify({'error': 'Failed to send email'}), 500
