"""Team replies saved as style examples for UMI.

The team wanted UMI to copy how *they* answer, together with the guest message
being answered. Stored as a `correction` entry (FRAGE:/ANTWORT:) so it rides
the prompt path that already loads corrections.
"""

from datetime import datetime, timedelta

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, User, Property, Conversation, Message, Guest, KnowledgeEntry
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
    user = User(username='t', display_name='T', is_admin=True)
    user.set_password('pw'); db.session.add(user); db.session.commit()
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(user.id); s['_fresh'] = True
    return c


def _thread(with_property=True):
    """Guest asks twice, team answers once — returns the owner message."""
    prop = None
    if with_property:
        prop = Property(name='F3', street='Hertigswalder Str. 27'); db.session.add(prop); db.session.flush()
    guest = Guest(name='G'); db.session.add(guest); db.session.flush()
    conv = Conversation(guest_id=guest.id, platform='airbnb',
                        property_id=prop.id if prop else None)
    db.session.add(conv); db.session.flush()

    t0 = datetime(2026, 8, 27, 10, 0)
    db.session.add(Message(conversation_id=conv.id, sender_type='guest',
                           content='Wo kann ich parken?', sent_at=t0))
    db.session.add(Message(conversation_id=conv.id, sender_type='guest',
                           content='Kann ich früher einchecken?', sent_at=t0 + timedelta(minutes=5)))
    owner = Message(conversation_id=conv.id, sender_type='owner',
                    content='Klar, ab 13 Uhr geht das gerne!', sent_at=t0 + timedelta(minutes=10))
    db.session.add(owner)
    # A later guest message must NOT be picked as the question.
    db.session.add(Message(conversation_id=conv.id, sender_type='guest',
                           content='Super, danke!', sent_at=t0 + timedelta(minutes=20)))
    db.session.commit()
    return owner


def test_saves_the_guest_message_it_answered(app, client):
    owner = _thread()
    r = client.post(f'/chatbot/api/messages/{owner.id}/save-example', json={'scope': 'room'})
    assert r.status_code == 201, r.get_data(as_text=True)

    entry = KnowledgeEntry.query.filter_by(category='correction').one()
    assert entry.value == 'FRAGE: Kann ich früher einchecken?\nANTWORT: Klar, ab 13 Uhr geht das gerne!'
    assert entry.property_id is not None and entry.street is None


def test_scope_street_and_general(app, client):
    owner = _thread()
    r = client.post(f'/chatbot/api/messages/{owner.id}/save-example', json={'scope': 'street'})
    assert r.status_code == 201
    entry = KnowledgeEntry.query.filter_by(category='correction').one()
    assert entry.property_id is None and entry.street == 'Hertigswalder Str. 27'


def test_saving_twice_is_a_no_op(app, client):
    owner = _thread()
    client.post(f'/chatbot/api/messages/{owner.id}/save-example', json={'scope': 'room'})
    r = client.post(f'/chatbot/api/messages/{owner.id}/save-example', json={'scope': 'room'})
    assert r.status_code == 200 and r.get_json()['saved'] == 0
    assert KnowledgeEntry.query.filter_by(category='correction').count() == 1


def test_guest_message_cannot_be_saved(app, client):
    _thread()
    guest_msg = Message.query.filter_by(sender_type='guest').first()
    r = client.post(f'/chatbot/api/messages/{guest_msg.id}/save-example', json={'scope': 'general'})
    assert r.status_code == 400


def test_example_pair_renders_as_an_example_in_the_prompt():
    """Not as a "you got this wrong" correction — the wording is the lesson."""
    line = AIService._format_corrections([{
        'label': 'Kann ich früher einchecken?',
        'value': 'FRAGE: Kann ich früher einchecken?\nANTWORT: Klar, ab 13 Uhr geht das gerne!',
    }])
    assert 'the team answered: "Klar, ab 13 Uhr geht das gerne!"' in line
    assert "Don't say" not in line


def test_real_correction_still_renders_as_a_correction():
    line = AIService._format_corrections([{
        'label': 'Parken',
        'value': 'FALSCH: Parkplatz ist gratis\nRICHTIG: Parkplatz kostet 5€',
    }])
    assert "Don't say" in line and 'Parkplatz kostet 5€' in line
