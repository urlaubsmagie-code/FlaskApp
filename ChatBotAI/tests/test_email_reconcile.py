import pytest
from datetime import datetime
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, EmailBackfillCandidate, Guest, Conversation, Message


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def test_email_backfill_candidate_roundtrip(app):
    c = EmailBackfillCandidate(
        gmail_message_id="gmail-abc",
        platform="airbnb",
        parsed_name="Rosy",
        parsed_text="Vielen Dank!",
        parsed_timestamp=datetime(2026, 6, 9, 12, 0, 0),
        guessed_conversation_id=None,
        confidence=0.42,
        status="pending",
    )
    db.session.add(c)
    db.session.commit()
    got = EmailBackfillCandidate.query.filter_by(gmail_message_id="gmail-abc").first()
    assert got is not None
    assert got.platform == "airbnb"
    assert got.status == "pending"
    assert abs(got.confidence - 0.42) < 1e-6


from ChatBotAI.services.gmail_service import GmailService


def _fake_gmail_message(headers: dict, body_text: str):
    import base64
    raw = base64.urlsafe_b64encode(body_text.encode('utf-8')).decode('ascii')
    return {
        'id': 'msg1', 'threadId': 'thr1', 'snippet': '', 'labelIds': [],
        'payload': {
            'headers': [{'name': k, 'value': v} for k, v in headers.items()],
            'mimeType': 'text/plain',
            'body': {'data': raw},
        },
    }


def test_parse_email_captures_reply_to():
    svc = GmailService.__new__(GmailService)  # no OAuth needed for pure parse
    msg = _fake_gmail_message(
        {'From': 'Airbnb <automated@airbnb.com>',
         'Reply-To': 'tok123@reply.airbnb.com',
         'Subject': 'RE: Buchung', 'To': 'urlaubsmagie@gmail.com',
         'Date': 'Mon, 09 Jun 2026 12:19:00 +0200'},
        'hello',
    )
    parsed = svc._parse_email(msg)
    assert parsed['reply_to'] == 'tok123@reply.airbnb.com'


from ChatBotAI.models import Guest, Conversation, Message
from ChatBotAI.services.email_reconcile import (
    classify_notification, score_conversation_match, pick_best_match,
)


def _email(**kw):
    base = {'id': 'g1', 'thread_id': 't1', 'subject': '', 'from': '',
            'sender_email': '', 'reply_to': '', 'to': '', 'date': '', 'body': ''}
    base.update(kw)
    return base


def test_classify_booking_by_sender():
    e = _email(sender_email='5843975682-uzs8.brju@guest.booking.com',
               body='##- Bitte schreiben Sie Ihre Antwort oberhalb dieser Zeile -##\nhi')
    assert classify_notification(e) == 'booking'


def test_classify_airbnb_by_reply_to():
    e = _email(sender_email='automated@airbnb.com',
               reply_to='4lb0qk@reply.airbnb.com',
               body='Du kannst auch direkt auf diese E-Mail antworten.')
    assert classify_notification(e) == 'airbnb'


def test_classify_rejects_booking_confirmation():
    e = _email(sender_email='noreply@booking.com', body='Ihre Buchung ist bestätigt')
    assert classify_notification(e) is None


def test_classify_rejects_airbnb_without_reply_relay():
    e = _email(sender_email='express@airbnb.com', reply_to='', body='Auszahlung gesendet')
    assert classify_notification(e) is None


from datetime import date, date as _d
from ChatBotAI.services.email_reconcile import ParsedNotification, parse_notification

BOOKING_BODY = (
    "##- Bitte schreiben Sie Ihre Antwort oberhalb dieser Zeile -##\n"
    "Sie haben eine neue Nachricht von einem Gast\n"
    "Nachricht von Carolin Janowski:\n"
    "Alles klar das habe ich nur überflogen\n"
    "Danke für die Info\n"
    "Liebe Grüße\n"
    "Antworten\n"
    "Buchungsangaben\n"
    "Name des Gastes:\nCarolin Janowski\n"
    "Check-in:\nFr., 12. Juni 2026\n"
    "Check-out:\nSo., 14. Juni 2026\n"
    "Unterkunftsname:\nUrlaubsmagie - Ferienwohnung Waldweg - mit Grill\n"
    "Buchungsnummer:\n5843975682\n"
)


def test_parse_booking_extracts_fields():
    e = _email(id='gb1', thread_id='tb1',
               sender_email='5843975682-uzs8.brju@guest.booking.com',
               date='Mon, 09 Jun 2026 13:24:00 +0200', body=BOOKING_BODY)
    n = parse_notification(e)
    assert n.platform == 'booking'
    assert n.gmail_id == 'gb1'
    assert n.guest_name == 'Carolin Janowski'
    assert 'Alles klar' in n.message_text
    assert 'Antworten' not in n.message_text
    assert n.booking_ref == '5843975682'
    assert n.check_in == date(2026, 6, 12)
    assert n.check_out == date(2026, 6, 14)
    assert 'Waldweg' in n.property_name
    # 13:24 Berlin (+0200) -> 11:24 UTC, naive
    assert n.sent_at == datetime(2026, 6, 9, 11, 24, 0)


AIRBNB_BODY = (
    "Buchung für „Pool | Sauna | Lagerfeuer - perfekter Urlaub\n"
    "Rosy\n"
    "Buchende Person\n"
    "Vielen Dank! Mein Mann und ich freuen uns, bei dir übernachten zu dürfen.\n"
    "Mit freundlichen Grüßen\n"
    "Die ursprüngliche Nachricht wurde automatisch übersetzt\n"
    "Muchas gracias! Estamos felices.\n"
    "Antworten\n"
    "Du kannst auch direkt auf diese E-Mail antworten.\n"
)


def test_parse_airbnb_extracts_fields():
    e = _email(id='ga1', thread_id='ta1',
               sender_email='automated@airbnb.com',
               reply_to='4lb0qk@reply.airbnb.com',
               subject='RE: Buchung für „Pool | Sauna | Lagerfeuer - perfekter Urlaub", 14.–16. Juni',
               date='Mon, 09 Jun 2026 12:19:00 +0200', body=AIRBNB_BODY)
    n = parse_notification(e)
    assert n.platform == 'airbnb'
    assert n.guest_name == 'Rosy'
    assert 'Vielen Dank' in n.message_text
    assert 'Antworten' not in n.message_text
    assert 'Pool | Sauna' in n.property_name
    assert n.sent_at == datetime(2026, 6, 9, 10, 19, 0)


def _booking_notif(**kw):
    base = dict(platform='booking', gmail_id='g', thread_id='t',
                guest_name='Carolin Janowski', message_text='hi',
                sent_at=datetime(2026, 6, 9, 11, 24), property_name='Ferienwohnung Waldweg',
                check_in=_d(2026, 6, 12), check_out=_d(2026, 6, 14), booking_ref='5843975682')
    base.update(kw)
    return ParsedNotification(**base)


def _conv(**kw):
    base = dict(conversation_id=1, channel='booking', guest_name='Carolin Janowski',
                property_name='Ferienwohnung Waldweg', check_in=_d(2026, 6, 12),
                check_out=_d(2026, 6, 14))
    base.update(kw)
    return base


def test_booking_full_match_is_high_confidence():
    assert score_conversation_match(_booking_notif(), _conv()) >= 0.8


def test_wrong_channel_scores_zero():
    assert score_conversation_match(_booking_notif(), _conv(channel='airbnb')) == 0.0


def test_airbnb_first_name_only_is_low_confidence():
    n = ParsedNotification(platform='airbnb', gmail_id='g', thread_id='t', guest_name='Rosy',
                           message_text='hi', sent_at=datetime(2026, 6, 9, 10, 19),
                           property_name='Pool | Sauna', check_in=None, check_out=None,
                           booking_ref=None)
    c = _conv(channel='airbnb', guest_name='Rosy Fernandez', property_name='Ferienwohnung Berg',
              check_in=None, check_out=None)
    score = score_conversation_match(n, c)
    assert 0.0 < score < 0.8


def test_pick_best_match_returns_highest():
    n = _booking_notif()
    convs = [_conv(conversation_id=1, guest_name='Someone Else'),
             _conv(conversation_id=2)]
    best, score = pick_best_match(n, convs)
    assert best['conversation_id'] == 2
    assert score >= 0.8


def test_pick_best_match_empty():
    assert pick_best_match(_booking_notif(), []) == (None, 0.0)


from ChatBotAI.models import AISettings, GuestDetail
from ChatBotAI.services.email_reconcile import has_equivalent_message, get_reconcile_config, resolve_channel


def _make_conv_with_guest_msg(sent_at):
    g = Guest(name='Carolin Janowski')
    db.session.add(g); db.session.flush()
    c = Conversation(guest_id=g.id, platform='booking')
    db.session.add(c); db.session.flush()
    if sent_at:
        m = Message(conversation_id=c.id, sender_type='guest', content='hallo', sent_at=sent_at)
        db.session.add(m)
    db.session.commit()
    return c


def test_dedup_detects_message_in_window(app):
    c = _make_conv_with_guest_msg(datetime(2026, 6, 9, 11, 25))
    n = _booking_notif(sent_at=datetime(2026, 6, 9, 11, 24))  # 1 min apart
    assert has_equivalent_message(c.id, n, window_minutes=10) is True


def test_dedup_ignores_out_of_window(app):
    c = _make_conv_with_guest_msg(datetime(2026, 6, 9, 9, 0))
    n = _booking_notif(sent_at=datetime(2026, 6, 9, 11, 24))  # >2h apart
    assert has_equivalent_message(c.id, n, window_minutes=10) is False


def test_dedup_false_when_no_guest_message(app):
    c = _make_conv_with_guest_msg(None)
    n = _booking_notif(sent_at=datetime(2026, 6, 9, 11, 24))
    assert has_equivalent_message(c.id, n, window_minutes=10) is False


def test_config_defaults(app):
    cfg = get_reconcile_config()
    assert cfg['enabled'] is False  # dormant by default — opt-in via Settings
    assert cfg['threshold'] == 0.8
    assert cfg['autoinsert_booking'] is True
    assert cfg['autoinsert_airbnb'] is False


def test_config_reads_overrides(app):
    AISettings.set('email_autoinsert_airbnb', 'true')
    AISettings.set('email_confidence_threshold', '0.6')
    cfg = get_reconcile_config()
    assert cfg['autoinsert_airbnb'] is True
    assert cfg['threshold'] == 0.6


def test_resolve_channel_from_platform(app):
    g = Guest(name='X'); db.session.add(g); db.session.flush()
    c = Conversation(guest_id=g.id, platform='booking'); db.session.add(c); db.session.commit()
    assert resolve_channel(c) == 'booking'


def test_resolve_channel_from_guest_detail(app):
    g = Guest(name='Y'); db.session.add(g); db.session.flush()
    c = Conversation(guest_id=g.id, platform='smoobu'); db.session.add(c); db.session.flush()
    db.session.add(GuestDetail(guest_id=g.id, detail_type='preference',
                               detail_key='booking_channel', detail_value='Airbnb'))
    db.session.commit()
    assert resolve_channel(c) == 'airbnb'


# ---------------------------------------------------------------------------
# Task 8: Orchestrator reconcile_from_email
# ---------------------------------------------------------------------------

from ChatBotAI.services.email_reconcile import reconcile_from_email


class FakeGmail:
    """Returns canned emails per query."""
    def __init__(self, by_query):
        self._by_query = by_query
    def get_recent_emails(self, max_results=10, query=None, apply_filter=True):
        return self._by_query.get(query, [])


def test_orchestrator_autoinserts_high_confidence_booking(app):
    g = Guest(name='Carolin Janowski'); db.session.add(g); db.session.flush()
    conv = Conversation(guest_id=g.id, platform='booking',
                        check_in=_d(2026, 6, 12), check_out=_d(2026, 6, 14))
    db.session.add(conv); db.session.commit()

    email = _email(id='gb1', thread_id='tb1',
                   sender_email='5843975682-x@guest.booking.com',
                   date='Mon, 09 Jun 2026 13:24:00 +0200', body=BOOKING_BODY)
    gmail = FakeGmail({'from:guest.booking.com newer_than:90d': [email]})

    AISettings.set('email_reconcile_enabled', 'true')  # feature is dormant by default
    stats = reconcile_from_email(gmail)

    assert stats['auto_inserted'] == 1
    msgs = Message.query.filter_by(conversation_id=conv.id).all()
    assert len(msgs) == 1
    assert msgs[0].platform_message_id == 'email:gb1'
    assert 'Alles klar' in msgs[0].content


def test_orchestrator_queues_low_confidence_airbnb(app):
    g = Guest(name='Rosy Fernandez'); db.session.add(g); db.session.flush()
    conv = Conversation(guest_id=g.id, platform='airbnb')
    db.session.add(conv); db.session.commit()

    email = _email(id='ga1', thread_id='ta1', sender_email='automated@airbnb.com',
                   reply_to='tok@reply.airbnb.com',
                   subject='RE: Buchung für „Pool | Sauna", 14.–16. Juni',
                   date='Mon, 09 Jun 2026 12:19:00 +0200', body=AIRBNB_BODY)
    gmail = FakeGmail({'from:airbnb.com newer_than:90d': [email]})

    AISettings.set('email_reconcile_enabled', 'true')  # feature is dormant by default
    stats = reconcile_from_email(gmail)

    assert stats['queued'] == 1
    assert Message.query.filter_by(conversation_id=conv.id).count() == 0
    cand = EmailBackfillCandidate.query.filter_by(gmail_message_id='ga1').first()
    assert cand is not None and cand.status == 'pending'


def test_orchestrator_skips_duplicates(app):
    g = Guest(name='Carolin Janowski'); db.session.add(g); db.session.flush()
    conv = Conversation(guest_id=g.id, platform='booking',
                        check_in=_d(2026, 6, 12), check_out=_d(2026, 6, 14))
    db.session.add(conv); db.session.flush()
    db.session.add(Message(conversation_id=conv.id, sender_type='guest',
                           content='already here', sent_at=datetime(2026, 6, 9, 11, 24)))
    db.session.commit()

    email = _email(id='gb1', sender_email='5843975682-x@guest.booking.com',
                   date='Mon, 09 Jun 2026 13:24:00 +0200', body=BOOKING_BODY)
    gmail = FakeGmail({'from:guest.booking.com newer_than:90d': [email]})

    AISettings.set('email_reconcile_enabled', 'true')  # feature is dormant by default
    stats = reconcile_from_email(gmail)
    assert stats['skipped_dupe'] == 1
    assert Message.query.filter_by(conversation_id=conv.id).count() == 1


def test_orchestrator_rescan_does_not_duplicate(app):
    g = Guest(name='Carolin Janowski'); db.session.add(g); db.session.flush()
    conv = Conversation(guest_id=g.id, platform='booking',
                        check_in=_d(2026, 6, 12), check_out=_d(2026, 6, 14))
    db.session.add(conv); db.session.commit()
    email = _email(id='gb1', sender_email='5843975682-x@guest.booking.com',
                   date='Mon, 09 Jun 2026 13:24:00 +0200', body=BOOKING_BODY)
    gmail = FakeGmail({'from:guest.booking.com newer_than:90d': [email]})

    AISettings.set('email_reconcile_enabled', 'true')  # feature is dormant by default
    first = reconcile_from_email(gmail)
    second = reconcile_from_email(gmail)  # re-scan same email

    assert first['auto_inserted'] == 1
    # second run must NOT insert again (global email:<id> guard)
    assert second['auto_inserted'] == 0
    assert Message.query.filter_by(conversation_id=conv.id).count() == 1


# ---------------------------------------------------------------------------
# Task 10: Review page route + confirm/reject/pending-count API
# ---------------------------------------------------------------------------

@pytest.fixture
def client(app):
    # The /chatbot blueprint has a before_request that redirects unauthenticated
    # users. Create an admin user and inject the Flask-Login session cookie to
    # bypass both the custom before_request guard and @login_required.
    from ChatBotAI.models import User
    user = User(username='tester', display_name='Tester', is_admin=True)
    user.set_password('pw')
    db.session.add(user)
    db.session.commit()

    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True
    return c


def _seed_pending_candidate():
    g = Guest(name='Carolin Janowski'); db.session.add(g); db.session.flush()
    conv = Conversation(guest_id=g.id, platform='booking'); db.session.add(conv); db.session.flush()
    cand = EmailBackfillCandidate(
        gmail_message_id='gb1', platform='booking', parsed_name='Carolin Janowski',
        parsed_text='Alles klar danke', parsed_timestamp=datetime(2026, 6, 9, 11, 24),
        guessed_conversation_id=conv.id, confidence=0.55, status='pending')
    db.session.add(cand); db.session.commit()
    return cand.id, conv.id


def test_confirm_inserts_message_and_marks_confirmed(app, client):
    cand_id, conv_id = _seed_pending_candidate()
    resp = client.post(f'/chatbot/api/email-review/{cand_id}/confirm')
    assert resp.status_code == 200
    msgs = Message.query.filter_by(conversation_id=conv_id).all()
    assert len(msgs) == 1
    assert msgs[0].platform_message_id == 'email:gb1'
    assert EmailBackfillCandidate.query.get(cand_id).status == 'confirmed'


def test_reject_marks_rejected_without_insert(app, client):
    cand_id, conv_id = _seed_pending_candidate()
    resp = client.post(f'/chatbot/api/email-review/{cand_id}/reject')
    assert resp.status_code == 200
    assert Message.query.filter_by(conversation_id=conv_id).count() == 0
    assert EmailBackfillCandidate.query.get(cand_id).status == 'rejected'


def test_pending_count(app, client):
    _seed_pending_candidate()
    resp = client.get('/chatbot/api/email-review/pending-count')
    assert resp.status_code == 200
    assert resp.get_json()['count'] == 1


def test_email_review_page_renders(app, client):
    _seed_pending_candidate()
    resp = client.get('/chatbot/email-review')
    assert resp.status_code == 200
    assert b'Alles klar danke' in resp.data  # the candidate's parsed_text shows on the page
