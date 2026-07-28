"""Guard against double-delivering a reply to the guest (Smoobu send has no id,
so a retry / re-click can send the same text twice). Tests the shared helper
`_recent_duplicate_owner_reply`."""
from datetime import datetime, timedelta

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Guest, Conversation, Message
from ChatBotAI.routes import _recent_duplicate_owner_reply


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def _conv():
    g = Guest(name='Karina')
    db.session.add(g); db.session.flush()
    c = Conversation(guest_id=g.id, platform='smoobu', smoobu_reservation_id='R1')
    db.session.add(c); db.session.commit()
    return c


def _owner_msg(conv_id, content, when):
    m = Message(conversation_id=conv_id, sender_type='owner', content=content,
                sent_at=when, is_processed=True)
    db.session.add(m); db.session.commit()
    return m


def test_blocks_identical_recent_reply(app):
    c = _conv()
    _owner_msg(c.id, 'Hallo Karina, pro Wohnung gibt es nur eine Gästekarte.', datetime.utcnow())
    # Same text (even with whitespace/case noise) within window -> blocked.
    assert _recent_duplicate_owner_reply(c.id, '  Hallo Karina, pro Wohnung gibt es nur eine Gästekarte.  ')


def test_allows_different_reply(app):
    c = _conv()
    _owner_msg(c.id, 'Hallo Karina, pro Wohnung gibt es nur eine Gästekarte.', datetime.utcnow())
    assert not _recent_duplicate_owner_reply(c.id, 'Guten Tag, wie kann ich helfen?')


def test_allows_identical_reply_after_window(app):
    c = _conv()
    _owner_msg(c.id, 'Vielen Dank!', datetime.utcnow() - timedelta(seconds=200))
    # Older than the 120s window -> a genuine repeat is allowed through.
    assert not _recent_duplicate_owner_reply(c.id, 'Vielen Dank!', within_seconds=120)


def test_scoped_to_conversation(app):
    c1, c2 = _conv(), _conv()
    _owner_msg(c1.id, 'Danke!', datetime.utcnow())
    # Same text in a DIFFERENT conversation must not block.
    assert not _recent_duplicate_owner_reply(c2.id, 'Danke!')


# ---------------------------------------------------------------------------
# Concurrency: the guard alone is a TOCTOU race (check -> slow send -> store).
# `_guarded_smoobu_reply` closes it by holding a per-conversation lock across the
# whole check+send+store, so two overlapping identical sends can't both get through.
# In-memory SQLite isn't shared across threads, so we test the concurrency-control
# layer with mocked collaborators (the guard's SQL is covered by the tests above).
# ---------------------------------------------------------------------------
import threading
import time
from ChatBotAI import routes as R


class _Conv:
    def __init__(self, cid):
        self.id = cid
        self.smoobu_reservation_id = 'R' + str(cid)


def _run_two_sends(monkeypatch, conv_a, conv_b, content='same text'):
    """Fire two _guarded_smoobu_reply calls concurrently. Returns (results,
    send_calls, max_concurrent_sends). `stored` acts as the committed-message
    store the duplicate guard reads."""
    stored = []                 # normalized 'DB' of stored owner replies
    store_lock = threading.Lock()
    send_calls = []
    conc = {'now': 0, 'max': 0}
    conc_lock = threading.Lock()

    # Guard: reports a duplicate once an identical reply has been stored.
    monkeypatch.setattr(R, '_recent_duplicate_owner_reply',
                        lambda cid, text, **kw: (cid, text) in stored)

    class FakeRouter:
        def process_owner_message(self, conversation_id, content, **kw):
            with store_lock:
                stored.append((conversation_id, content))
                return {'message_id': len(stored)}
    monkeypatch.setattr(R, 'get_message_router', lambda: FakeRouter())

    def slow_send():
        with conc_lock:
            conc['now'] += 1
            conc['max'] = max(conc['max'], conc['now'])
        try:
            time.sleep(0.25)          # widen the race window
            send_calls.append(1)
            return {'id': str(len(send_calls))}
        finally:
            with conc_lock:
                conc['now'] -= 1

    results = []
    res_lock = threading.Lock()

    def work(conv):
        r = R._guarded_smoobu_reply(conv, content, slow_send)
        with res_lock:
            results.append(r)

    # clean any leftover locks for these conversation ids
    R._conversation_send_locks.pop(conv_a.id, None)
    R._conversation_send_locks.pop(conv_b.id, None)

    t1 = threading.Thread(target=work, args=(conv_a,))
    t2 = threading.Thread(target=work, args=(conv_b,))
    t1.start(); t2.start(); t1.join(); t2.join()
    return results, send_calls, conc['max']


def test_race_same_conversation_sends_once(monkeypatch):
    # Two identical sends to the SAME chat, racing across a slow send: exactly one
    # reaches the guest, the other is duplicate-skipped. This is the reported bug.
    conv = _Conv(9001)
    results, send_calls, max_conc = _run_two_sends(monkeypatch, conv, conv)
    assert max_conc == 1, 'per-conversation lock must serialize the sends'
    assert len(send_calls) == 1, 'only one message delivered to the guest'
    assert sum(1 for r in results if r.get('duplicate_skipped')) == 1
    assert sum(1 for r in results if r.get('message_id')) == 1


def test_different_conversations_are_not_serialized(monkeypatch):
    # The lock is PER conversation: sends to two different chats run concurrently
    # and both deliver (no false duplicate blocking, no global bottleneck).
    ca, cb = _Conv(9002), _Conv(9003)
    results, send_calls, max_conc = _run_two_sends(monkeypatch, ca, cb)
    assert max_conc == 2, 'different conversations must not block each other'
    assert len(send_calls) == 2
    assert all(r.get('message_id') for r in results)


# ---------------------------------------------------------------------------
# The generic local-store endpoint (/api/conversations/<id>/messages) had NO
# guard, so it silently created a phantom copy of a reply already sent via the
# platform path — the duplicate seen ONLY in our app (the guest was messaged
# once). It must now dedup like the platform-send paths.
# ---------------------------------------------------------------------------
from ChatBotAI.models import User


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


def test_local_send_endpoint_skips_duplicate(client):
    c = _conv()
    R._conversation_send_locks.pop(c.id, None)
    body = {'content': 'Hallo, das passt gut für uns!'}
    r1 = client.post(f'/chatbot/api/conversations/{c.id}/messages', json=body)
    r2 = client.post(f'/chatbot/api/conversations/{c.id}/messages', json=body)
    assert r1.status_code == 201
    assert r2.status_code == 200 and r2.get_json().get('duplicate_skipped') is True
    # Exactly one owner message stored despite two identical POSTs.
    assert Message.query.filter_by(conversation_id=c.id, sender_type='owner').count() == 1


def test_local_send_endpoint_allows_distinct_messages(client):
    c = _conv()
    R._conversation_send_locks.pop(c.id, None)
    client.post(f'/chatbot/api/conversations/{c.id}/messages', json={'content': 'Erste Nachricht'})
    r2 = client.post(f'/chatbot/api/conversations/{c.id}/messages', json={'content': 'Andere Nachricht'})
    assert r2.status_code == 201
    assert Message.query.filter_by(conversation_id=c.id, sender_type='owner').count() == 2
