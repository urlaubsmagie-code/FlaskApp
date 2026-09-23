import pytest
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, User, Property, Conversation, Message, Guest, KnowledgeEntry
from ChatBotAI import routes as routes_mod


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app, monkeypatch):
    # Stub the AI extractor to return one fixed entry (no Ollama).
    class FakeAI:
        def extract_knowledge_from_message(self, content):
            return [{'category': 'general', 'label': 'Müll', 'value': 'Dienstags'}]
    # routes.py does `from .services.ai_service import get_ai_service`, so the
    # name is bound directly into the routes module namespace — patch it there.
    monkeypatch.setattr(routes_mod, 'get_ai_service', lambda: FakeAI())

    user = User(username='t', display_name='T', is_admin=True)
    user.set_password('pw'); db.session.add(user); db.session.commit()
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(user.id); s['_fresh'] = True
    return c


def _make_conv(street='Hertigswalder Str. 27', with_property=True):
    prop = None
    if with_property:
        prop = Property(name='F3', street=street); db.session.add(prop); db.session.flush()
    guest = Guest(name='G'); db.session.add(guest); db.session.flush()
    conv = Conversation(guest_id=guest.id, platform='airbnb',
                        property_id=prop.id if prop else None)
    db.session.add(conv); db.session.flush()
    msg = Message(conversation_id=conv.id, sender_type='owner', content='Müll dienstags raus')
    db.session.add(msg); db.session.commit()
    return msg


def test_scope_street_saves_with_street_only(app, client):
    msg = _make_conv()
    r = client.post(f'/chatbot/api/messages/{msg.id}/extract-knowledge', json={'scope': 'street'})
    assert r.status_code == 201, r.get_data(as_text=True)
    e = KnowledgeEntry.query.filter_by(label='Müll').first()
    assert e.property_id is None and e.street == 'Hertigswalder Str. 27'


def test_scope_general_saves_global(app, client):
    msg = _make_conv()
    r = client.post(f'/chatbot/api/messages/{msg.id}/extract-knowledge', json={'scope': 'general'})
    assert r.status_code == 201
    e = KnowledgeEntry.query.filter_by(label='Müll').first()
    assert e.property_id is None and e.street is None


def test_scope_room_requires_property(app, client):
    msg = _make_conv(with_property=False)
    r = client.post(f'/chatbot/api/messages/{msg.id}/extract-knowledge', json={'scope': 'room'})
    assert r.status_code == 400


def test_scope_street_requires_property_street(app, client):
    msg = _make_conv(street=None)
    r = client.post(f'/chatbot/api/messages/{msg.id}/extract-knowledge', json={'scope': 'street'})
    assert r.status_code == 400


def test_extract_can_mark_entries_internal(app, client):
    """The 💡 button must be able to file a fact as team-only — the message it
    reads from can just as easily describe an internal procedure."""
    msg = _make_conv()
    r = client.post(f'/chatbot/api/messages/{msg.id}/extract-knowledge',
                    json={'scope': 'general', 'is_internal': True})
    assert r.status_code == 201
    assert KnowledgeEntry.query.filter_by(label='Müll').first().is_internal is True


def test_extract_defaults_to_guest_facing(app, client):
    msg = _make_conv()
    r = client.post(f'/chatbot/api/messages/{msg.id}/extract-knowledge',
                    json={'scope': 'general'})
    assert r.status_code == 201
    assert KnowledgeEntry.query.filter_by(label='Müll').first().is_internal is False
