"""Per-message translation endpoint.

Reading a guest message in a language nobody on the team speaks was a manual
copy-paste into Google Translate. The endpoint wraps deep-translator (already a
dependency of the review portal) — no key, no new service.

The translator itself is stubbed: these pin OUR contract (auth, empty input,
already-in-target detection, upstream failure), not Google's output.
"""

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, User
from ChatBotAI import routes as routes_mod


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


@pytest.fixture(autouse=True)
def clear_cache():
    # Tests may replace the module attribute until monkeypatch teardown runs.
    # Clear the real cache independently of fixture teardown ordering.
    cached = routes_mod._translate_cached
    cached.cache_clear()
    yield
    cached.cache_clear()


def test_translates_foreign_message(client, monkeypatch):
    monkeypatch.setattr(routes_mod, '_translate_cached',
                        lambda text, target: 'Hallo, wo ist der Schlüssel?')
    r = client.post('/chatbot/api/translate',
                    json={'text': 'Bonjour, où est la clé ?', 'target': 'de'})
    assert r.status_code == 200
    body = r.get_json()
    assert body['translated'] == 'Hallo, wo ist der Schlüssel?'
    assert body['was_translated'] is True
    assert body['target'] == 'de'


def test_same_text_back_is_not_a_translation(client, monkeypatch):
    """Google returns the input unchanged when it is already German — the UI
    uses this to say 'already in German' instead of swapping the text."""
    monkeypatch.setattr(routes_mod, '_translate_cached',
                        lambda text, target: 'Wann können wir einchecken?')
    r = client.post('/chatbot/api/translate',
                    json={'text': 'Wann können wir einchecken?'})
    assert r.get_json()['was_translated'] is False


def test_english_target_is_honoured(client, monkeypatch):
    seen = {}

    def fake(text, target):
        seen['target'] = target
        return 'Where is the key?'

    monkeypatch.setattr(routes_mod, '_translate_cached', fake)
    r = client.post('/chatbot/api/translate',
                    json={'text': 'Où est la clé ?', 'target': 'en'})
    assert seen['target'] == 'en'
    assert r.get_json()['target'] == 'en'


def test_unknown_target_falls_back_to_german(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(routes_mod, '_translate_cached',
                        lambda text, target: seen.setdefault('target', target) and 'x')
    client.post('/chatbot/api/translate', json={'text': 'hola', 'target': 'kl'})
    assert seen['target'] == 'de'


def test_empty_text_rejected(client):
    r = client.post('/chatbot/api/translate', json={'text': '   '})
    assert r.status_code == 400


def test_upstream_failure_is_502_not_500(client, monkeypatch):
    def boom(text, target):
        raise RuntimeError('google is down')

    monkeypatch.setattr(routes_mod, '_translate_cached', boom)
    r = client.post('/chatbot/api/translate', json={'text': 'hola'})
    assert r.status_code == 502
    assert r.get_json()['error'] == 'translation_failed'


def test_requires_login(app):
    r = app.test_client().post('/chatbot/api/translate', json={'text': 'hola'})
    assert r.status_code in (302, 401)


def test_long_message_is_truncated_for_the_api(monkeypatch):
    """Google rejects payloads over 5000 chars."""
    captured = {}

    class _Resp:
        text = '<div class="result-container">ok</div>'

        def raise_for_status(self):
            pass

    def fake_get(url, params=None, **kw):
        captured['len'] = len((params or {}).get('q', ''))
        return _Resp()

    # Assert on the helper, not on routes._translate_cached: that wrapper is
    # lru_cache'd, so whether the fake is reached at all would depend on cache
    # state any other test could have touched.
    from ChatBotAI.services import translate as translate_mod
    monkeypatch.setattr(translate_mod.requests, 'get', fake_get)
    translate_mod.translate_text('x' * 8000, 'de')
    assert captured['len'] <= 4900
