"""Problem Report feature — model + route tests."""
import pytest

from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, ProblemReport, User


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    user = User(username='reporter', display_name='Reporter', is_admin=True)
    user.set_password('pw')
    db.session.add(user)
    db.session.commit()
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(user.id)
        s['_fresh'] = True
    return c


def test_problem_report_roundtrip(app):
    u = User(username='u1', display_name='U One')
    u.set_password('pw')
    db.session.add(u)
    db.session.commit()
    r = ProblemReport(user_id=u.id, category='bug', message='Suche ist langsam')
    db.session.add(r)
    db.session.commit()
    got = ProblemReport.query.first()
    assert got.status == 'open'
    assert got.category == 'bug'
    assert got.reporter.display_name == 'U One'
    assert got.to_dict()['reporter_name'] == 'U One'


def test_create_rejects_empty_message(client):
    resp = client.post('/chatbot/api/problem-reports',
                       json={'message': '   ', 'category': 'bug'})
    assert resp.status_code == 400


def test_create_rejects_bad_category(client):
    resp = client.post('/chatbot/api/problem-reports',
                       json={'message': 'x', 'category': 'nonsense'})
    assert resp.status_code == 400


def test_create_persists_and_counts(client, app):
    resp = client.post('/chatbot/api/problem-reports',
                       json={'message': 'Gast schrieb, kein Chat', 'category': 'missing_message',
                             'page_url': '/chatbot/'})
    assert resp.status_code == 201
    from ChatBotAI.models import ProblemReport
    row = ProblemReport.query.first()
    assert row.status == 'open'
    assert row.message == 'Gast schrieb, kein Chat'
    assert row.category == 'missing_message'

    count = client.get('/chatbot/api/problem-reports/pending-count').get_json()['count']
    assert count == 1


def _non_admin_client(app):
    u = User(username='plain', display_name='Plain', is_admin=False)
    u.set_password('pw')
    db.session.add(u)
    db.session.commit()
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u.id)
        s['_fresh'] = True
    return c


def test_resolve_toggles_status(client, app):
    from ChatBotAI.models import ProblemReport
    client.post('/chatbot/api/problem-reports', json={'message': 'x', 'category': 'idea'})
    rid = ProblemReport.query.first().id
    resp = client.post(f'/chatbot/api/problem-reports/{rid}/resolve')
    assert resp.status_code == 200
    row = ProblemReport.query.get(rid)
    assert row.status == 'resolved'
    assert row.resolved_at is not None
    # toggle back
    client.post(f'/chatbot/api/problem-reports/{rid}/resolve')
    assert ProblemReport.query.get(rid).status == 'open'
    assert ProblemReport.query.get(rid).resolved_at is None


def test_review_page_renders_for_admin(client):
    assert client.get('/chatbot/problem-reports').status_code == 200


def test_review_page_forbidden_for_non_admin(app):
    c = _non_admin_client(app)
    assert c.get('/chatbot/problem-reports').status_code in (302, 403)
