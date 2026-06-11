"""Regression tests for inbox sort order.

These tests pin down the bug where the inbox was sorted by
``Conversation.updated_at`` (a "polling tripwire" that gets bumped by any
change, including out-of-order syncs) instead of
``Conversation.last_message_at`` (the real timestamp of the most recent
message).

Test 1 (ORM-level) should PASS once the ``last_message_at`` column exists
(Task 1+2). Test 2 (endpoint-level) is expected to FAIL until Task 8
switches the route's ``order_by`` to ``last_message_at``.
"""

from datetime import datetime, timedelta

import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Conversation, Guest, Message, User


@pytest.fixture
def app():
    # create_app() calls Flask's app.config.from_object(), which interprets a
    # raw string as an import path. Resolve the string to the TestingConfig
    # class ourselves before handing it to the factory.
    app = create_app(config_map['testing'])
    with app.app_context():
        # _auto_upgrade_schema + db.create_all() ran inside create_app(); the
        # schema (including last_message_at) is already in place for :memory:.
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    # The /chatbot blueprint has a before_request that redirects unauth'd
    # users to /chatbot/setup (if no users exist) or /chatbot/login. To hit
    # the API directly we create an admin user and log them in via the
    # Flask-Login test session cookie.
    user = User(username='tester', display_name='Tester', is_admin=True)
    user.set_password('pw')
    db.session.add(user)
    db.session.commit()

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True
    return client


def _make_conv(name, last_msg_sent_at, updated_at=None):
    """Create a Guest + Conversation + one Message with the given timestamps.

    Both Conversation.last_message_at and Conversation.updated_at are set
    explicitly so the test exercises the sort key in isolation.
    """
    guest = Guest(name=name, email=f"{name.lower()}@example.com")
    db.session.add(guest)
    db.session.flush()
    conv = Conversation(
        guest_id=guest.id,
        platform='smoobu',
        platform_id=f"smoobu-test-{name}",
        last_message_at=last_msg_sent_at,
        updated_at=updated_at or last_msg_sent_at,
    )
    db.session.add(conv)
    db.session.flush()
    msg = Message(
        conversation_id=conv.id,
        sender_type='guest',
        content=f"hi from {name}",
        sent_at=last_msg_sent_at,
    )
    db.session.add(msg)
    db.session.commit()
    return conv


def test_orm_orders_by_last_message_at_not_updated_at(app):
    """A conversation whose last real message is older must appear BELOW a
    conversation with a newer last message — even if its updated_at is
    newer (e.g. an out-of-order sync that bumped updated_at to now)."""
    now = datetime.utcnow()
    old_conv = _make_conv(
        "Old", last_msg_sent_at=now - timedelta(days=3), updated_at=now
    )
    new_conv = _make_conv(
        "New",
        last_msg_sent_at=now - timedelta(hours=1),
        updated_at=now - timedelta(hours=1),
    )

    ordered = (
        Conversation.query
        .order_by(Conversation.last_message_at.desc())
        .all()
    )
    ids = [c.id for c in ordered]
    assert ids.index(new_conv.id) < ids.index(old_conv.id), (
        "Conversation with the newer real message must come first; "
        "updated_at must not influence sort."
    )


def test_inbox_endpoint_orders_by_last_message_at(client, app):
    """The /chatbot/api/conversations endpoint must order conversations by
    last_message_at desc, NOT updated_at desc. A conversation whose
    updated_at was bumped to ``now`` by an out-of-order sync but whose
    latest real message is days old must NOT appear at the top.

    This test will FAIL while routes.py still sorts on
    ``Conversation.updated_at.desc()`` (the bug we're fixing).
    """
    now = datetime.utcnow()

    # Bug case: oldest real message, but updated_at bumped to now.
    bumped_old = _make_conv(
        "BumpedOld",
        last_msg_sent_at=now - timedelta(days=5),
        updated_at=now,
    )
    # Genuinely newest conversation.
    newest = _make_conv(
        "Newest",
        last_msg_sent_at=now - timedelta(minutes=10),
        updated_at=now - timedelta(minutes=10),
    )
    # Middle: a day old, untouched.
    middle = _make_conv(
        "Middle",
        last_msg_sent_at=now - timedelta(days=1),
        updated_at=now - timedelta(days=1),
    )

    resp = client.get('/chatbot/api/conversations?per_page=20')
    assert resp.status_code == 200, resp.data

    payload = resp.get_json()
    returned_ids = [c['id'] for c in payload['conversations']]

    expected_order = [newest.id, middle.id, bumped_old.id]
    assert returned_ids == expected_order, (
        "Endpoint must order by last_message_at desc. "
        f"Got {returned_ids}, expected {expected_order}. "
        "If bumped_old appears first, the route is still sorting by "
        "updated_at — that's the bug."
    )
