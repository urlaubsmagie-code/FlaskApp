"""An expired session must fail API calls as JSON 401, never as an HTML redirect.

The redirect was the real cause behind "Wissensextraktion fehlgeschlagen": fetch()
follows the 302 to /chatbot/login, gets 200 + HTML, and the caller's r.json()
throws. Every caller then reports its own generic error instead of "logged out",
and conversation.js additionally burns a pointless retry on it.
"""
import pytest
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, User


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        # A user must exist, otherwise the hook routes to /setup instead of /login.
        u = User(username='t', display_name='T')
        u.set_password('pw')
        db.session.add(u)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def anon(app):
    return app.test_client()


def test_api_post_returns_json_401_not_redirect(anon):
    r = anon.post('/chatbot/api/messages/1/extract-knowledge',
                  json={'scope': 'room'})
    assert r.status_code == 401
    assert r.is_json, 'API auth failure must be JSON, not an HTML login page'
    body = r.get_json()
    assert body['session_expired'] is True
    assert body['error']


def test_api_get_returns_json_401(anon):
    r = anon.get('/chatbot/api/conversations')
    assert r.status_code == 401
    assert r.get_json()['session_expired'] is True


def test_page_route_still_redirects_to_login(anon):
    """Only /api/ changes — humans hitting a page still get the login screen."""
    r = anon.get('/chatbot/')
    assert r.status_code == 302
    assert '/chatbot/login' in r.headers['Location']


def test_login_page_stays_reachable(anon):
    assert anon.get('/chatbot/login').status_code == 200
