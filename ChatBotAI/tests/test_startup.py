"""Production/standalone parity, configuration and background-task isolation."""

import logging
from unittest.mock import Mock

import pytest
from flask import Flask
from sqlalchemy import text

from ChatBotAI import chatbot_bp, init_chatbot
from ChatBotAI.app import create_app
from ChatBotAI.config import TestingConfig, ProductionConfig
from ChatBotAI.models import db
from ChatBotAI.startup import configure_app, start_background_tasks
from ChatBotAI.services.debug_service import get_api_tracker, get_log_handler
from ChatBotAI.services.notion_service import get_notion_service


@pytest.mark.parametrize('integrated', [False, True])
def test_both_entrypoints_initialize_services_and_sqlite(integrated, tmp_path):
    if integrated:
        app = Flask('review-portal', instance_path=str(tmp_path))
        app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
        app.register_blueprint(chatbot_bp)
    else:
        app = create_app(TestingConfig)
    try:
        assert get_notion_service() is not None
        assert get_api_tracker() is not None
        assert app.extensions['chatbot_initialized']
        with app.app_context():
            assert db.session.execute(text('PRAGMA foreign_keys')).scalar() == 1
            assert db.session.execute(text('PRAGMA busy_timeout')).scalar() == 5000
            assert db.session.execute(text('SELECT count(*) FROM message_fts')).scalar() == 0
        handler = get_log_handler()
        init_chatbot(app)
        assert get_log_handler() is handler  # no repeated extension setup
        assert not app.extensions.get('chatbot_background_tasks')
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()


def test_bare_host_reads_late_environment_without_enabling_debug(monkeypatch):
    monkeypatch.setenv('FLASK_ENV', 'development')
    monkeypatch.setenv('SECRET_KEY', 'private-test-value-with-enough-entropy')
    monkeypatch.setenv('OLLAMA_TIMEOUT', '77')
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
    app = Flask('review-portal')
    configure_app(app)
    assert not app.debug
    assert app.secret_key == 'private-test-value-with-enough-entropy'
    assert app.config['SQLALCHEMY_DATABASE_URI'] == 'sqlite:///:memory:'
    assert app.config['OLLAMA_TIMEOUT'] == 77
    assert app.config['SESSION_COOKIE_SECURE'] is True
    assert app.config['SESSION_COOKIE_SAMESITE'] == 'Lax'
    assert app.config['REMEMBER_COOKIE_SECURE'] is True


@pytest.mark.parametrize('key', ['', 'dev-secret-key-change-in-production',
                                  'change-this-to-a-secure-random-string'])
def test_production_rejects_missing_or_placeholder_secret(monkeypatch, key):
    monkeypatch.setenv('SECRET_KEY', key)
    with pytest.raises(RuntimeError, match='SECRET_KEY'):
        configure_app(Flask('review-portal'))


def test_explicit_production_config_is_validated_without_flask_env(monkeypatch):
    monkeypatch.delenv('FLASK_ENV', raising=False)
    class InvalidProduction(ProductionConfig):
        SECRET_KEY = ''
    with pytest.raises(RuntimeError, match='SECRET_KEY'):
        configure_app(Flask('review-portal'), InvalidProduction)


def test_explicit_host_settings_are_preserved(monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'environment-secret')
    monkeypatch.setenv('OLLAMA_TIMEOUT', '30')
    app = Flask('review-portal')
    app.config.update(SECRET_KEY='host-configured-secret', OLLAMA_TIMEOUT=88,
                      SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    configure_app(app)
    assert app.secret_key == 'host-configured-secret'
    assert app.config['OLLAMA_TIMEOUT'] == 88


def test_testing_does_not_start_daemons_even_if_enabled(monkeypatch):
    import ChatBotAI.app as runtime
    starters = []
    for name in ('_start_background_sync', '_start_email_reconcile', '_start_keepalive'):
        starter = Mock()
        monkeypatch.setattr(runtime, name, starter)
        starters.append(starter)
    app = Flask('test')
    app.config.update(TESTING=True, CHATBOT_BACKGROUND_TASKS_ENABLED=True)
    start_background_tasks(app)
    assert all(not starter.called for starter in starters)


def test_production_daemons_start_once_and_failure_does_not_block_others(monkeypatch):
    import ChatBotAI.app as runtime
    sync = Mock(side_effect=RuntimeError('cannot start'))
    email, keepalive = Mock(), Mock()
    monkeypatch.setattr(runtime, '_start_background_sync', sync)
    monkeypatch.setattr(runtime, '_start_email_reconcile', email)
    monkeypatch.setattr(runtime, '_start_keepalive', keepalive)
    app = Flask('review-portal')
    start_background_tasks(app)
    sync.side_effect = None
    start_background_tasks(app)
    start_background_tasks(app)
    assert sync.call_count == 2
    assert email.call_count == 1
    assert keepalive.call_count == 1


def test_test_factory_never_runs_startup_network_or_migrations(monkeypatch):
    from ChatBotAI.services.ai_service import AIService
    import ChatBotAI.app as runtime
    probe, migrations, file_logger = Mock(), Mock(), Mock()
    monkeypatch.setattr(AIService, 'test_connection', probe)
    monkeypatch.setattr(runtime, '_auto_upgrade_schema', migrations)
    monkeypatch.setattr(runtime, '_install_file_logger', file_logger)
    app = create_app(TestingConfig)
    assert not probe.called and not migrations.called and not file_logger.called
    assert app.instance_path == TestingConfig.CHATBOT_INSTANCE_PATH
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def test_migrations_preserve_existing_application_logging(tmp_path):
    from flask_migrate import upgrade
    from ChatBotAI.app import MIGRATIONS_DIR
    app = create_app(TestingConfig)
    log = logging.getLogger('ChatBotAI.services.smoobu_service')
    handlers = list(logging.getLogger().handlers)
    log.disabled = False
    # The fresh test schema already has columns from the baseline migration.
    # Its SQL may fail, but loading env.py must never disable application logs.
    with app.app_context():
        try:
            upgrade(directory=str(MIGRATIONS_DIR))
        except Exception:
            db.session.rollback()
        assert log.disabled is False
        assert logging.getLogger().handlers == handlers
        log.error('migration logging regression marker')
        assert any('migration logging regression marker' in e['message']
                   for e in get_log_handler().get_entries())
        db.session.remove()
        db.engine.dispose()
