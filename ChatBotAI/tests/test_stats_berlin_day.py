"""'Today' on the inbox and Team-Leistung starts at 00:00 German time.

Timestamps are stored as naive UTC; splitting days at UTC midnight made 'today'
start at 02:00 local and put night-time activity on the previous day.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Conversation, Guest, Message, User, UserSession

BERLIN = ZoneInfo('Europe/Berlin')


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def user_and_client(app):
    user = User(username='tester', display_name='Tester', is_admin=True)
    user.set_password('pw')
    db.session.add(user)
    db.session.commit()
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(user.id)
        s['_fresh'] = True
    return user, c


def _midnight_utc():
    local = datetime.now(BERLIN).replace(hour=0, minute=0, second=0, microsecond=0)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def _conv(user_id=None):
    return _conv_for('g@x.com', user_id)


def _conv_for(email, user_id=None):
    guest = Guest(name='G', email=email)
    db.session.add(guest)
    db.session.flush()
    conv = Conversation(guest_id=guest.id, platform='smoobu', user_id=user_id)
    db.session.add(conv)
    db.session.flush()
    return conv


def test_inbox_messages_today_counts_guest_messages_since_berlin_midnight(user_and_client):
    _, client = user_and_client
    midnight = _midnight_utc()
    conv = _conv()
    for sender, at in [('guest', midnight + timedelta(minutes=1)),   # counts
                       ('guest', midnight - timedelta(minutes=1)),   # yesterday
                       ('owner', midnight + timedelta(minutes=2))]:  # ours
        db.session.add(Message(conversation_id=conv.id, sender_type=sender,
                               content='x', sent_at=at))
    db.session.commit()

    assert client.get('/chatbot/api/stats').get_json()['messages_today'] == 1


def test_team_page_splits_days_at_berlin_midnight(user_and_client):
    user, client = user_and_client
    midnight = _midnight_utc()
    conv = _conv()
    for at in (midnight + timedelta(minutes=1), midnight - timedelta(minutes=1)):
        db.session.add(Message(conversation_id=conv.id, sender_type='owner', content='x', sent_at=at))
    db.session.add(UserSession(user_id=user.id, started_at=midnight + timedelta(minutes=1),
                               last_active_at=midnight + timedelta(minutes=31)))
    db.session.commit()

    data = client.get('/chatbot/api/stats/detailed').get_json()
    today = datetime.now(BERLIN).date()
    days = {d['date']: d['team'] for d in data['daily']}
    assert data['daily'][-1]['date'] == today.isoformat()
    assert days[today.isoformat()] == 1
    assert days[(today - timedelta(days=1)).isoformat()] == 1
    me = next(u for u in data['team'] if u['user_id'] == user.id)
    assert me['online_minutes_today'] == 30


def test_team_page_reply_time_and_waiting(user_and_client):
    """Reply time runs from the FIRST unanswered guest message to our next
    message; a chat whose last word is the guest's is waiting."""
    _, client = user_and_client
    base = datetime.utcnow() - timedelta(days=3)
    answered, open_chat, thanks = _conv(), _conv_for('h@x.com'), _conv_for('t@x.com')
    for conv, sender, minutes in [(answered, 'guest', 0), (answered, 'guest', 10),
                                  (answered, 'owner', 40),     # 40 min after the first
                                  (open_chat, 'owner', 0), (open_chat, 'guest', 5),
                                  (thanks, 'guest', 0),        # "Danke!" ...
                                  (thanks, 'owner', 25 * 60)]: # ... check-in info next day: not a reply
        db.session.add(Message(conversation_id=conv.id, sender_type=sender, content='x',
                               sent_at=base + timedelta(minutes=minutes)))
    db.session.commit()

    data = client.get('/chatbot/api/stats/detailed').get_json()
    assert data['reply_minutes_median'] == 40
    assert data['waiting_count'] == 1


def test_umi_reply_is_credited_to_the_sender_not_the_assignee(user_and_client, app):
    """Messages sent from UMI carry the person who sent them. Before, none did,
    and Team-Leistung credited whoever the chat was assigned to."""
    from ChatBotAI.services.message_router import get_message_router
    user, client = user_and_client
    colleague = User(username='other', display_name='Other')
    colleague.set_password('pw')
    db.session.add(colleague)
    db.session.flush()
    conv = _conv(colleague.id)  # assigned to the colleague
    db.session.commit()

    with app.test_request_context():
        from flask_login import login_user
        login_user(user)
        result = get_message_router().process_owner_message(
            conversation_id=conv.id, content='Hallo', extract_memory=False, sent_via_app=True)
    assert db.session.get(Message, result['message_id']).user_id == user.id

    team = {u['user_id']: u for u in client.get('/chatbot/api/stats/detailed').get_json()['team']}
    assert team[user.id]['umi_messages_week'] == 1
    assert team[colleague.id]['umi_messages_week'] == 0
