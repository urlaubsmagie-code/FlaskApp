"""Guards the frontend/backend category contract for the knowledge base.

Regression: the Wissen tab leaked escalation categories (Safari ignores
display:none on <option>) AND the backend VALID_CATEGORIES was missing the
granular esc_* categories, so saving one returned "invalid category".
These categories must stay in sync with ESCALATION_CATEGORIES in knowledge.js.
"""
import pytest
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, User, KnowledgeEntry

# Mirrors ESCALATION_CATEGORIES in static/js/knowledge.js
ESCALATION_CATEGORIES = ['esc_maintenance', 'esc_cleanliness', 'esc_noise',
                         'esc_payment', 'esc_access', 'esc_emergency', 'esc_other']


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


def test_escalation_categories_are_valid():
    for cat in ESCALATION_CATEGORIES:
        assert cat in KnowledgeEntry.VALID_CATEGORIES, f"{cat} rejected by backend"


def test_create_with_escalation_category_succeeds(client):
    r = client.post('/chatbot/api/knowledge',
                    json={'category': 'esc_cleanliness', 'label': 'Sauberkeit',
                          'value': 'Reinigung Freitags'})
    assert r.status_code == 201, r.get_data(as_text=True)


def test_create_with_bogus_category_rejected(client):
    r = client.post('/chatbot/api/knowledge',
                    json={'category': 'not_a_category', 'label': 'x', 'value': 'y'})
    assert r.status_code == 400
