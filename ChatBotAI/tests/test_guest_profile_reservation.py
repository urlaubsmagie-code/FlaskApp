"""Smoobu reservation data (detail_type 'reservation') must show on the guest profile.
It was stored for ~4,100 guests but the profile only rendered 'booking'."""
import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Guest, GuestDetail, User


@pytest.fixture
def client():
    app = create_app(config_map['testing'])
    with app.app_context():
        user = User(username='tester', display_name='Tester', is_admin=True)
        user.set_password('pw')
        guest = Guest(name='Maxim Oehm')
        db.session.add_all([user, guest])
        db.session.commit()
        for key, value in [('booking_channel', 'Booking.com'), ('adults', '2'),
                           ('check_out', '2026-09-24'), ('check_in', '2026-09-20')]:
            db.session.add(GuestDetail(guest_id=guest.id, detail_type='reservation',
                                       detail_key=key, detail_value=value, confidence=1.0))
        db.session.commit()
        c = app.test_client()
        with c.session_transaction() as s:
            s['_user_id'] = str(user.id)
            s['_fresh'] = True
        yield c, guest.id
        db.session.remove()
        db.drop_all()


def test_reservation_details_show_in_buchungsdetails(client):
    c, guest_id = client
    html = c.get(f'/chatbot/guest/{guest_id}').get_data(as_text=True)
    booking = html[html.index('id="bookingItems"'):]
    booking = booking[:booking.index('memory-add-form')]
    assert 'Keine Buchungsdetails erfasst' not in booking
    # Arrival first, channel last — the order the team reads a booking in.
    assert booking.index('Anreise') < booking.index('Abreise') < booking.index('Erwachsene') < booking.index('Kanal')
    assert '2026-09-20' in booking and 'Booking.com' in booking
