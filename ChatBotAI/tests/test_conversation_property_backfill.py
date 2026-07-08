"""Webhook-first Smoobu conversations start with property_id=NULL (the inbox
then shows "Reservation <id>" instead of the apartment name). When a later
message for the same conversation carries a resolved property_id, the
conversation must be healed in place.

Regression test for the 2026-06-26 "Reservation N instead of apartment" bug.
"""
import pytest
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Guest, Property, Conversation
from ChatBotAI.services.message_router import MessageRouter


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def _make_guest():
    g = Guest(name="Martin Kriz", email=None)
    db.session.add(g)
    db.session.commit()
    return g


def test_existing_null_property_conversation_is_backfilled(app):
    """A conversation created without a property (webhook-first) gets its
    property_id backfilled when a later call supplies one."""
    router = MessageRouter()
    guest = _make_guest()
    prop = Property(name="Seb1 - Zi2", smoobu_apartment_id="99001")
    db.session.add(prop)
    db.session.commit()

    # First touch: webhook path, no property_id -> NULL
    conv = router._find_or_create_conversation(
        guest_id=guest.id,
        platform='smoobu',
        platform_id='smoobu-144880391',
        subject='Reservation 144880391',
        property_id=None,
    )
    assert conv.property_id is None  # the bug state

    # Later message carries the resolved property -> must heal in place
    conv2 = router._find_or_create_conversation(
        guest_id=guest.id,
        platform='smoobu',
        platform_id='smoobu-144880391',
        subject='Reservation 144880391',
        property_id=prop.id,
    )
    assert conv2.id == conv.id            # same conversation
    assert conv2.property_id == prop.id   # healed


def test_resolve_property_id_from_thread_apartment(app):
    """The service resolves a property_id from a thread's nested apartment dict."""
    from ChatBotAI.services.smoobu_service import SmoobuService
    prop = Property(name="LH2 - L5", smoobu_apartment_id="2468")
    db.session.add(prop)
    db.session.commit()

    svc = SmoobuService(api_key="test")
    # nested apartment dict (reservation/thread shape)
    assert svc._resolve_property_id({'apartment': {'id': 2468}}) == prop.id
    # flat apartmentId fallback
    assert svc._resolve_property_id({'apartmentId': '2468'}) == prop.id
    # unknown apartment -> None
    assert svc._resolve_property_id({'apartment': {'id': 777}}) is None
    # no apartment info -> None
    assert svc._resolve_property_id({}) is None


def test_existing_property_is_not_overwritten(app):
    """If a conversation already has a property, a later call with a different
    property_id must NOT clobber it."""
    router = MessageRouter()
    guest = _make_guest()
    prop_a = Property(name="Seb1 - Zi2", smoobu_apartment_id="99001")
    prop_b = Property(name="LH2 - L5", smoobu_apartment_id="99002")
    db.session.add_all([prop_a, prop_b])
    db.session.commit()

    conv = router._find_or_create_conversation(
        guest_id=guest.id, platform='smoobu', platform_id='smoobu-1',
        subject='Reservation 1', property_id=prop_a.id,
    )
    assert conv.property_id == prop_a.id

    conv2 = router._find_or_create_conversation(
        guest_id=guest.id, platform='smoobu', platform_id='smoobu-1',
        subject='Reservation 1', property_id=prop_b.id,
    )
    assert conv2.property_id == prop_a.id  # unchanged
