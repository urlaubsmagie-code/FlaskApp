"""modifiedAt fast-path: an unchanged existing conversation must NOT trigger a
per-reservation message fetch (that fan-out is what wedged the sweep on Smoobu's
rate limit); a new reservation still must be fetched so outbound-only chats get
created."""
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Guest, Conversation, Message
from ChatBotAI.services.smoobu_service import SmoobuService


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def _reservation(res_id, modified_at):
    return {
        'id': res_id, 'first-name': 'Test', 'last-name': f'Guest{res_id}',
        'apartment': {'id': 999}, 'arrival': '2026-07-01', 'departure': '2026-07-03',
        'modifiedAt': modified_at, 'adults': 2, 'children': 0,
    }


def test_unchanged_conv_skipped_new_fetched(app):
    guest = Guest(name='Test Guest100')
    db.session.add(guest)
    db.session.flush()
    conv = Conversation(guest_id=guest.id, platform='smoobu', platform_id='smoobu-100')
    db.session.add(conv)
    db.session.flush()
    # Our newest stored message is well AFTER res 100's modifiedAt -> nothing new.
    db.session.add(Message(conversation_id=conv.id, sender_type='guest',
                           content='hi', platform_message_id='smoobu-100-1',
                           sent_at=datetime(2026, 7, 1, 12, 0, 0)))
    db.session.commit()

    s = SmoobuService(api_key='test-key')
    # One page: res 100 unchanged (modifiedAt way before watermark) + res 200 new.
    s.get_reservations = MagicMock(return_value={
        'page_count': 1,
        'bookings': [_reservation(100, '2026-06-01 00:00:00'),
                     _reservation(200, '2026-07-09 00:00:00')],
    })
    s.get_reservation_messages = MagicMock(return_value=None)  # we only assert call args

    s.sync_messages(force=True)

    fetched = {call.args[0] for call in s.get_reservation_messages.call_args_list}
    assert '100' not in fetched, "unchanged conv should be skipped (no message fetch)"
    assert '200' in fetched, "new reservation must still be fetched"


def test_changed_conv_is_fetched(app):
    guest = Guest(name='Test Guest100')
    db.session.add(guest)
    db.session.flush()
    conv = Conversation(guest_id=guest.id, platform='smoobu', platform_id='smoobu-100')
    db.session.add(conv)
    db.session.flush()
    db.session.add(Message(conversation_id=conv.id, sender_type='guest',
                           content='hi', platform_message_id='smoobu-100-1',
                           sent_at=datetime(2026, 7, 1, 12, 0, 0)))
    db.session.commit()

    s = SmoobuService(api_key='test-key')
    # modifiedAt AFTER our newest message -> reservation changed -> must fetch.
    s.get_reservations = MagicMock(return_value={
        'page_count': 1, 'bookings': [_reservation(100, '2026-07-05 00:00:00')],
    })
    s.get_reservation_messages = MagicMock(return_value=None)

    s.sync_messages(force=True)

    fetched = {call.args[0] for call in s.get_reservation_messages.call_args_list}
    assert '100' in fetched, "changed reservation must be fetched"
