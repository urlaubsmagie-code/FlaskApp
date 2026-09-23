"""Multi-account Smoobu routing.

UMI talks to more than one Smoobu account (Sonnenhof lives in a separate one).
The danger is sending a guest message with the wrong account's API key, so
these tests pin the routing rules:

  * a conversation is served by the account it was synced from
  * an untagged (pre-multi-account) conversation falls back to the primary
  * webhooks route by their 'user' field, and an unknown account is ignored
"""

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, AISettings, Conversation, Guest, Property
from ChatBotAI.services import smoobu_service as ss


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def accounts(app):
    """Two connected accounts: slot 1 = 111, slot 2 = 222."""
    AISettings.set('smoobu_api_key', 'key-one')
    AISettings.set('smoobu_account_id', '111')
    AISettings.set('smoobu_api_key_2', 'key-two')
    AISettings.set('smoobu_account_id_2', '222')
    for svc in ss._smoobu_services.values():
        svc.reload_api_key()
    return ss._smoobu_services


def _conv(account_id):
    guest = Guest(name='G', email=f'g{account_id}@x.com')
    db.session.add(guest)
    db.session.flush()
    conv = Conversation(guest_id=guest.id, platform='smoobu',
                        smoobu_reservation_id='900', smoobu_account_id=account_id)
    db.session.add(conv)
    db.session.commit()
    return conv


def test_conversation_routes_to_its_own_account(accounts):
    assert ss.get_smoobu_service_for(_conv('111')).api_key == 'key-one'
    assert ss.get_smoobu_service_for(_conv('222')).api_key == 'key-two'


def test_untagged_conversation_falls_back_to_primary(accounts):
    """Rows written before multi-account existed have a NULL tag."""
    assert ss.get_smoobu_service_for(_conv(None)).api_key == 'key-one'


def test_unknown_account_never_borrows_another_key(accounts):
    """A chat from an account we no longer hold a key for must not be sent
    through a different account — that would message the wrong guest."""
    assert ss.get_smoobu_service_by_account('999') is None


def test_services_lists_only_configured_accounts(app):
    AISettings.set('smoobu_api_key', 'key-one')
    AISettings.set('smoobu_account_id', '111')
    AISettings.set('smoobu_api_key_2', '')
    for svc in ss._smoobu_services.values():
        svc.reload_api_key()

    services = ss.get_smoobu_services()
    assert [s.slot for s in services] == [1]


def test_apartment_lookup_is_scoped_to_the_account(accounts):
    """Apartment ids are only unique within one Smoobu account."""
    db.session.add_all([
        Property(name='A1 (acct 1)', smoobu_apartment_id='50', smoobu_account_id='111'),
        Property(name='A1 (acct 2)', smoobu_apartment_id='50', smoobu_account_id='222'),
    ])
    db.session.commit()

    assert accounts[1]._property_for_apartment('50').name == 'A1 (acct 1)'
    assert accounts[2]._property_for_apartment('50').name == 'A1 (acct 2)'


def test_legacy_untagged_property_belongs_to_primary(accounts):
    db.session.add(Property(name='Legacy', smoobu_apartment_id='77', smoobu_account_id=None))
    db.session.commit()

    assert accounts[1]._property_for_apartment('77').name == 'Legacy'
    assert accounts[2]._property_for_apartment('77') is None


def test_settings_keys_keep_slot_one_backwards_compatible():
    assert ss.settings_key(1) == 'smoobu_api_key'
    assert ss.account_settings_key(1) == 'smoobu_account_id'
    assert ss.settings_key(2) == 'smoobu_api_key_2'
    assert ss.account_settings_key(2) == 'smoobu_account_id_2'


def test_webhook_dispatches_to_the_account_that_fired_it(accounts, app, monkeypatch):
    """The webhook's 'user' field decides which key syncs the booking."""
    from ChatBotAI import routes

    synced = []
    for slot, svc in accounts.items():
        monkeypatch.setattr(svc, 'sync_conversation_messages',
                            lambda bid, _s=slot: synced.append((_s, bid)) or {'imported': 0})

    routes._run_webhook_message_sync(app, '12345', account_id=222)
    assert synced == [(2, '12345')]


def test_webhook_from_unknown_account_is_ignored(accounts, app, monkeypatch):
    from ChatBotAI import routes

    calls = []
    for svc in accounts.values():
        monkeypatch.setattr(svc, 'sync_conversation_messages',
                            lambda bid: calls.append(bid) or {'imported': 0})

    routes._run_webhook_message_sync(app, '12345', account_id=999)
    assert calls == []


def test_webhook_without_account_id_uses_primary(accounts, app, monkeypatch):
    """Older payloads / manual replays carry no 'user' — keep old behaviour."""
    from ChatBotAI import routes

    synced = []
    for slot, svc in accounts.items():
        monkeypatch.setattr(svc, 'sync_conversation_messages',
                            lambda bid, _s=slot: synced.append(_s) or {'imported': 0})

    routes._run_webhook_message_sync(app, '12345', account_id=None)
    assert synced == [1]


# =============================================================================
# Smoobu HMAC auth (new token format: label + secret)
# =============================================================================

def _capture(monkeypatch):
    """Capture the outgoing request instead of sending it."""
    seen = {}

    class FakeResponse:
        status_code = 200
        headers = {}
        text = '{}'

        def json(self):
            return {}

    def fake_request(method, url, headers=None, timeout=None, **kw):
        seen.update(method=method, url=url, headers=headers or {}, kw=kw)
        return FakeResponse()

    monkeypatch.setattr(ss.requests, 'request', fake_request)
    return seen


def test_legacy_key_without_secret_uses_the_old_header(app, monkeypatch):
    seen = _capture(monkeypatch)
    AISettings.set('smoobu_api_key', 'legacy-key')
    AISettings.set('smoobu_api_secret', '')
    svc = ss.SmoobuService(slot=1)

    svc._request('GET', '/me')

    assert seen['headers']['Api-Key'] == 'legacy-key'
    assert 'X-Signature' not in seen['headers']


def test_token_with_secret_signs_the_request(app, monkeypatch):
    import base64, hashlib, hmac

    seen = _capture(monkeypatch)
    AISettings.set('smoobu_api_key', 'usr_live_abc')
    AISettings.set('smoobu_api_secret', 'shhh')
    svc = ss.SmoobuService(slot=1)

    svc._request('GET', '/reservations?page_size=50&page=1')

    h = seen['headers']
    assert h['X-API-Key'] == 'usr_live_abc'
    assert 'Api-Key' not in h            # legacy header must not leak alongside
    assert h['X-Timestamp'].endswith('Z')
    assert len(h['X-Nonce']) == 36       # uuid4

    # Rebuild the canonical string independently — this pins the exact format:
    # path keeps the /api prefix, query is sorted, body hash is of an empty body.
    expected_canonical = '\n'.join([
        'GET', '/api/reservations', 'page=1&page_size=50',
        h['X-Timestamp'], h['X-Nonce'],
        hashlib.sha256(b'').hexdigest(), 'usr_live_abc',
    ])
    expected = base64.b64encode(
        hmac.new(b'shhh', expected_canonical.encode(), hashlib.sha256).digest()).decode()
    assert h['X-Signature'] == expected


def test_post_signs_the_exact_body_that_is_sent(app, monkeypatch):
    """The body hash must cover the bytes on the wire, or every send 401s."""
    import hashlib

    seen = _capture(monkeypatch)
    AISettings.set('smoobu_api_key', 'usr_live_abc')
    AISettings.set('smoobu_api_secret', 'shhh')
    svc = ss.SmoobuService(slot=1)

    svc._request('POST', '/reservations/1/messages/send-message-to-guest',
                 json={'messageBody': 'Hallo'})

    sent_body = seen['kw']['data']
    assert 'json' not in seen['kw']      # serialized here, not by requests
    assert hashlib.sha256(sent_body.encode()).hexdigest() in _canonical_of(seen)


def _canonical_of(seen):
    """Re-derive what must have been signed, for the body-hash assertion."""
    import base64, hashlib, hmac
    h = seen['headers']
    from urllib.parse import urlparse
    path = urlparse(seen['url']).path
    body = seen['kw'].get('data') or ''
    canonical = '\n'.join(['POST', path, '', h['X-Timestamp'], h['X-Nonce'],
                           hashlib.sha256(body.encode()).hexdigest(), h['X-API-Key']])
    expected = base64.b64encode(
        hmac.new(b'shhh', canonical.encode(), hashlib.sha256).digest()).decode()
    assert h['X-Signature'] == expected
    return canonical


# =============================================================================
# New-account cutoff: connect an account and only get messages from then on
# =============================================================================

def _svc_with_cutoff(cutoff_iso):
    AISettings.set('smoobu_api_key_2', 'usr_live_x')
    AISettings.set('smoobu_sync_from_2', cutoff_iso)
    svc = ss.SmoobuService(slot=2)
    return svc


def test_messages_before_the_cutoff_are_skipped(app):
    from datetime import datetime, timedelta
    cutoff = datetime(2026, 8, 10, 12, 0, 0)
    svc = _svc_with_cutoff(cutoff.isoformat())

    assert svc._too_old(cutoff - timedelta(days=1)) is True
    assert svc._too_old(cutoff + timedelta(minutes=1)) is False
    assert svc._too_old(None) is False        # unknown timestamp → never dropped


def test_no_cutoff_means_import_everything(app):
    """The primary account has no cutoff — its behaviour must not change."""
    from datetime import datetime
    AISettings.set('smoobu_api_key', 'legacy')
    AISettings.set('smoobu_sync_from', '')
    svc = ss.SmoobuService(slot=1)

    assert svc.sync_from is None
    assert svc._too_old(datetime(2020, 1, 1)) is False


def test_old_threads_are_skipped_without_an_api_call(app, monkeypatch):
    """The sweep must not fetch messages for pre-cutoff threads every cycle."""
    svc = _svc_with_cutoff('2026-08-10T12:00:00')

    monkeypatch.setattr(svc, 'get_threads', lambda page, page_size: {
        'page_count': 1,
        'threads': [
            {'booking': {'id': 1}, 'latest_message': {'id': 9, 'created_at': '2025-01-01 10:00:00'}},
            {'booking': {'id': 2}, 'latest_message': {'id': 8, 'created_at': '2026-08-11 10:00:00'}},
        ],
    })
    fetched = []
    monkeypatch.setattr(svc, 'sync_conversation_messages',
                        lambda rid: fetched.append(rid) or {'imported': 0})

    result = svc.sync_recent_threads(max_pages=1)

    assert fetched == ['2']              # only the thread newer than the cutoff
    assert result['threads_seen'] == 2


# =============================================================================
# Rate-limit header handling
# =============================================================================

def _fake_response(status=200, remaining='995', retry_after='9999999999'):
    class R:
        status_code = status
        headers = {'X-RateLimit-Remaining': remaining,
                   'X-RateLimit-Retry-After': retry_after}
        text = '{}'

        def json(self):
            return {}
    return R()


def test_retry_after_on_a_healthy_response_does_not_stall_the_next_call(app, monkeypatch):
    """Smoobu sends X-RateLimit-Retry-After on EVERY response — it is the window
    reset time, not a block. Honouring it on a 200 made every call sleep 60s."""
    AISettings.set('smoobu_api_key', 'k')
    svc = ss.SmoobuService(slot=1)
    monkeypatch.setattr(ss.requests, 'request', lambda *a, **kw: _fake_response())

    svc._request('GET', '/apartments')

    assert svc._rate_limit_retry_after is None


def test_retry_after_is_honoured_on_a_429(app, monkeypatch):
    AISettings.set('smoobu_api_key', 'k')
    svc = ss.SmoobuService(slot=1)
    monkeypatch.setattr(ss.requests, 'request',
                        lambda *a, **kw: _fake_response(status=429, remaining='0'))
    monkeypatch.setattr(ss.time if hasattr(ss, 'time') else __import__('time'),
                        'sleep', lambda s: None)

    svc._request('GET', '/apartments', allow_retry=False)

    assert svc._rate_limit_retry_after == 9999999999.0
