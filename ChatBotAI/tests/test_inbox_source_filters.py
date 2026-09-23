"""Inbox channel/account filters must run server-side: the inbox is paginated, so a
client-side filter over the loaded page leaves the rest hidden behind 'Load More'.

Also pins the two traps: 'Direct booking' must not count as Booking.com, and the
primary account must include rows whose smoobu_account_id is still NULL."""
import pytest
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Guest, GuestDetail, Conversation, User, AISettings


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    user = User(username='t', display_name='T', is_admin=True)
    user.set_password('pw'); db.session.add(user); db.session.commit()
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(user.id); s['_fresh'] = True
    return c


def _conv(channel=None, account='385537'):
    g = Guest(name='G'); db.session.add(g); db.session.flush()
    if channel:
        db.session.add(GuestDetail(guest_id=g.id, detail_type='booking', detail_key='booking_channel',
                                   detail_value=channel))
    c = Conversation(guest_id=g.id, platform='smoobu', smoobu_account_id=account)
    db.session.add(c); db.session.commit()
    return c


def _ids(client, qs):
    r = client.get(f'/chatbot/api/conversations?{qs}')
    assert r.status_code == 200
    return {c['id'] for c in r.get_json()['conversations']}


def test_channel_filter_separates_booking_airbnb_and_direct(client, app):
    booking = _conv('Booking.com')
    airbnb = _conv('Airbnb')
    direct = _conv('Direct booking')

    assert _ids(client, 'channel=booking') == {booking.id}
    assert _ids(client, 'channel=airbnb') == {airbnb.id}
    assert _ids(client, 'channel=direct') == {direct.id}
    assert _ids(client, '') == {booking.id, airbnb.id, direct.id}


def test_account_filter_and_combination(client, app):
    AISettings.set('smoobu_account_id', '385537')
    main_booking = _conv('Booking.com', account='385537')
    main_airbnb = _conv('Airbnb', account='385537')
    sonnenhof = _conv('Booking.com', account='1782807')
    untagged = _conv('Booking.com', account=None)  # pre-multi-account row = primary

    assert _ids(client, 'account=1782807') == {sonnenhof.id}
    assert _ids(client, 'account=385537') == {main_booking.id, main_airbnb.id, untagged.id}
    # The point of the feature: Booking messages of the main account only.
    assert _ids(client, 'channel=booking&account=385537') == {main_booking.id, untagged.id}


def test_unknown_channel_is_ignored(client, app):
    c = _conv('Booking.com')
    assert _ids(client, 'channel=bogus') == {c.id}
