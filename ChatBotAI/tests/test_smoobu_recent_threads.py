"""/threads recency sweep: sync_recent_threads() must fetch a thread only when
its newest message (latest_message.id) is NOT already stored — i.e. brand-new
threads (no conversation) and threads with a newer message get synced, while an
already-in-sync thread is skipped (no per-reservation fetch). This is what makes
the sweep cheap enough to run every daemon cycle while still mirroring the
Smoobu inbox (which is backed by /threads)."""
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


def _thread(res_id, latest_msg_id):
    return {
        'booking': {'id': res_id, 'guest_name': f'Guest{res_id}'},
        'apartment': {'id': 999, 'name': 'A1'},
        'latest_message': {'id': latest_msg_id, 'text_content': 'hi'},
    }


def test_recent_threads_syncs_only_out_of_sync(app):
    # Thread 300: conversation exists AND its newest message (id 55) is stored -> skip.
    g1 = Guest(name='Guest300')
    db.session.add(g1)
    db.session.flush()
    conv300 = Conversation(guest_id=g1.id, platform='smoobu', platform_id='smoobu-300')
    db.session.add(conv300)
    db.session.flush()
    db.session.add(Message(conversation_id=conv300.id, sender_type='owner',
                           content='stored', platform_message_id='smoobu-300-55',
                           sent_at=datetime(2026, 7, 9, 10, 0, 0)))

    # Thread 500: conversation exists but newest message (id 99) is NOT stored -> sync.
    g2 = Guest(name='Guest500')
    db.session.add(g2)
    db.session.flush()
    conv500 = Conversation(guest_id=g2.id, platform='smoobu', platform_id='smoobu-500')
    db.session.add(conv500)
    db.session.flush()
    db.session.add(Message(conversation_id=conv500.id, sender_type='owner',
                           content='old', platform_message_id='smoobu-500-1',
                           sent_at=datetime(2026, 7, 9, 9, 0, 0)))
    db.session.commit()

    s = SmoobuService(api_key='test-key')
    # Thread 400 has no conversation at all -> new -> must sync.
    s.get_threads = MagicMock(return_value={
        'page_count': 1,
        'threads': [_thread(300, 55), _thread(400, 77), _thread(500, 99)],
    })
    s.sync_conversation_messages = MagicMock(return_value={'success': True, 'imported': 1})

    result = s.sync_recent_threads()

    synced_rids = {call.args[0] for call in s.sync_conversation_messages.call_args_list}
    assert '300' not in synced_rids, "in-sync thread must NOT be fetched"
    assert synced_rids == {'400', '500'}, "new + updated threads must be fetched"
    assert result['threads_seen'] == 3
    assert result['synced'] == 2
    assert result['imported'] == 2


def test_recent_threads_max_pages_limits_walk(app):
    s = SmoobuService(api_key='test-key')
    # No page_count in the response -> the walk is bounded by max_pages.
    s.get_threads = MagicMock(return_value={'threads': [_thread(1, 1)]})
    s.sync_conversation_messages = MagicMock(return_value={'success': True, 'imported': 0})

    s.sync_recent_threads(max_pages=3)

    assert s.get_threads.call_count == 3, "max_pages must cap the number of /threads pages walked"


def test_owner_only_thread_creates_conversation(app):
    """An owner-outbound-only thread (host welcome / invoice / marketing on a
    brand-new booking, no guest reply) must create the conversation. This is the
    regression that made freshly-created chats invisible: the webhook delivered
    a newMessage(sender=host) but sync_conversation_messages did `if not conv:
    continue` and dropped it."""
    s = SmoobuService(api_key='test-key')
    s.get_reservation = MagicMock(return_value={
        'id': 700, 'firstname': 'Thor', 'lastname': 'Bjorn',
        'email': 'thor@example.com', 'apartment': {'id': 999, 'name': 'A1'},
        'arrival': '2026-07-11', 'departure': '2026-07-13', 'adults': 2,
    })
    s.get_all_reservation_messages = MagicMock(return_value={
        'total_items': 1,
        'messages': [{'id': 55, 'type': 2, 'message': 'Hey Thor, welcome!',
                      'created_at': '2026-07-09 12:00:00'}],
    })

    result = s.sync_conversation_messages('700', force=True)

    conv = Conversation.query.filter_by(platform_id='smoobu-700').first()
    assert conv is not None, "owner-only thread must create a conversation"
    msgs = Message.query.filter_by(conversation_id=conv.id).all()
    assert len(msgs) == 1
    assert msgs[0].sender_type == 'owner'
    assert msgs[0].content == 'Hey Thor, welcome!'
    assert result['imported'] == 1
