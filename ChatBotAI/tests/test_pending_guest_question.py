"""UMI must answer everything the guest said since our last reply.

Real case (2026-09-03): a guest asked where to transfer her money, got no reply,
and nudged with "???" the next day. "UMI-Vorschlag" answered the "???" — the real
question never reached the prompt, so neither did the knowledge entry with the
IBAN (the KB is selected by keywords from that same text)."""
import pytest
from datetime import datetime, timedelta
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Guest, Conversation, Message, pending_guest_question
from ChatBotAI.services.context_filter import ContextFilter


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def _conv():
    g = Guest(name='G'); db.session.add(g); db.session.flush()
    c = Conversation(guest_id=g.id, platform='smoobu')
    db.session.add(c); db.session.commit()
    return c


def _msg(conv, sender, content, minutes):
    m = Message(conversation_id=conv.id, sender_type=sender, content=content,
                sent_at=datetime(2026, 9, 1) + timedelta(minutes=minutes))
    db.session.add(m); db.session.commit()
    return m


def test_nudge_after_question_answers_both(app):
    c = _conv()
    _msg(c, 'owner', 'Willkommen!', 0)
    question = _msg(c, 'guest', 'Wo finde ich die Bankdaten zum Überweisen?', 10)
    nudge = _msg(c, 'guest', '???', 20)

    newest, text = pending_guest_question(c)
    assert newest.id == nudge.id          # newest is still the nudge (used for reply_to)
    assert 'Bankdaten' in text             # ...but the question is what gets answered
    assert text.endswith('???')
    assert question.content in text


def test_messages_before_our_last_reply_are_excluded(app):
    c = _conv()
    _msg(c, 'guest', 'Alte Frage zum WLAN', 0)
    _msg(c, 'owner', 'Das Passwort ist X', 10)
    new_q = _msg(c, 'guest', 'Und wo parke ich?', 20)

    _, text = pending_guest_question(c)
    assert text == new_q.content
    assert 'WLAN' not in text


def test_falls_back_to_newest_when_team_already_replied(app):
    c = _conv()
    q = _msg(c, 'guest', 'Wo parke ich?', 0)
    _msg(c, 'owner', 'Hinterm Haus.', 10)

    newest, text = pending_guest_question(c)
    assert newest.id == q.id and text == q.content


def test_no_guest_message_returns_nothing(app):
    c = _conv()
    _msg(c, 'owner', 'Willkommen!', 0)
    assert pending_guest_question(c) == (None, '')


def test_small_knowledge_base_is_sent_whole(app):
    """Nothing is dropped while the KB fits the budget — the retrieval cap is what
    hid "Zahlungskonto" (no word in common with "Bankdaten ... überweisen")."""
    iban = {'category': 'faq', 'label': 'Zahlungskonto',
            'value': 'Urlaubsmagie GmbH\nDE80 8504 0000 0143 4026 00',
            'trigger_words': ''}
    noise = [{'category': 'faq', 'label': f'Anderes {i}', 'value': 'nichts',
              'trigger_words': ''} for i in range(20)]
    msg = 'Nun finde ich keine Bankdaten um mein Geld zu überweisen, wohin?'

    picked = ContextFilter._filter_knowledge_entries(
        noise + [iban], ContextFilter._extract_keywords(msg), msg)
    assert len(picked) == len(noise) + 1
    assert any(e['label'] == 'Zahlungskonto' for e in picked)


def test_trigger_words_rank_an_entry_the_wording_would_miss(app):
    """Above the budget the top-N scorer is back, and trigger words are what keep
    the right entry in it."""
    iban = {'category': 'faq', 'label': 'Zahlungskonto',
            'value': 'Urlaubsmagie GmbH\nDE80 8504 0000 0143 4026 00',
            'trigger_words': 'bankdaten, iban, überweisen, kontonummer'}
    # Push the KB over KB_FULL_BUDGET_CHARS so scoring decides again.
    bulk = 'x' * 400 + ' geld bezahlen überweisen konto bank'
    # Sized from the budget, not a fixed count, so raising the budget can't
    # silently turn this into an under-budget test.
    count = ContextFilter.KB_FULL_BUDGET_CHARS // len(bulk) + 10
    noise = [{'category': 'faq', 'label': f'Anderes {i} geld bezahlen',
              'value': bulk, 'trigger_words': ''} for i in range(count)]
    msg = 'Nun finde ich keine Bankdaten um mein Geld zu überweisen, wohin?'
    assert sum(len(e['label']) + len(e['value']) for e in noise) >         ContextFilter.KB_FULL_BUDGET_CHARS

    kws = ContextFilter._extract_keywords(msg)
    picked = ContextFilter._filter_knowledge_entries(noise + [iban], kws, msg)
    assert any(e['label'] == 'Zahlungskonto' for e in picked)

    without = {**iban, 'trigger_words': ''}
    picked_without = ContextFilter._filter_knowledge_entries(
        noise + [without], kws, msg)
    assert not any(e['label'] == 'Zahlungskonto' for e in picked_without)
