from collections import namedtuple

from ChatBotAI.services.guest_matching import (
    normalize_email, normalize_phone, normalize_name,
)
from ChatBotAI.services.guest_matching import build_merge_groups

Row = namedtuple("Row", "id email phone name")


def test_normalize_email():
    assert normalize_email("  Bob@EXAMPLE.com ") == "bob@example.com"
    assert normalize_email("") is None
    assert normalize_email(None) is None


def test_normalize_phone():
    assert normalize_phone("+49 (170) 123-4567") == "491701234567"
    assert normalize_phone("  ") is None
    assert normalize_phone(None) is None


def test_normalize_name():
    assert normalize_name("  Steven   Amaya ") == "steven amaya"
    assert normalize_name("STEVEN AMAYA") == normalize_name("steven amaya")
    assert normalize_name("") is None
    assert normalize_name(None) is None


def test_groups_name_only_duplicates():
    rows = [
        Row(1, None, None, "Steven Amaya"),
        Row(2, None, None, "steven amaya"),
        Row(3, None, None, "Nathalie Roos"),
    ]
    groups, conflicts = build_merge_groups(rows)
    assert groups == [[1, 2]]
    assert conflicts == []


def test_groups_by_email_and_phone():
    rows = [
        Row(1, "a@x.com", None, "A One"),
        Row(2, "A@X.COM", None, "Totally Different"),   # same email -> merge
        Row(3, None, "0170-5", "B Two"),
        Row(4, None, "0170 5", "B Two"),                 # same phone digits -> merge
    ]
    groups, conflicts = build_merge_groups(rows)
    assert [1, 2] in groups
    assert [3, 4] in groups


def test_skips_name_group_with_conflicting_email():
    rows = [
        Row(1, "real1@x.com", None, "Benjamin Schmidt"),
        Row(2, "real2@x.com", None, "Benjamin Schmidt"),  # different emails, same name
        Row(3, None, None, "Benjamin Schmidt"),
    ]
    groups, conflicts = build_merge_groups(rows)
    assert groups == []                       # name union skipped
    assert len(conflicts) == 1
    assert conflicts[0]["name"] == "benjamin schmidt"
    assert sorted(conflicts[0]["emails"]) == ["real1@x.com", "real2@x.com"]


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


def test_find_by_email_case_insensitive(app):
    db.session.add(Guest(name="Bob", email="bob@x.com"))
    db.session.commit()
    found = find_existing_guest(email="BOB@X.COM", name="Whatever")
    assert found is not None and found.email == "bob@x.com"


def test_find_by_name_only_when_no_conflict(app):
    db.session.add(Guest(name="Steven Amaya"))
    db.session.commit()
    assert find_existing_guest(name="steven amaya") is not None


def test_no_name_match_when_email_conflicts(app):
    db.session.add(Guest(name="Steven Amaya", email="real@x.com"))
    db.session.commit()
    # incoming has a DIFFERENT email -> must not attach to the existing row
    assert find_existing_guest(email="other@x.com", name="Steven Amaya") is None


def test_returns_none_when_nothing_matches(app):
    assert find_existing_guest(email="nobody@x.com", name="Ghost") is None
