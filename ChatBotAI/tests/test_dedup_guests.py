import pytest
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Guest, Conversation, GuestDetail
from ChatBotAI.scripts.dedup_guests import merge_group
from ChatBotAI.scripts.dedup_guests import run_dedup


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def test_merge_reassigns_fks_and_backfills(app):
    # loser has the contact info + a conversation; winner picked by contact/conv
    g1 = Guest(name="Steven Amaya")                       # id 1, no contact
    g2 = Guest(name="Steven Amaya", email="s@x.com")      # id 2, has email
    db.session.add_all([g1, g2])
    db.session.commit()
    db.session.add(Conversation(guest_id=g1.id, platform="smoobu", platform_id="c1"))
    db.session.add(GuestDetail(guest_id=g1.id, detail_type="pet", detail_key="dog", detail_value="Max"))
    db.session.add(GuestDetail(guest_id=g2.id, detail_type="pet", detail_key="dog", detail_value="Max"))
    db.session.commit()

    winner_id, loser_ids = merge_group([g1.id, g2.id])
    db.session.commit()

    assert winner_id == g2.id                 # g2 has email -> richer
    assert loser_ids == [g1.id]
    assert Guest.query.count() == 1
    assert Guest.query.get(g2.id).email == "s@x.com"
    # conversation reassigned, no orphans
    assert Conversation.query.filter_by(guest_id=g2.id).count() == 1
    assert Conversation.query.filter_by(guest_id=g1.id).count() == 0
    # identical details deduped to one
    assert GuestDetail.query.filter_by(guest_id=g2.id).count() == 1


def test_merge_backfills_email_onto_winner_without_unique_clash(app):
    # Winner has a phone + more conversations; loser carries the (unique) email.
    # The winner lacks an email and must be backfilled from the loser, which
    # requires deleting the loser BEFORE setting the winner's email so the
    # unique-email constraint is not violated mid-transaction.
    g1 = Guest(name="A", phone="0170")         # winner: has phone, 2 convs, no email
    g2 = Guest(name="A", email="a@x.com")      # loser: has email, 0 convs
    db.session.add_all([g1, g2])
    db.session.commit()
    db.session.add_all([
        Conversation(guest_id=g1.id, platform="smoobu", platform_id="x1"),
        Conversation(guest_id=g1.id, platform="smoobu", platform_id="x2"),
    ])
    db.session.commit()

    winner_id, loser_ids = merge_group([g1.id, g2.id])
    db.session.commit()

    assert winner_id == g1.id                          # both have contact; g1 wins on conv count
    assert Guest.query.get(g1.id).email == "a@x.com"   # backfilled, no IntegrityError
    assert Guest.query.get(g1.id).phone == "0170"      # winner keeps its phone
    assert Guest.query.count() == 1


def test_run_dedup_merges_and_is_idempotent(app):
    db.session.add_all([
        Guest(name="Nathalie Roos"),
        Guest(name="nathalie roos"),
        Guest(name="Nathalie Roos"),
        Guest(name="Unique Person"),
    ])
    db.session.commit()

    result = run_dedup(apply=True)
    db.session.commit()
    assert result["groups"] == 1
    assert result["deleted"] == 2
    assert Guest.query.count() == 2          # 1 merged Roos + 1 unique

    # second pass finds nothing
    again = run_dedup(apply=True)
    db.session.commit()
    assert again["groups"] == 0
    assert again["deleted"] == 0


def test_run_dedup_reports_conflicts_without_merging(app):
    db.session.add_all([
        Guest(name="Benjamin Schmidt", email="b1@x.com"),
        Guest(name="Benjamin Schmidt", email="b2@x.com"),
    ])
    db.session.commit()
    result = run_dedup(apply=False)         # dry-run
    assert result["groups"] == 0
    assert result["conflicts"] == 1
    assert Guest.query.count() == 2          # untouched
