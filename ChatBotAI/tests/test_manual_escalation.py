"""Manual escalation: the team must be able to flag a chat as important even
when UMI is not answering it. Same flag the AI sets, so the inbox filter,
badge and banner all keep working unchanged.
"""

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Conversation, Guest, User


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


def _conv():
    guest = Guest(name='G', email='g@x.com')
    db.session.add(guest)
    db.session.flush()
    conv = Conversation(guest_id=guest.id, platform='smoobu',
                        ai_enabled=False, auto_respond=False)
    db.session.add(conv)
    db.session.commit()
    return conv


def test_escalate_then_resolve(client, app):
    conv = _conv()
    assert conv.escalated is False

    r = client.post(f'/chatbot/api/conversations/{conv.id}/escalate')
    assert r.status_code == 200
    assert r.get_json()['escalated'] is True
    assert db.session.get(Conversation, conv.id).escalated is True
    assert db.session.get(Conversation, conv.id).escalated_at is not None

    r = client.post(f'/chatbot/api/conversations/{conv.id}/resolve')
    assert r.status_code == 200
    assert r.get_json()['escalated'] is False
    assert db.session.get(Conversation, conv.id).escalated is False


def test_escalated_shows_in_escalated_filter(client):
    conv = _conv()
    client.post(f'/chatbot/api/conversations/{conv.id}/escalate')

    r = client.get('/chatbot/api/conversations?escalated=true')
    ids = [c['id'] for c in r.get_json()['conversations']]
    assert conv.id in ids


def test_stats_report_open_escalations(client, app):
    """The inbox badge is driven by /api/stats — closed chats must not count,
    or the number never drops and the team stops trusting it."""
    _conv().escalated = True

    other = Guest(name='G2', email='g2@x.com')
    db.session.add(other)
    db.session.flush()
    closed = Conversation(guest_id=other.id, platform='smoobu',
                          escalated=True, status='closed')
    db.session.add(closed)
    db.session.commit()

    data = client.get('/chatbot/api/stats').get_json()
    assert data['escalated_count'] == 1


def test_escalated_filter_matches_the_badge(client, app):
    """The badge counts open escalations; the filter must return the same set,
    or clicking a badge showing 19 shows a different number."""
    open_conv = _conv()
    open_conv.escalated = True

    other = Guest(name='G3', email='g3@x.com')
    db.session.add(other)
    db.session.flush()
    db.session.add(Conversation(guest_id=other.id, platform='smoobu',
                                escalated=True, status='closed'))
    db.session.commit()

    listed = client.get('/chatbot/api/conversations?escalated=true').get_json()
    count = client.get('/chatbot/api/stats').get_json()['escalated_count']
    assert [c['id'] for c in listed['conversations']] == [open_conv.id]
    assert listed['total'] == count == 1


def test_approval_tile_matches_its_filter(client, app):
    """The UMI-Freigabe tile opens ?status=pending_approval — same set, same count."""
    from ChatBotAI.models import Message
    waiting = _conv()
    for _ in range(2):  # two drafts in one chat still count once
        db.session.add(Message(conversation_id=waiting.id, sender_type='ai',
                               content='draft', approval_status='pending'))
    other = Guest(name='G4', email='g4@x.com')
    db.session.add(other)
    db.session.flush()
    done = Conversation(guest_id=other.id, platform='smoobu')
    db.session.add(done)
    db.session.flush()
    db.session.add(Message(conversation_id=done.id, sender_type='ai',
                           content='sent', approval_status='approved'))
    db.session.commit()

    listed = client.get('/chatbot/api/conversations?status=pending_approval').get_json()
    count = client.get('/chatbot/api/stats').get_json()['pending_approval_count']
    assert [c['id'] for c in listed['conversations']] == [waiting.id]
    assert listed['total'] == count == 1
    assert client.get('/chatbot/').status_code == 200  # inbox renders with the new header vars


def test_sidebar_badge_source_matches_unread_tile(client, app):
    """The sidebar badge reads /last-updated, the Ungelesen tile reads /api/stats.
    Both must count every unread chat — not just page 1, not just 'mine'."""
    colleague = User(username='colleague', display_name='Colleague')
    colleague.set_password('pw')
    db.session.add(colleague)
    db.session.flush()
    for i in range(60):  # more than one inbox page (50)
        g = Guest(name=f'U{i}', email=f'u{i}@x.com')
        db.session.add(g)
        db.session.flush()
        db.session.add(Conversation(guest_id=g.id, platform='smoobu', is_read=False,
                                    user_id=colleague.id if i % 2 else None))  # half assigned to someone else
    db.session.commit()

    badge = client.get('/chatbot/api/conversations/last-updated').get_json()['unread']
    tile = client.get('/chatbot/api/stats').get_json()['unread_count']
    assert badge == tile == 60


def test_playtest_chats_are_excluded_from_stats(client, app):
    """The badge must describe the set the list can actually show.

    /api/conversations filters out playtest chats; the stats query did not, so
    an escalated playtest chat produced a badge reading 1 over an empty list.
    """
    ghost = Guest(name='Playtest', email='pt@x.com')
    db.session.add(ghost)
    db.session.flush()
    db.session.add(Conversation(guest_id=ghost.id, platform='playtest',
                                escalated=True, status='active', is_read=False))
    db.session.commit()

    data = client.get('/chatbot/api/stats').get_json()
    listed = client.get('/chatbot/api/conversations?escalated=true').get_json()
    assert data['escalated_count'] == listed['total'] == 0
    assert data['total_conversations'] == 0
    assert data['unread_count'] == 0


def test_resolve_keeps_the_escalation_timestamp(client, app):
    """Resolving must not erase the evidence that a chat was escalated.

    Clearing escalated_at made "detection never fired" indistinguishable from
    "fired and was handled" — there is no other record, prod logging aside.
    """
    conv = _conv()
    client.post(f'/chatbot/api/conversations/{conv.id}/escalate')
    assert conv.escalated_at is not None
    stamped = conv.escalated_at

    client.post(f'/chatbot/api/conversations/{conv.id}/resolve')
    assert conv.escalated is False
    assert conv.escalated_at == stamped
