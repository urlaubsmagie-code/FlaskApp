"""The UMI page carries the settings the team needs; /settings stays admin-only.

Both pages moved content, so both must still render — for an admin and for a
plain team member, who is the whole point of the move.
"""

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, User


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def _client(app, is_admin):
    user = User(username='admin' if is_admin else 'team', display_name='X', is_admin=is_admin)
    user.set_password('pw'); db.session.add(user); db.session.commit()
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(user.id); s['_fresh'] = True
    return c


@pytest.mark.parametrize('is_admin', [True, False])
def test_umi_page_renders_personality_and_templates(app, is_admin):
    r = _client(app, is_admin).get('/chatbot/knowledge')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'aiSettingsForm' in html          # Persönlichkeit tab
    assert 'hostInstructions' in html
    assert 'templatesList' in html           # Vorlagen tab
    assert 'templateModal' in html           # its dialog, outside the hidden panel
    assert 'data-tab="personality"' in html


@pytest.mark.parametrize('is_admin', [True, False])
def test_admin_only_fields_stay_admin_only(app, is_admin):
    """Temperature/max-tokens must not reach a non-admin.

    One user per app fixture on purpose: Flask-Login caches the loaded user on
    `g`, which is shared across requests inside a single long-lived app context,
    so two logins in one test would both see whoever loaded first.
    """
    html = _client(app, is_admin).get('/chatbot/knowledge').get_data(as_text=True)
    assert ('aiTemperature' in html) is is_admin


def test_settings_page_still_renders(app):
    r = _client(app, True).get('/chatbot/settings')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    # Moved away — must not be duplicated on both pages.
    assert 'aiSettingsForm' not in html
    assert 'templatesList' not in html
    # Still here: admin-only plumbing.
    assert 'ollamaStatus' in html
