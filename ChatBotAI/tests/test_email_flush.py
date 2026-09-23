import pytest
from datetime import datetime
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, EmailBackfillCandidate, Guest, Conversation, Message
from ChatBotAI.services.email_reconcile import promote_email_candidates


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def _conv_with_candidate(confidence, gmail_id, text="Hallo", ts=None):
    guest = Guest(name="Test Gast")
    db.session.add(guest)
    db.session.flush()
    conv = Conversation(guest_id=guest.id, platform="booking")
    db.session.add(conv)
    db.session.flush()
    cand = EmailBackfillCandidate(
        gmail_message_id=gmail_id, platform="booking", parsed_name="Test Gast",
        parsed_text=text, parsed_timestamp=ts or datetime(2026, 6, 9, 12, 0, 0),
        guessed_conversation_id=conv.id, confidence=confidence, status="pending",
    )
    db.session.add(cand)
    db.session.commit()
    return conv, cand


def test_promote_returns_inserted_message_ids(app):
    conv, cand = _conv_with_candidate(0.9, "gmail-1")
    ids = promote_email_candidates(conv.id, 0.8)
    assert isinstance(ids, list)
    assert len(ids) == 1
    msg = Message.query.get(ids[0])
    assert msg.platform_message_id == "email:gmail-1"
    assert EmailBackfillCandidate.query.get(cand.id).status == "confirmed"


import json
from ChatBotAI.models import AISettings
from ChatBotAI.services.email_reconcile import promote_all_email_candidates


def test_flush_all_inserts_only_above_floor_and_records_ids(app):
    conv_hi, _ = _conv_with_candidate(0.9, "gmail-hi")
    conv_lo, cand_lo = _conv_with_candidate(0.5, "gmail-lo")
    # a pending high-conf candidate with no conversation -> counted as skipped
    orphan = EmailBackfillCandidate(
        gmail_message_id="gmail-orphan", platform="booking", parsed_name="X",
        parsed_text="hi", parsed_timestamp=datetime(2026, 6, 9, 12, 0, 0),
        guessed_conversation_id=None, confidence=0.95, status="pending",
    )
    db.session.add(orphan)
    db.session.commit()

    result = promote_all_email_candidates(0.8)

    assert result['inserted'] == 1
    assert result['conversations'] == 1
    assert result['skipped_no_conv'] == 1
    # low-conf untouched
    assert EmailBackfillCandidate.query.get(cand_lo.id).status == "pending"
    # recorded ids match the one inserted message
    recorded = json.loads(AISettings.get('email_last_flush_message_ids', '[]'))
    assert len(recorded) == 1
    assert Message.query.get(recorded[0]).platform_message_id == "email:gmail-hi"


from ChatBotAI.services.email_reconcile import undo_last_flush


def test_undo_removes_flush_and_restores_candidates(app):
    conv, cand = _conv_with_candidate(0.9, "gmail-u")
    promote_all_email_candidates(0.8)
    assert Message.query.filter_by(platform_message_id="email:gmail-u").count() == 1

    removed = undo_last_flush()

    assert removed == 1
    assert Message.query.filter_by(platform_message_id="email:gmail-u").count() == 0
    assert EmailBackfillCandidate.query.get(cand.id).status == "pending"
    # second undo is a no-op
    assert undo_last_flush() == 0


@pytest.fixture
def client(app):
    return app.test_client()


def _login_admin(app, client):
    from ChatBotAI.models import User
    # display_name and password_hash are NOT NULL on User; set_password fills the latter.
    user = User(username="admin", display_name="Admin", is_admin=True)
    user.set_password("pw")
    db.session.add(user)
    db.session.commit()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
    return user


def test_flush_and_undo_routes(app, client):
    _login_admin(app, client)
    conv, cand = _conv_with_candidate(0.9, "gmail-route")

    r = client.post('/chatbot/api/email-reconcile/flush-all')
    assert r.status_code == 200
    data = r.get_json()
    assert data['inserted'] == 1

    r2 = client.post('/chatbot/api/email-reconcile/undo-flush')
    assert r2.get_json()['removed'] == 1
    assert EmailBackfillCandidate.query.get(cand.id).status == "pending"


def test_empty_reflush_preserves_undo_record(app):
    # A second flush that inserts nothing must NOT clobber the previous flush's
    # undo record (else the first flush's inserts become unrecoverable).
    conv, cand = _conv_with_candidate(0.9, "gmail-keep")
    promote_all_email_candidates(0.8)  # flush A inserts 1, records its id
    recorded = json.loads(AISettings.get('email_last_flush_message_ids', '[]'))
    assert len(recorded) == 1

    result_b = promote_all_email_candidates(0.8)  # nothing pending now
    assert result_b['inserted'] == 0
    # record unchanged, not wiped to []
    assert json.loads(AISettings.get('email_last_flush_message_ids', '[]')) == recorded
    # undo still reverts flush A
    assert undo_last_flush() == 1
    assert EmailBackfillCandidate.query.get(cand.id).status == "pending"
