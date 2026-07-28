import json
import pytest
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_manifest_served_with_correct_type_and_content(client):
    # Whitelisted (like sw.js), so reachable without login.
    r = client.get('/chatbot/manifest.webmanifest')
    assert r.status_code == 200
    assert 'application/manifest+json' in r.content_type
    data = json.loads(r.data)
    assert data['name'] == 'UMI-Chat'
    assert data['short_name'] == 'UMI-Chat'
    assert data['scope'] == '/chatbot/'
    assert data['start_url'] == '/chatbot/'
    assert data['display'] == 'standalone'
    assert data['theme_color'] == '#7B2332'
    assert len(data['icons']) == 4
    assert any(i.get('purpose') == 'maskable' for i in data['icons'])


def test_login_page_has_pwa_head_tags(app):
    # A user must exist, else /chatbot/login redirects to setup (routes.py:219).
    from ChatBotAI.models import User, db
    user = User(username='u', display_name='U', is_admin=True)
    user.set_password('pw'); db.session.add(user); db.session.commit()
    html = app.test_client().get('/chatbot/login').get_data(as_text=True)
    assert 'rel="manifest"' in html
    assert 'name="theme-color"' in html
    assert 'apple-touch-icon' in html


def test_inbox_has_pwa_head_tags(app):
    # Authenticated inbox (base.html) must carry the manifest link too.
    from ChatBotAI.models import User, db
    user = User(username='t', display_name='T', is_admin=True)
    user.set_password('pw'); db.session.add(user); db.session.commit()
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(user.id); s['_fresh'] = True
    html = c.get('/chatbot/').get_data(as_text=True)
    assert 'rel="manifest"' in html
    assert 'apple-mobile-web-app-title' in html
