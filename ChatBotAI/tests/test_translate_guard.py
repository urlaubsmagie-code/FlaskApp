"""A failed translation must fail loudly, never overwrite the guest's message.

Google serves an error page (HTTP 200, empty result-container) when the request
carries no browser User-Agent. deep-translator scraped that page and returned
"Error 500 (Server Error)!!1500.That's an error..." as the translation, so the
route answered 200 and the frontend replaced the guest's own words with it.
"""
import pytest
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, User
from ChatBotAI import routes


GOOGLE_ERROR_PAGE = (
    '<html><head><title>Error 500 (Server Error)!!1</title></head><body>'
    '<div class="result-container"></div>'
    '<p>That’s an error.There was an error. Please try again later.</p>'
    '</body></html>'
)
GOOGLE_OK_PAGE = '<html><body><div class="result-container">Hallo Welt</div></body></html>'


class _FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        u = User(username='t', display_name='T')
        u.set_password('pw')
        db.session.add(u)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = '1'
        s['_fresh'] = True
    return c


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch):
    # The LRU is module-global and would leak results between tests.
    cached = routes._translate_cached
    cached.cache_clear()
    # These legacy Google guards cover the presentation helper, not UMI.
    from ChatBotAI.services.translate import translate_text
    monkeypatch.setattr(routes, '_translate_cached', translate_text)
    yield
    cached.cache_clear()


def _patch_requests(monkeypatch, page):
    import requests
    monkeypatch.setattr(requests, 'get', lambda *a, **kw: _FakeResponse(page))


def test_google_error_page_does_not_become_a_translation(client, monkeypatch):
    _patch_requests(monkeypatch, GOOGLE_ERROR_PAGE)
    r = client.post('/chatbot/api/translate',
                    json={'text': 'Hello world', 'target': 'de'})
    assert r.status_code == 502, 'an error page must not be served as a translation'
    body = r.get_json()
    assert body['error'] == 'translation_failed'
    assert 'Server Error' not in str(body)


def test_successful_translation_is_returned(client, monkeypatch):
    _patch_requests(monkeypatch, GOOGLE_OK_PAGE)
    r = client.post('/chatbot/api/translate',
                    json={'text': 'Hello world', 'target': 'de'})
    assert r.status_code == 200
    body = r.get_json()
    assert body['translated'] == 'Hallo Welt'
    assert body['was_translated'] is True


def test_request_carries_a_browser_user_agent(client, monkeypatch):
    """Without it Google returns the error page — that IS the bug."""
    seen = {}

    import requests

    def fake_get(url, **kw):
        seen['url'] = url
        seen['headers'] = kw.get('headers') or {}
        return _FakeResponse(GOOGLE_OK_PAGE)

    monkeypatch.setattr(requests, 'get', fake_get)
    client.post('/chatbot/api/translate', json={'text': 'Hello', 'target': 'de'})
    assert 'Mozilla/5.0' in seen['headers'].get('User-Agent', '')


def test_unchanged_text_reports_not_translated(client, monkeypatch):
    _patch_requests(monkeypatch,
                    '<div class="result-container">Hallo Welt</div>')
    r = client.post('/chatbot/api/translate',
                    json={'text': 'Hallo Welt', 'target': 'de'})
    assert r.get_json()['was_translated'] is False


def test_empty_text_is_rejected(client):
    r = client.post('/chatbot/api/translate', json={'text': '   ', 'target': 'de'})
    assert r.status_code == 400
