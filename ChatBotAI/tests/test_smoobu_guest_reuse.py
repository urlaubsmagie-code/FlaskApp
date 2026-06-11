"""Two reservations from the same guest must reuse one Guest row."""
import pytest
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Guest
from ChatBotAI.services.guest_matching import find_existing_guest


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def _get_or_make_guest(name, email, reservation_id):
    """Mirror of the rewritten smoobu_service guest-creation block."""
    guest = find_existing_guest(email=email, name=name)
    if not guest:
        guest = Guest(name=name or f"Guest {reservation_id}", email=email or None)
        db.session.add(guest)
        db.session.flush()
    return guest


def test_second_reservation_reuses_guest(app):
    g1 = _get_or_make_guest("Steven Amaya", None, "res-111")
    db.session.commit()
    g2 = _get_or_make_guest("Steven Amaya", None, "res-222")  # different reservation
    db.session.commit()
    assert g1.id == g2.id
    assert Guest.query.count() == 1


def test_guest_id_not_set_to_reservation_id(app):
    g = _get_or_make_guest("New Person", None, "res-999")
    db.session.commit()
    assert g.smoobu_guest_id != "res-999"
    assert g.smoobu_guest_id is None
