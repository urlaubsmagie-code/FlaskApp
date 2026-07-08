"""The per-message suggest route must pass real context (knowledge base +
corrections) down to the AI — previously it hard-coded all of them to None,
so the lightbulb had no KB and no corrections. After unification it should
pass them like the other suggest path, while still targeting the chosen message.
"""

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Conversation, Guest, KnowledgeEntry, Message, User
from ChatBotAI.services.ai_service import AIService


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    user = User(username='tester', display_name='Tester', is_admin=True)
    user.set_password('pw')
    db.session.add(user)
    db.session.commit()
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(user.id)
        s['_fresh'] = True
    return c


@pytest.fixture
def captured(monkeypatch):
    """Capture the kwargs the route passes to generate_guest_response."""
    cap = {}

    def fake_generate(self, **kwargs):
        cap.update(kwargs)
        return 'Test reply'

    monkeypatch.setattr(AIService, 'test_connection', lambda self: True)
    monkeypatch.setattr(AIService, 'generate_guest_response', fake_generate)
    return cap


def _setup_conversation():
    guest = Guest(name='Mario', email='mario@test.local')
    db.session.add(guest)
    db.session.flush()
    conv = Conversation(guest_id=guest.id, platform='smoobu', platform_id='s-1')
    db.session.add(conv)
    db.session.flush()
    msg = Message(conversation_id=conv.id, sender_type='guest', content='Wo ist der Busbahnhof?')
    db.session.add(msg)
    # Global KB entry + a correction
    db.session.add(KnowledgeEntry(category='general', label='Check-in', value='Ab 15 Uhr', property_id=None))
    db.session.add(KnowledgeEntry(category='correction', label='Parken',
                                  value='FALSCH: kostenlos\nRICHTIG: 10€', property_id=None))
    db.session.commit()
    return conv, msg


def test_per_message_route_passes_kb_and_corrections(client, captured):
    conv, msg = _setup_conversation()
    resp = client.post(
        f'/chatbot/api/conversations/{conv.id}/ai-suggest-for-message',
        json={'message_id': msg.id},
    )
    assert resp.status_code == 200
    # KB + corrections are now passed (were hard-coded None before)
    assert captured.get('knowledge_entries')
    assert captured.get('corrections')
    # Still targets the chosen message
    assert captured.get('target_message_override') == 'Wo ist der Busbahnhof?'
