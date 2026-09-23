"""Internal-only knowledge entries must never reach the guest-reply prompt.

The Wissensdatenbank holds two kinds of rows: facts a guest may be told, and
working instructions for the team (invoicing process, office hours, how to
phrase things). Since the whole KB goes into the rich prompt, the internal ones
would otherwise be handed to the model that writes to guests.

Two gates, both pinned here: the loader (load_for_conversation_context) and the
ContextFilter boundary, so a caller assembling entries by hand can't leak them.
"""

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Conversation, Guest, KnowledgeEntry
from ChatBotAI.services.context_filter import ContextFilter


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


SECRET = 'Rechnungen an buchhaltung@example.invalid, 0% Steuersatz'


def _conversation():
    guest = Guest(name='Anna', email='a@x.com')
    db.session.add(guest)
    db.session.flush()
    conv = Conversation(guest_id=guest.id, platform='smoobu', platform_id='r1',
                        status='active')
    db.session.add(conv)
    db.session.flush()
    return conv


def _seed():
    db.session.add(KnowledgeEntry(category='general', label='Rechnungen',
                                  value=SECRET, is_internal=True))
    db.session.add(KnowledgeEntry(category='faq', label='WLAN',
                                  value='Passwort SunnyBeach2024'))
    db.session.commit()


def test_loader_excludes_internal_entries(app):
    conv = _conversation()
    _seed()
    entries = KnowledgeEntry.load_for_conversation_context(conv)
    labels = [e['label'] for e in entries]
    assert 'WLAN' in labels
    assert 'Rechnungen' not in labels
    assert SECRET not in repr(entries)


def test_context_filter_drops_internal_entries(app):
    """Second gate: an entry handed in directly still must not pass."""
    entries = [
        {'category': 'general', 'label': 'Rechnungen', 'value': SECRET,
         'is_internal': True},
        {'category': 'faq', 'label': 'WLAN', 'value': 'Passwort SunnyBeach2024'},
    ]
    result = ContextFilter.filter(
        latest_message='Bekomme ich eine Rechnung?',
        conversation_history=[],
        knowledge_entries=entries,
    )
    labels = [e['label'] for e in result.knowledge_entries]
    assert 'Rechnungen' not in labels
    assert SECRET not in repr(result.knowledge_entries)


def test_entries_are_guest_facing_by_default(app):
    """The flag is opt-in — nothing silently disappears from the prompt."""
    conv = _conversation()
    entry = KnowledgeEntry(category='faq', label='Parken', value='Hof, kostenlos')
    db.session.add(entry)
    db.session.commit()
    assert entry.is_internal is False
    assert 'Parken' in [e['label'] for e in
                        KnowledgeEntry.load_for_conversation_context(conv)]
