import pytest
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, AISettings


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def test_host_addresses_default_and_override(app):
    from ChatBotAI.services.email_thread_backfill import get_host_addresses
    # defaults present, lowercased
    defaults = get_host_addresses()
    assert 'buchungsanfrage.urlaubsmagie@gmail.com' in defaults
    assert 'urlaubsmagie@host.smoobu.com' in defaults
    # override via settings (comma-separated, mixed case + spaces)
    AISettings.set('email_host_addresses', 'Foo@Bar.com, baz@qux.de')
    over = get_host_addresses()
    assert over == {'foo@bar.com', 'baz@qux.de'}


def test_thread_backfill_config_defaults(app):
    from ChatBotAI.services.email_thread_backfill import get_thread_backfill_config
    cfg = get_thread_backfill_config()
    assert cfg['auto_enabled'] is False
    assert cfg['lookback_days'] == 180
    assert cfg['window_minutes'] == 10
