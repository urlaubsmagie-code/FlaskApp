"""UMI must escalate on the team's Eskalation topics — and must never see the
team's internal notes.

The topic labels are rendered into the guest-reply prompt so UMI catches a
paraphrase no trigger word matches. The note (`value`) stays team-only: it can
contain phone numbers and procedures that must not reach a guest.
"""

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db
from ChatBotAI.services.ai_service import AIService
from ChatBotAI.services.context_filter import ContextFilter


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


ESC_ENTRY = {
    'category': 'esc_access',
    'label': 'Aussperrung',
    'value': 'Hausmeister 0171-1234567 anrufen, Ersatzschlüssel im Büro',
    'trigger_words': 'ausgesperrt',
}


def _build(app, entries):
    service = AIService()
    return service._build_guest_reply_prompt(
        guest_profile={'name': 'Anna', 'language': 'de'},
        conversation_history=[],
        clean_latest='Ich komme nicht in die Wohnung',
        unanswered_count=1,
        knowledge_entries=entries,
    )


def test_topic_label_reaches_the_prompt(app):
    prompt = _build(app, [ESC_ENTRY])
    assert 'Aussperrung' in prompt


def test_internal_note_never_reaches_the_prompt(app):
    """Safety-critical: the note must not be renderable to a guest."""
    prompt = _build(app, [ESC_ENTRY])
    assert '0171-1234567' not in prompt
    assert 'Ersatzschlüssel' not in prompt


def test_no_escalation_entries_means_no_topic_line(app):
    prompt = _build(app, [{'category': 'general', 'label': 'WLAN', 'value': 'pw123'}])
    assert 'Aussperrung' not in prompt


def test_duplicate_labels_are_listed_once(app):
    prompt = _build(app, [ESC_ENTRY, dict(ESC_ENTRY)])
    assert prompt.count('Aussperrung') == 1


def test_context_filter_keeps_escalation_entries(app):
    """Relevance filtering must not drop topics — the list UMI sees has to be
    the same on every message, not whatever matched today's keywords."""
    entries = [ESC_ENTRY] + [
        {'category': 'general', 'label': f'Info {i}', 'value': f'text {i}'}
        for i in range(10)
    ]
    result = ContextFilter.filter(
        latest_message='Wo kann ich parken?',
        conversation_history=[],
        knowledge_entries=entries,
    )
    labels = [e['label'] for e in result.knowledge_entries]
    assert 'Aussperrung' in labels
