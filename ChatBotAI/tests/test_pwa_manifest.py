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
