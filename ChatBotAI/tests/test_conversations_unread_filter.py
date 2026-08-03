"""The inbox 'Ungelesen' filter must return ALL unread conversations server-side,
not just the ones on the currently loaded page (client-side filtering over
paginated data hid old unread conversations until 'Load More' was clicked)."""
import pytest
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Guest, Conversation, User


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


def _conv(read):
    g = Guest(name='G'); db.session.add(g); db.session.flush()
    c = Conversation(guest_id=g.id, platform='airbnb', is_read=read)
    db.session.add(c); db.session.commit()
    return c


def test_unread_filter_returns_only_unread(client, app):
    read_c = _conv(read=True)
    unread_c = _conv(read=False)

    r = client.get('/chatbot/api/conversations?unread=true')
    assert r.status_code == 200
    ids = {c['id'] for c in r.get_json()['conversations']}
    assert unread_c.id in ids
    assert read_c.id not in ids


def test_no_unread_param_returns_all(client, app):
    read_c = _conv(read=True)
    unread_c = _conv(read=False)

    r = client.get('/chatbot/api/conversations')
    ids = {c['id'] for c in r.get_json()['conversations']}
    assert read_c.id in ids and unread_c.id in ids
