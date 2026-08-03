import pytest
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, Property, KnowledgeEntry, street_from_address


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def test_street_from_address():
    assert street_from_address('Hertigswalder Str. 27, 01855, Sebnitz, Germany') == 'Hertigswalder Str. 27'
    assert street_from_address('Bergblick 11, 01855, Lichtenhain') == 'Bergblick 11'
    assert street_from_address('') == ''
    assert street_from_address(None) == ''


def test_street_columns_persist(app):
    p = Property(name='F3', address='Hertigswalder Str. 27, 01855, Sebnitz', street='Hertigswalder Str. 27')
    db.session.add(p); db.session.commit()
    k = KnowledgeEntry(category='general', label='Müll', value='Dienstags', street='Hertigswalder Str. 27')
    db.session.add(k); db.session.commit()
    assert Property.query.first().street == 'Hertigswalder Str. 27'
    got = KnowledgeEntry.query.first()
    assert got.street == 'Hertigswalder Str. 27'
    assert got.to_dict()['street'] == 'Hertigswalder Str. 27'
