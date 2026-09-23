import json
from unittest.mock import Mock

import pytest
from flask import Flask

from ChatBotAI.services.smoobu_service import SmoobuService


@pytest.fixture
def audit_app(tmp_path):
    app = Flask('delivery-test', instance_path=str(tmp_path))
    app.testing = True
    with app.app_context():
        yield app


def events(app):
    from pathlib import Path
    return [json.loads(line) for line in
            (Path(app.instance_path) / 'delivery_attempts.jsonl').read_text().splitlines()]


def test_failure_evidence_survives_successful_retry(audit_app, monkeypatch):
    svc = SmoobuService(api_key='private-api-secret', slot=2)
    reject = Mock(status_code=429)
    accept = Mock(status_code=201)
    accept.json.return_value = {'success': True}
    request = Mock(side_effect=[reject, accept])
    monkeypatch.setattr(svc, '_request', request)
    content = 'Private guest message that must not appear in logs'
    assert svc.send_message(123, content) is None
    assert svc.send_message(123, content) == {'success': True}
    rows = events(audit_app)
    assert [r['event'] for r in rows] == ['started','finished','started','finished']
    assert rows[0]['account_slot'] == 2
    assert rows[0]['attempt_id'] == rows[1]['attempt_id']
    assert rows[2]['attempt_id'] == rows[3]['attempt_id']
    assert rows[0]['attempt_id'] != rows[2]['attempt_id']
    assert rows[1]['outcome'] == 'rejected' and rows[1]['http_status'] == 429
    assert rows[3]['outcome'] == 'accepted'
    assert content not in json.dumps(rows) and 'private-api-secret' not in json.dumps(rows)
    assert request.call_count == 2
    assert all(call.kwargs['allow_retry'] is False for call in request.call_args_list)


@pytest.mark.parametrize('response', [None, Mock(status_code=503)])
def test_ambiguous_delivery_stays_unknown(audit_app, monkeypatch, response):
    svc = SmoobuService(api_key='test')
    monkeypatch.setattr(svc, '_request', Mock(return_value=response))
    assert svc.send_message(1, 'hello') is None
    assert events(audit_app)[-1]['outcome'] == 'unknown'


def test_unparseable_success_response_is_audited_without_retry(audit_app, monkeypatch):
    svc = SmoobuService(api_key='test')
    response = Mock(status_code=200)
    response.json.side_effect = ValueError('invalid response body with sensitive content')
    request = Mock(return_value=response)
    monkeypatch.setattr(svc, '_request', request)
    with pytest.raises(ValueError):
        svc.send_message(1, 'hello')
    row = events(audit_app)[-1]
    assert row['outcome'] == 'unknown' and row['http_status'] == 200
    assert row['error_type'] == 'ValueError'
    assert 'sensitive' not in json.dumps(row)
    request.assert_called_once()


def test_audit_filesystem_error_does_not_report_successful_send_as_failure(audit_app, monkeypatch):
    from pathlib import Path
    bad_directory = Path(audit_app.instance_path) / 'a-file'
    bad_directory.write_text('not a directory')
    audit_app.config['CHATBOT_LOG_DIR'] = str(bad_directory)
    svc = SmoobuService(api_key='test')
    response = Mock(status_code=200)
    response.json.return_value = {'success': True}
    request = Mock(return_value=response)
    monkeypatch.setattr(svc, '_request', request)
    assert svc.send_message(1, 'hello') == {'success': True}
    request.assert_called_once()
