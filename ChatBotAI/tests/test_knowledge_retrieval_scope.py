import pytest
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Property, KnowledgeEntry, Conversation, Guest


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def _load_for_property(property_id):
    """Mirror of message_router's street-aware knowledge query."""
    prop = Property.query.get(property_id)
    prop_street = prop.street if prop else None
    branches = [
        db.and_(KnowledgeEntry.property_id.is_(None), KnowledgeEntry.street.is_(None)),
        KnowledgeEntry.property_id == property_id,
    ]
    if prop_street:
        branches.append(KnowledgeEntry.street == prop_street)
    q = KnowledgeEntry.query.filter(KnowledgeEntry.category != 'correction', db.or_(*branches))
    return {e.label for e in q.all()}


def test_scope_isolation(app):
    f3 = Property(name='F3', street='Hertigswalder Str. 27'); db.session.add(f3)
    b1 = Property(name='B1', street='Bergblick 11'); db.session.add(b1)
    db.session.commit()

    db.session.add_all([
        KnowledgeEntry(category='general', label='general_fact', value='v'),  # scope: general
        KnowledgeEntry(category='general', label='street_fact', value='v', street='Hertigswalder Str. 27'),
        KnowledgeEntry(category='general', label='room_fact', value='v', property_id=f3.id),
    ])
    db.session.commit()

    f3_labels = _load_for_property(f3.id)
    assert f3_labels == {'general_fact', 'street_fact', 'room_fact'}

    b1_labels = _load_for_property(b1.id)
    assert b1_labels == {'general_fact'}  # not street_fact (other building), not room_fact


def test_classmethod_scope_isolation(app):
    """Exercises the real KnowledgeEntry.load_for_conversation_context classmethod
    (not the mirror above) via real Conversation/Guest objects."""
    f3 = Property(name='F3', street='Hertigswalder Str. 27'); db.session.add(f3)
    b1 = Property(name='B1', street='Bergblick 11'); db.session.add(b1)
    db.session.commit()

    db.session.add_all([
        KnowledgeEntry(category='general', label='general_fact', value='v'),
        KnowledgeEntry(category='general', label='street_fact', value='v', street='Hertigswalder Str. 27'),
        KnowledgeEntry(category='general', label='room_fact', value='v', property_id=f3.id),
    ])
    db.session.commit()

    guest = Guest(name='G'); db.session.add(guest)
    db.session.commit()

    f3_conv = Conversation(guest_id=guest.id, platform='airbnb', property_id=f3.id)
    b1_conv = Conversation(guest_id=guest.id, platform='airbnb', property_id=b1.id)
    db.session.add_all([f3_conv, b1_conv])
    db.session.commit()

    f3_labels = {e['label'] for e in KnowledgeEntry.load_for_conversation_context(f3_conv)}
    assert f3_labels == {'general_fact', 'street_fact', 'room_fact'}

    b1_labels = {e['label'] for e in KnowledgeEntry.load_for_conversation_context(b1_conv)}
    assert b1_labels == {'general_fact'}
