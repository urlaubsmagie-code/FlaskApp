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


# ---------------------------------------------------------------------------
# Parser hardening — fixtures taken from REAL Airbnb/Booking emails (2026-06-15)
# ---------------------------------------------------------------------------

# German Booking, "Format A": name inline on the intro line, message AFTER a
# blank line. The old parser returned an empty message here (the bug).
REAL_BOOKING_DE_BLANK = (
    "##- Bitte schreiben Sie Ihre Antwort oberhalb dieser Zeile -##\n"
    "\n"
    " Buchungsnummer: 5346680128\n"
    "\n"
    " Sie haben eine neue Nachricht von einem Gast\n"
    "\n"
    " Nachricht von Sebastian Große:\n"
    "\n"
    " Hallo, ich möchte, dass mir beim Check-out eine Rechnung per E-Mail\n"
    " zugesandt wird. Vielen Dank!\n"
    "\n"
    " Antworten\n"
    "\n"
    " Buchungsangaben\n"
    "\n"
    " Name des Gastes:\n Sebastian Große\n"
    " Check-in:\n Mo., 15. Juni 2026\n"
    " Check-out:\n Mi., 17. Juni 2026\n"
    " Unterkunftsname:\n Urlaubsmagie - Maisonette-Wohnung Wanderfalke - Saisonaler Pool\n"
    " Buchungsnummer:\n 5346680128\n"
)


def test_real_booking_de_message_after_blank_not_empty():
    e = _email(id='b1', sender_email='5346680128-x@guest.booking.com',
               date='Mon, 15 Jun 2026 12:21:37 +0200', body=REAL_BOOKING_DE_BLANK)
    n = parse_notification(e)
    assert n.guest_name == 'Sebastian Große'
    assert 'Rechnung' in n.message_text          # message no longer empty
    assert 'Antworten' not in n.message_text
    assert n.check_in == date(2026, 6, 15)
    assert n.check_out == date(2026, 6, 17)
    assert n.property_name == 'Urlaubsmagie - Maisonette-Wohnung Wanderfalke - Saisonaler Pool'
    assert n.booking_ref == '5346680128'


# German Booking "Format B": compact (inline labels), check-in-time request with
# button chrome + a wrapped property name across two lines.
REAL_BOOKING_DE_CHROME = (
    "Booking.com\n"
    " Buchungsnummer: 6179977145\n"
    "\n"
    " Sie haben eine neue Nachricht von einem Gast\n"
    "\n"
    " Nachricht von Egbert Steinbrück:\n"
    " Ich möchte einen Check-in um 16:00 - 17:00 Uhr anfragen. Ist das\n"
    " möglich?\n"
    " Kostenlos akzeptieren\n"
    " __________________________________________________________________\n"
    "\n"
    " Sonstiges\n"
    " __________________________________________________________________\n"
    "\n"
    " Buchungsangaben\n"
    " Name des Gastes: Egbert Steinbrück\n"
    " Check-in: Samstag, 27. Juni 2026\n"
    " Check-out: Sonntag, 28. Juni 2026\n"
    " Unterkunftsname: Urlaubsmagie - Ferienwohnung Forellensprung - Sauna &\n"
    " Saisonaler Pool\n"
    " Buchungsnummer: 6179977145\n"
)


def test_real_booking_strips_chrome_and_joins_wrapped_property():
    e = _email(id='b2', sender_email='6179977145-x@guest.booking.com',
               date='Mon, 15 Jun 2026 11:18:54 +0200', body=REAL_BOOKING_DE_CHROME)
    n = parse_notification(e)
    assert n.guest_name == 'Egbert Steinbrück'
    assert n.message_text == 'Ich möchte einen Check-in um 16:00 - 17:00 Uhr anfragen. Ist das möglich?'
    assert 'akzeptieren' not in n.message_text       # button chrome stripped
    assert n.check_in == date(2026, 6, 27)
    # wrapped property name joined across both lines
    assert n.property_name == 'Urlaubsmagie - Ferienwohnung Forellensprung - Sauna & Saisonaler Pool'


# English Booking: different anchors entirely (<Name> said:, Reply, Guest name,
# Property name). The old German-only parser extracted nothing here.
REAL_BOOKING_EN = (
    "##- Please type your reply above this line -##\n"
    "\n"
    " Confirmation number: 6288132125\n"
    "\n"
    " You have a new message from a guest\n"
    "\n"
    " Aleksandra Nowojska said:\n"
    "\n"
    " Sorry for the confusion. We've managed to check in.\n"
    "\n"
    " Reply\n"
    "\n"
    " Reservation details\n"
    "\n"
    " Guest name:\n Aleksandra Nowojska\n"
    " Check-in:\n Thu 18 Jun 2026\n"
    " Check-out:\n Sat 20 Jun 2026\n"
    " Property name:\n W2 - Urlaubsmagie - Im Herzen des Elbsandsteingebirges\n"
    " Booking number:\n 6288132125\n"
)


def test_real_booking_english_is_parsed():
    e = _email(id='b3', sender_email='6288132125-x@guest.booking.com',
               date='Mon, 15 Jun 2026 08:17:51 +0200', body=REAL_BOOKING_EN)
    n = parse_notification(e)
    assert n.guest_name == 'Aleksandra Nowojska'
    assert n.message_text == "Sorry for the confusion. We've managed to check in."
    assert n.check_in == date(2026, 6, 18)
    assert n.check_out == date(2026, 6, 20)
    assert 'Elbsandsteingebirges' in n.property_name


# Real Airbnb guest message: 'Buchende Person' role, with an auto-translation
# block that must be excluded, plus an in-body date block.
REAL_AIRBNB_GUEST = (
    "%opentrack%\n"
    "https://www.airbnb.de/?c=x\n"
    "\n"
    " ANH THU\n"
    " \n"
    " Buchende Person\n"
    " \n"
    " Hi,\n"
    " Vielen Dank für den herzlichen Empfang! Ich habe den\n"
    " Online-Check-in bereits abgeschlossen.\n"
    " \n"
    " Die ursprüngliche Nachricht wurde automatisch übersetzt:\n"
    " \n"
    " Hi,\n"
    " Thank you for the warm welcome!\n"
    "\n"
    "Antworten\n"
    "Du kannst auch direkt auf diese E-Mail antworten.\n"
    "Check-in Check-out\n"
    "DIENSTAG FREITAG\n"
    "16. Juni 2026 19. Juni 2026\n"
    "16:00 10:00\n"
)


def test_real_airbnb_guest_message_and_dates():
    e = _email(id='a1', sender_email='express@airbnb.com',
               reply_to='tok@reply.airbnb.com',
               subject='RE: Buchung für „Rothirsch, bis zu 4P", 16.–19. Juni',
               date='Mon, 15 Jun 2026 10:02:24 +0000', body=REAL_AIRBNB_GUEST)
    n = parse_notification(e)
    assert n.guest_name == 'ANH THU'
    assert 'Vielen Dank' in n.message_text
    assert 'Thank you' not in n.message_text       # translated copy excluded
    assert 'Antworten' not in n.message_text
    assert n.property_name == 'Rothirsch'
    assert n.check_in == date(2026, 6, 16)         # dates now pulled from body
    assert n.check_out == date(2026, 6, 19)


# Real Airbnb CO-HOST message: 'Co-Gastgeber:in' role. This is OUR OWN outgoing
# reply, NOT a guest message — must be skipped (returns None).
REAL_AIRBNB_COHOST = (
    "%opentrack%\n"
    "https://www.airbnb.de/?c=x\n"
    "\n"
    " FRANKA\n"
    " \n"
    " Co-Gastgeber:in\n"
    " \n"
    " Huhu, sehr vorbildlich;)\n"
    " Wir freuen uns auf dich\n"
    "\n"
    "Antworten\n"
)


def test_real_airbnb_cohost_message_is_skipped():
    e = _email(id='a2', sender_email='express@airbnb.com',
               reply_to='tok@reply.airbnb.com',
               subject='RE: Buchung für „Rothirsch", 16.–19. Juni',
               date='Mon, 15 Jun 2026 10:05:51 +0000', body=REAL_AIRBNB_COHOST)
    assert parse_notification(e) is None


def test_score_matches_when_conv_dates_are_strings():
    """Conversation.check_in is stored as a 'YYYY-MM-DD' string, not a date.
    Scoring must still credit a date match."""
    n = _booking_notif(check_in=_d(2026, 6, 12), check_out=_d(2026, 6, 14))
    conv = _conv(check_in='2026-06-12', check_out='2026-06-14')  # strings, like the DB
    assert score_conversation_match(n, conv) >= 0.8


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
                   date='Mon, 09 Jun 2026 13:24:00 +0200', body=BOOKING_BODY,
                   authentication_results=[BOOKING_AR_DIRECT])
    gmail = FakeGmail({'from:guest.booking.com newer_than:30d': [email]})

    AISettings.set('email_reconcile_enabled', 'true')  # feature is dormant by default
    stats = reconcile_from_email(gmail)

    assert stats['auto_inserted'] == 1
    msgs = Message.query.filter_by(conversation_id=conv.id).all()
    assert len(msgs) == 1
    assert msgs[0].platform_message_id == 'email:gb1'
    assert 'Alles klar' in msgs[0].content


def test_orchestrator_queues_low_confidence_airbnb(app):
    # Airbnb is intentionally NOT scanned anymore (Booking-only). Even if an
    # Airbnb notification is present under its old query key, the scan never
    # requests it, so nothing is queued or inserted.
    g = Guest(name='Rosy Fernandez'); db.session.add(g); db.session.flush()
    conv = Conversation(guest_id=g.id, platform='airbnb')
    db.session.add(conv); db.session.commit()

    email = _email(id='ga1', thread_id='ta1', sender_email='automated@airbnb.com',
                   reply_to='tok@reply.airbnb.com',
                   subject='RE: Buchung für „Pool | Sauna", 14.–16. Juni',
                   date='Mon, 09 Jun 2026 12:19:00 +0200', body=AIRBNB_BODY,
                   authentication_results=[AIRBNB_AR_PASS])
    gmail = FakeGmail({'from:airbnb.com newer_than:30d': [email]})

    AISettings.set('email_reconcile_enabled', 'true')
    stats = reconcile_from_email(gmail)

    assert stats['queued'] == 0
    assert Message.query.filter_by(conversation_id=conv.id).count() == 0
    assert EmailBackfillCandidate.query.filter_by(gmail_message_id='ga1').first() is None


def test_orchestrator_skips_duplicates(app):
    g = Guest(name='Carolin Janowski'); db.session.add(g); db.session.flush()
    conv = Conversation(guest_id=g.id, platform='booking',
                        check_in=_d(2026, 6, 12), check_out=_d(2026, 6, 14))
    db.session.add(conv); db.session.flush()
    db.session.add(Message(conversation_id=conv.id, sender_type='guest',
                           content='already here', sent_at=datetime(2026, 6, 9, 11, 24)))
    db.session.commit()

    email = _email(id='gb1', sender_email='5843975682-x@guest.booking.com',
                   date='Mon, 09 Jun 2026 13:24:00 +0200', body=BOOKING_BODY,
                   authentication_results=[BOOKING_AR_DIRECT])
    gmail = FakeGmail({'from:guest.booking.com newer_than:30d': [email]})

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
                   date='Mon, 09 Jun 2026 13:24:00 +0200', body=BOOKING_BODY,
                   authentication_results=[BOOKING_AR_DIRECT])
    gmail = FakeGmail({'from:guest.booking.com newer_than:30d': [email]})

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


# ---------------------------------------------------------------------------
# Tier 1: sender authenticity gate (DKIM/DMARC). Fixtures are REAL
# Authentication-Results strings pulled from live urlaubsmagie@gmail.com
# emails (2026-06-24). Gmail stamps the `mx.google.com; ...` line itself on
# receipt, so it cannot be forged by the sender.
# ---------------------------------------------------------------------------

from ChatBotAI.services.email_reconcile import verify_sender_authenticity

# Booking sent directly: SPF + DKIM + DMARC all aligned to guest.booking.com.
BOOKING_AR_DIRECT = (
    "mx.google.com;       dkim=pass header.i=@guest.booking.com header.s=bk "
    "header.b=ZB3yqEm2;       spf=pass (google.com: domain of "
    "6953701031-x@guest.booking.com designates 37.10.31.10 as permitted sender) "
    "smtp.mailfrom=6953701031-x@guest.booking.com;       dmarc=pass "
    "(p=REJECT sp=REJECT dis=NONE) header.from=guest.booking.com"
)

# Same Booking message but FORWARDED through the user's googlemail alias: SPF now
# authenticates the FORWARDER (gmail), not Booking — DKIM/DMARC still prove Booking.
# The gate must accept this (must NOT require SPF alignment).
BOOKING_AR_FORWARDED = (
    "mx.google.com;       dkim=pass header.i=@guest.booking.com header.s=bk "
    "header.b=IPyOYxey;       arc=pass (i=2 spf=pass spfdomain=guest.booking.com "
    "dkim=pass dkdomain=guest.booking.com dmarc=pass fromdomain=guest.booking.com);"
    "       spf=pass (google.com: domain of "
    "urlaubsmagie.rd+caf_=urlaubsmagie=googlemail.com@gmail.com designates "
    "209.85.220.41 as permitted sender) "
    'smtp.mailfrom="urlaubsmagie.rd+caf_=urlaubsmagie=googlemail.com@gmail.com";'
    "       dmarc=pass (p=REJECT sp=REJECT dis=NONE) header.from=guest.booking.com"
)

# Airbnb via SendGrid: DKIM passes for BOTH express.airbnb.com (aligned) and
# sendgrid.info (the ESP, NOT aligned). DMARC aligns to airbnb.com.
AIRBNB_AR_PASS = (
    "mx.google.com;       dkim=pass header.i=@express.airbnb.com header.s=s1 "
    "header.b=mq2YcfK7;       dkim=pass header.i=@sendgrid.info header.s=smtpapi "
    "header.b=QEBvaFaO;       arc=pass (i=2 spf=pass "
    "spfdomain=em5726.express.airbnb.com dkim=pass dkdomain=express.airbnb.com "
    "dkim=pass dkdomain=sendgrid.info dmarc=pass fromdomain=airbnb.com);"
    "       spf=pass (google.com: domain of x@gmail.com designates 209.85.220.41 "
    'as permitted sender) smtp.mailfrom="x@gmail.com";       dmarc=pass '
    "(p=REJECT sp=QUARANTINE dis=NONE) header.from=airbnb.com"
)

# A phishing mail forging From: booking.com — Booking publishes p=REJECT, so Gmail
# stamps dmarc=fail and there is no aligned DKIM signature.
SPOOFED_BOOKING_AR = (
    "mx.google.com;       dkim=none (no signature);       spf=fail "
    "(google.com: domain of bounce@eatonnanqiaohotel.com does not designate "
    "1.2.3.4 as permitted sender) smtp.mailfrom=bounce@eatonnanqiaohotel.com;"
    "       dmarc=fail (p=REJECT sp=REJECT dis=REJECT) header.from=booking.com"
)

# DKIM passes, but ONLY for an unrelated attacker domain; DMARC fails for booking.
UNALIGNED_DKIM_AR = (
    "mx.google.com;       dkim=pass header.i=@sneaky.example.com header.s=s1 "
    "header.b=abc;       spf=fail smtp.mailfrom=x@sneaky.example.com;"
    "       dmarc=fail (p=REJECT) header.from=booking.com"
)


def _ar_email(ar, **kw):
    return _email(authentication_results=([ar] if isinstance(ar, str) else ar), **kw)


def test_verify_accepts_booking_direct():
    ok, info = verify_sender_authenticity(_ar_email(BOOKING_AR_DIRECT), 'booking')
    assert ok is True
    assert info['dmarc'] == 'pass'


def test_verify_accepts_booking_forwarded_despite_spf_on_forwarder():
    # SPF authenticates gmail (the forwarder), not Booking — must still pass.
    ok, info = verify_sender_authenticity(_ar_email(BOOKING_AR_FORWARDED), 'booking')
    assert ok is True
    assert info['dkim_aligned'] is True


def test_verify_accepts_airbnb_via_sendgrid():
    ok, _ = verify_sender_authenticity(_ar_email(AIRBNB_AR_PASS), 'airbnb')
    assert ok is True


def test_verify_rejects_spoofed_booking():
    ok, info = verify_sender_authenticity(_ar_email(SPOOFED_BOOKING_AR), 'booking')
    assert ok is False
    assert info['dmarc'] == 'fail'


def test_verify_rejects_unaligned_dkim():
    ok, info = verify_sender_authenticity(_ar_email(UNALIGNED_DKIM_AR), 'booking')
    assert ok is False
    assert info['dkim_aligned'] is False


def test_verify_rejects_when_no_auth_results():
    ok, info = verify_sender_authenticity(_ar_email([]), 'booking')
    assert ok is False
    assert info['reason'] == 'no_trusted_auth_results'


def test_verify_trusts_only_googles_authserv_line():
    # Attacker injects their OWN Authentication-Results header claiming pass.
    # Only the line Gmail (mx.google.com) added is trustworthy → must be ignored.
    forged = (
        "evil.example.com;       dkim=pass header.i=@guest.booking.com "
        "header.b=x;       dmarc=pass header.from=guest.booking.com"
    )
    ok, info = verify_sender_authenticity(_ar_email([forged]), 'booking')
    assert ok is False
    assert info['reason'] == 'no_trusted_auth_results'


def test_parse_email_collects_authentication_results_list():
    svc = GmailService.__new__(GmailService)
    payload_headers = [
        {'name': 'From', 'value': 'x <a@guest.booking.com>'},
        {'name': 'Authentication-Results', 'value': BOOKING_AR_DIRECT},
        {'name': 'Authentication-Results', 'value': 'upstream.relay; dkim=pass'},
    ]
    import base64
    msg = {'id': 'm1', 'threadId': 't1', 'snippet': '', 'labelIds': [],
           'payload': {'headers': payload_headers, 'mimeType': 'text/plain',
                       'body': {'data': base64.urlsafe_b64encode(b'hi').decode()}}}
    parsed = svc._parse_email(msg)
    assert isinstance(parsed['authentication_results'], list)
    assert BOOKING_AR_DIRECT in parsed['authentication_results']
    assert len(parsed['authentication_results']) == 2  # both AR headers preserved


def test_orchestrator_drops_spoofed_email(app):
    g = Guest(name='Carolin Janowski'); db.session.add(g); db.session.flush()
    conv = Conversation(guest_id=g.id, platform='booking',
                        check_in=_d(2026, 6, 12), check_out=_d(2026, 6, 14))
    db.session.add(conv); db.session.commit()

    email = _email(id='spoof1', thread_id='ts1',
                   sender_email='5843975682-x@guest.booking.com',
                   date='Mon, 09 Jun 2026 13:24:00 +0200', body=BOOKING_BODY,
                   authentication_results=[SPOOFED_BOOKING_AR])
    gmail = FakeGmail({'from:guest.booking.com newer_than:30d': [email]})

    AISettings.set('email_reconcile_enabled', 'true')
    stats = reconcile_from_email(gmail)

    assert stats['rejected_unauthenticated'] == 1
    assert stats['auto_inserted'] == 0
    assert Message.query.filter_by(conversation_id=conv.id).count() == 0
    # Spoofed mail must NOT pollute the review tray either.
    assert EmailBackfillCandidate.query.filter_by(gmail_message_id='spoof1').first() is None


from ChatBotAI.services.email_reconcile import platform_queries


def test_platform_queries_is_booking_only():
    q = platform_queries(30)
    assert set(q.keys()) == {'booking'}
    assert q['booking'] == 'from:guest.booking.com newer_than:30d'


from ChatBotAI.services.email_reconcile import fetch_booking_for_conversation
import ChatBotAI.services.email_reconcile as _er


def test_live_fetch_inserts_matching_booking(app):
    _er._last_live_fetch.clear()
    g = Guest(name='Carolin Janowski'); db.session.add(g); db.session.flush()
    conv = Conversation(guest_id=g.id, platform='booking',
                        check_in=_d(2026, 6, 12), check_out=_d(2026, 6, 14))
    db.session.add(conv); db.session.commit()

    email = _email(id='glive1', sender_email='5843975682-x@guest.booking.com',
                   date='Mon, 09 Jun 2026 13:24:00 +0200', body=BOOKING_BODY,
                   authentication_results=[BOOKING_AR_DIRECT])
    query = f'from:guest.booking.com "Carolin Janowski" newer_than:30d'
    gmail = FakeGmail({query: [email]})

    stats = fetch_booking_for_conversation(gmail, conv.id)
    assert stats['auto_inserted'] == 1
    msgs = Message.query.filter_by(conversation_id=conv.id).all()
    assert len(msgs) == 1 and msgs[0].platform_message_id == 'email:glive1'


def test_live_fetch_noop_on_non_booking(app):
    _er._last_live_fetch.clear()
    g = Guest(name='Someone'); db.session.add(g); db.session.flush()
    conv = Conversation(guest_id=g.id, platform='email')
    db.session.add(conv); db.session.commit()
    gmail = FakeGmail({})  # must never be queried
    stats = fetch_booking_for_conversation(gmail, conv.id)
    assert stats['auto_inserted'] == 0
    assert stats.get('reason') == 'not_booking'


def test_live_fetch_throttled_second_call(app):
    _er._last_live_fetch.clear()
    g = Guest(name='Carolin Janowski'); db.session.add(g); db.session.flush()
    conv = Conversation(guest_id=g.id, platform='booking',
                        check_in=_d(2026, 6, 12), check_out=_d(2026, 6, 14))
    db.session.add(conv); db.session.commit()
    email = _email(id='glive2', sender_email='5843975682-x@guest.booking.com',
                   date='Mon, 09 Jun 2026 13:24:00 +0200', body=BOOKING_BODY,
                   authentication_results=[BOOKING_AR_DIRECT])
    query = f'from:guest.booking.com "Carolin Janowski" newer_than:30d'
    gmail = FakeGmail({query: [email]})

    first = fetch_booking_for_conversation(gmail, conv.id)
    second = fetch_booking_for_conversation(gmail, conv.id)  # within throttle window
    assert first['auto_inserted'] == 1
    assert second.get('reason') == 'throttled'
    assert Message.query.filter_by(conversation_id=conv.id).count() == 1


def test_live_fetch_matches_by_stored_buchungsnummer(app):
    import ChatBotAI.services.email_reconcile as er
    er._last_live_fetch.clear()
    g = Guest(name='Carolin Janowski'); db.session.add(g); db.session.flush()
    # Note carries the same Buchungsnummer as BOOKING_BODY (5843975682); dates deliberately DON'T match.
    db.session.add(GuestDetail(guest_id=g.id, detail_type='special_request',
        detail_key='guest_note', detail_value='Buchungsnummer: 5843975682\nGastnachricht: x'))
    conv = Conversation(guest_id=g.id, platform='booking',
                        check_in=_d(2020, 1, 1), check_out=_d(2020, 1, 2))
    db.session.add(conv); db.session.commit()

    email = _email(id='gbref', sender_email='5843975682-x@guest.booking.com',
                   date='Mon, 09 Jun 2026 13:24:00 +0200', body=BOOKING_BODY,
                   authentication_results=[BOOKING_AR_DIRECT])
    gmail = FakeGmail({'from:guest.booking.com "Carolin Janowski" newer_than:30d': [email]})

    stats = fetch_booking_for_conversation(gmail, conv.id)
    assert stats['auto_inserted'] == 1
    assert Message.query.filter_by(conversation_id=conv.id, platform_message_id='email:gbref').count() == 1


def test_live_fetch_rescues_misfiled_candidate(app):
    # The email is already a PENDING candidate filed under the WRONG conversation.
    # Opening the correct chat (whose note carries the matching ref) must insert it
    # here and flip the candidate to confirmed.
    import ChatBotAI.services.email_reconcile as er
    er._last_live_fetch.clear()
    other = Guest(name='Someone Else'); db.session.add(other); db.session.flush()
    wrong_conv = Conversation(guest_id=other.id, platform='booking')
    db.session.add(wrong_conv); db.session.flush()
    db.session.add(EmailBackfillCandidate(
        gmail_message_id='gbref', platform='booking', parsed_name='Carolin Janowski',
        parsed_text='hi', parsed_timestamp=datetime(2026, 6, 9, 11, 24),
        guessed_conversation_id=wrong_conv.id, confidence=0.15, status='pending'))

    g = Guest(name='Carolin Janowski'); db.session.add(g); db.session.flush()
    db.session.add(GuestDetail(guest_id=g.id, detail_type='special_request',
        detail_key='guest_note', detail_value='Buchungsnummer: 5843975682'))
    right_conv = Conversation(guest_id=g.id, platform='booking',
                              check_in=_d(2020, 1, 1), check_out=_d(2020, 1, 2))
    db.session.add(right_conv); db.session.commit()

    email = _email(id='gbref', sender_email='5843975682-x@guest.booking.com',
                   date='Mon, 09 Jun 2026 13:24:00 +0200', body=BOOKING_BODY,
                   authentication_results=[BOOKING_AR_DIRECT])
    gmail = FakeGmail({'from:guest.booking.com "Carolin Janowski" newer_than:30d': [email]})

    stats = fetch_booking_for_conversation(gmail, right_conv.id)
    assert stats['auto_inserted'] == 1
    assert Message.query.filter_by(conversation_id=right_conv.id).count() == 1
    assert Message.query.filter_by(conversation_id=wrong_conv.id).count() == 0
    assert EmailBackfillCandidate.query.filter_by(gmail_message_id='gbref').first().status == 'confirmed'


def test_live_fetch_matches_by_dates_when_no_note(app):
    import ChatBotAI.services.email_reconcile as er
    er._last_live_fetch.clear()
    g = Guest(name='Carolin Janowski'); db.session.add(g); db.session.flush()
    # No note -> no Tier-1 ref; BOOKING_BODY dates are 12.-14.06.2026, so match those.
    conv = Conversation(guest_id=g.id, platform='booking',
                        check_in=_d(2026, 6, 12), check_out=_d(2026, 6, 14))
    db.session.add(conv); db.session.commit()
    email = _email(id='gbdate', sender_email='5843975682-x@guest.booking.com',
                   date='Mon, 09 Jun 2026 13:24:00 +0200', body=BOOKING_BODY,
                   authentication_results=[BOOKING_AR_DIRECT])
    gmail = FakeGmail({'from:guest.booking.com "Carolin Janowski" newer_than:30d': [email]})
    stats = fetch_booking_for_conversation(gmail, conv.id)
    assert stats['auto_inserted'] == 1


def test_live_fetch_no_insert_when_ref_and_dates_differ(app):
    import ChatBotAI.services.email_reconcile as er
    er._last_live_fetch.clear()
    g = Guest(name='Carolin Janowski'); db.session.add(g); db.session.flush()
    conv = Conversation(guest_id=g.id, platform='booking',
                        check_in=_d(2026, 6, 12), check_out=_d(2026, 6, 20))  # checkout differs
    db.session.add(conv); db.session.commit()
    email = _email(id='gbno', sender_email='9999999999-x@guest.booking.com',
                   date='Mon, 09 Jun 2026 13:24:00 +0200', body=BOOKING_BODY,
                   authentication_results=[BOOKING_AR_DIRECT])
    gmail = FakeGmail({'from:guest.booking.com "Carolin Janowski" newer_than:30d': [email]})
    stats = fetch_booking_for_conversation(gmail, conv.id)
    assert stats['auto_inserted'] == 0
    assert Message.query.filter_by(conversation_id=conv.id).count() == 0


def test_live_fetch_matches_by_smoobu_reference_id(app, monkeypatch):
    # No note, dates DON'T match -> Tier 2: Smoobu reference-id supplies the number.
    import ChatBotAI.services.email_reconcile as er
    er._last_live_fetch.clear()
    g = Guest(name='Carolin Janowski'); db.session.add(g); db.session.flush()
    conv = Conversation(guest_id=g.id, platform='booking', smoobu_reservation_id='146578501',
                        check_in=_d(2020, 1, 1), check_out=_d(2020, 1, 2))
    db.session.add(conv); db.session.commit()

    class FakeSmoobu:
        def get_reservation(self, rid):
            return {'reference-id': '5843975682'}  # matches BOOKING_BODY's ref
    import ChatBotAI.services.smoobu_service as ss
    monkeypatch.setattr(ss, 'get_smoobu_service', lambda: FakeSmoobu())

    email = _email(id='gbsmoobu', sender_email='5843975682-x@guest.booking.com',
                   date='Mon, 09 Jun 2026 13:24:00 +0200', body=BOOKING_BODY,
                   authentication_results=[BOOKING_AR_DIRECT])
    gmail = FakeGmail({'from:guest.booking.com "Carolin Janowski" newer_than:30d': [email]})
    stats = fetch_booking_for_conversation(gmail, conv.id)
    assert stats['auto_inserted'] == 1


# ---------------------------------------------------------------------------
# Task 4: Route — POST /api/conversation/<id>/fetch-booking-live
# ---------------------------------------------------------------------------

def test_fetch_booking_live_route_inserts(client, monkeypatch):
    import ChatBotAI.services.email_reconcile as er
    er._last_live_fetch.clear()
    g = Guest(name='Carolin Janowski'); db.session.add(g); db.session.flush()
    conv = Conversation(guest_id=g.id, platform='booking',
                        check_in=_d(2026, 6, 12), check_out=_d(2026, 6, 14))
    db.session.add(conv); db.session.commit()

    email = _email(id='groute1', sender_email='5843975682-x@guest.booking.com',
                   date='Mon, 09 Jun 2026 13:24:00 +0200', body=BOOKING_BODY,
                   authentication_results=[BOOKING_AR_DIRECT])

    class FakeAuthedGmail:
        def is_authenticated(self):
            return True
        def get_recent_emails(self, max_results=10, query=None, apply_filter=True):
            return [email]

    import ChatBotAI.services.gmail_service as gs
    monkeypatch.setattr(gs, 'get_gmail_service', lambda: FakeAuthedGmail())

    r = client.post(f'/chatbot/api/conversation/{conv.id}/fetch-booking-live')
    assert r.status_code == 200
    assert r.get_json()['inserted'] == 1
    assert Message.query.filter_by(conversation_id=conv.id).count() == 1


def test_fetch_booking_live_route_gmail_disconnected(client, monkeypatch):
    import ChatBotAI.services.email_reconcile as er
    er._last_live_fetch.clear()
    g = Guest(name='X'); db.session.add(g); db.session.flush()
    conv = Conversation(guest_id=g.id, platform='booking')
    db.session.add(conv); db.session.commit()

    import ChatBotAI.services.gmail_service as gs
    monkeypatch.setattr(gs, 'get_gmail_service', lambda: None)

    r = client.post(f'/chatbot/api/conversation/{conv.id}/fetch-booking-live')
    assert r.status_code == 200
    assert r.get_json()['inserted'] == 0


from ChatBotAI.models import GuestDetail
from ChatBotAI.services.email_reconcile import (
    booking_ref_from_note, conversation_booking_ref, email_matches_conversation,
)
from types import SimpleNamespace


def test_booking_ref_from_note_extracts(app):
    g = Guest(name='Carolin Janowski'); db.session.add(g); db.session.flush()
    db.session.add(GuestDetail(guest_id=g.id, detail_type='special_request',
        detail_key='guest_note',
        detail_value='Buchungsnummer: 5110199521\nGastnachricht: ** PRE-PAID **'))
    db.session.commit()
    assert booking_ref_from_note(g.id) == '5110199521'


def test_booking_ref_from_note_absent_returns_none(app):
    g = Guest(name='No Note'); db.session.add(g); db.session.flush()
    db.session.commit()
    assert booking_ref_from_note(g.id) is None


def test_email_matches_by_exact_ref():
    notif = _booking_notif(booking_ref='5110199521',
                           check_in=_d(2026, 7, 10), check_out=_d(2026, 7, 12))
    conv = SimpleNamespace(check_in='2026-01-01', check_out='2026-01-02')  # dates differ
    assert email_matches_conversation(notif, conv, '5110199521') is True


def test_email_ref_mismatch_but_dates_match():
    notif = _booking_notif(booking_ref='9999999999',
                           check_in=_d(2026, 7, 10), check_out=_d(2026, 7, 12))
    conv = SimpleNamespace(check_in='2026-07-10', check_out='2026-07-12')
    assert email_matches_conversation(notif, conv, '5110199521') is True  # via dates


def test_email_no_match_when_ref_and_dates_differ():
    notif = _booking_notif(booking_ref='9999999999',
                           check_in=_d(2026, 7, 10), check_out=_d(2026, 7, 12))
    conv = SimpleNamespace(check_in='2026-07-10', check_out='2026-07-16')  # checkout differs
    assert email_matches_conversation(notif, conv, '5110199521') is False


def test_email_checkin_only_match_is_not_enough():
    notif = _booking_notif(booking_ref=None,
                           check_in=_d(2026, 7, 10), check_out=_d(2026, 7, 12))
    conv = SimpleNamespace(check_in='2026-07-10', check_out='2026-07-16')
    assert email_matches_conversation(notif, conv, None) is False
