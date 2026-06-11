"""Email reconciliation: backfill guest messages from Airbnb/Booking
notification emails that Smoobu dropped.

Pure functions (classify/parse/score) are unit-tested without a DB. The
reconcile_from_email() orchestrator and DB helpers live at the bottom.

See docs/superpowers/specs/2026-06-09-email-reconciliation-design.md.
"""
import logging
import re
from collections import namedtuple
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

from ..models import db
from .guest_matching import normalize_name  # DRY: reuse existing normalizer

# --- Relay domains: these subdomains are used ONLY for two-way guest
# messaging, never for confirmations/payouts/reviews. They are the funnel. ---
BOOKING_SENDER_DOMAIN = 'guest.booking.com'
AIRBNB_REPLY_DOMAIN = 'reply.airbnb.com'

ParsedNotification = namedtuple("ParsedNotification", [
    "platform", "gmail_id", "thread_id", "guest_name", "message_text",
    "sent_at", "property_name", "check_in", "check_out", "booking_ref",
])


def classify_notification(email: dict):
    """Return 'booking', 'airbnb', or None for a parsed Gmail email dict."""
    sender = (email.get('sender_email') or '').lower()
    reply_to = (email.get('reply_to') or '').lower()

    if sender.endswith('@' + BOOKING_SENDER_DOMAIN):
        # Sender subdomain is authoritative for Booking guest messaging.
        return 'booking'

    if AIRBNB_REPLY_DOMAIN in reply_to or AIRBNB_REPLY_DOMAIN in (email.get('from') or '').lower():
        return 'airbnb'

    return None


# German month names -> month number, for parsing "12. Juni 2026".
_MONTHS_DE = {
    'januar': 1, 'februar': 2, 'märz': 3, 'april': 4, 'mai': 5, 'juni': 6,
    'juli': 7, 'august': 8, 'september': 9, 'oktober': 10, 'november': 11, 'dezember': 12,
}


def _parse_email_date(date_header: str):
    """RFC-2822 Date header -> naive UTC datetime (matches app storage convention)."""
    from email.utils import parsedate_to_datetime
    if not date_header:
        return None
    try:
        dt = parsedate_to_datetime(date_header)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _parse_german_date(text: str):
    """Parse 'Fr., 12. Juni 2026' (and similar) -> datetime.date or None."""
    m = re.search(r'(\d{1,2})\.\s*([A-Za-zäöüÄÖÜ]+)\s+(\d{4})', text)
    if not m:
        return None
    day, month_name, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
    month = _MONTHS_DE.get(month_name)
    if not month:
        return None
    from datetime import date as _date
    try:
        return _date(year, month, day)
    except ValueError:
        return None


def _value_after_label(body: str, label: str):
    """Return the first non-empty line after a label line, else None."""
    lines = [ln.strip() for ln in body.splitlines()]
    for i, ln in enumerate(lines):
        if ln.startswith(label):
            inline = ln[len(label):].strip().lstrip(':').strip()
            if inline:
                return inline
            for nxt in lines[i + 1:]:
                if nxt:
                    return nxt
    return None


def _text_between(body: str, start_label: str, stop_labels):
    """Collect lines after start_label until a stop label/blank line. Trims chrome."""
    lines = [ln.strip() for ln in body.splitlines()]
    out, capturing = [], False
    for ln in lines:
        if not capturing:
            if ln.startswith(start_label):
                capturing = True
                inline = ln[len(start_label):].strip().lstrip(':').strip()
                if inline:
                    out.append(inline)
            continue
        if any(ln.startswith(s) for s in stop_labels) or ln == '':
            if out:
                break
            continue
        out.append(ln)
    return '\n'.join(out).strip() or None


def parse_booking_notification(email: dict):
    body = email.get('body') or ''
    sender = (email.get('sender_email') or '')
    _ref_candidate = sender.split('@')[0].split('-')[0]
    booking_ref = _ref_candidate if re.fullmatch(r'\d+', _ref_candidate or '') else None
    name = _value_after_label(body, 'Name des Gastes')
    message = _text_between(body, 'Nachricht von',
                            stop_labels=['Antworten', 'Buchungsangaben', 'Buchungsnummer'])
    if message and name and message.startswith(name):
        message = message[len(name):].lstrip(':').strip()
    check_in = _parse_german_date(_value_after_label(body, 'Check-in') or '')
    check_out = _parse_german_date(_value_after_label(body, 'Check-out') or '')
    prop = _value_after_label(body, 'Unterkunftsname')
    return ParsedNotification(
        platform='booking', gmail_id=email.get('id'), thread_id=email.get('thread_id'),
        guest_name=name, message_text=message, sent_at=_parse_email_date(email.get('date')),
        property_name=prop, check_in=check_in, check_out=check_out, booking_ref=booking_ref,
    )


def parse_airbnb_notification(email: dict):
    body = email.get('body') or ''
    subject = email.get('subject') or ''
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    name = None
    for i, ln in enumerate(lines):
        if ln.startswith('Buchende Person') and i > 0:
            name = lines[i - 1]
            break
    message = _text_between(body, 'Buchende Person',
                            stop_labels=['Die ursprüngliche Nachricht', 'Antworten',
                                         'Du kannst auch direkt'])
    prop = None
    m = re.search(r'Buchung für\s+[„"]?([^"\n]+?)[""]?(?:,|$)', subject)
    if m:
        prop = m.group(1).strip().strip('„""')
    return ParsedNotification(
        platform='airbnb', gmail_id=email.get('id'), thread_id=email.get('thread_id'),
        guest_name=name, message_text=message, sent_at=_parse_email_date(email.get('date')),
        property_name=prop, check_in=None, check_out=None, booking_ref=None,
    )


def parse_notification(email: dict):
    """Classify then parse. Returns ParsedNotification or None."""
    platform = classify_notification(email)
    if platform == 'booking':
        return parse_booking_notification(email)
    if platform == 'airbnb':
        return parse_airbnb_notification(email)
    return None


def _property_overlap(a: str, b: str) -> bool:
    """Loose property match: do the two names share a meaningful token?
    Booking/Airbnb titles are marketing strings, so exact equality is rare."""
    if not a or not b:
        return False
    stop = {'urlaubsmagie', 'ferienwohnung', 'mit', 'und', 'der', 'die', 'das',
            'perfekter', 'urlaub', 'apartment', 'wohnung', 'haus'}
    ta = {t for t in re.split(r'[^a-zäöüß0-9]+', a.lower()) if len(t) > 2 and t not in stop}
    tb = {t for t in re.split(r'[^a-zäöüß0-9]+', b.lower()) if len(t) > 2 and t not in stop}
    return bool(ta & tb)


def score_conversation_match(notif, conv: dict) -> float:
    """Return a 0..1 confidence that `notif` belongs to conversation `conv`."""
    if conv.get('channel') != notif.platform:
        return 0.0

    score = 0.0
    n_name = normalize_name(notif.guest_name)
    c_name = normalize_name(conv.get('guest_name'))

    if n_name and c_name:
        if notif.platform == 'booking':
            if n_name == c_name:
                score += 0.5
        else:  # airbnb gives first name only
            if c_name.split()[0] == n_name.split()[0]:
                score += 0.3

    if _property_overlap(notif.property_name, conv.get('property_name')):
        score += 0.3

    # Exact reservation dates (Booking only carries them) are strong corroboration.
    if notif.check_in and conv.get('check_in') and notif.check_in == conv['check_in']:
        score += 0.15
    if notif.check_out and conv.get('check_out') and notif.check_out == conv['check_out']:
        score += 0.15

    return min(score, 1.0)


def pick_best_match(notif, convs):
    """Return (best_conv_dict, score). (None, 0.0) if no candidates."""
    best, best_score = None, 0.0
    for conv in convs:
        s = score_conversation_match(notif, conv)
        if s > best_score:
            best, best_score = conv, s
    return best, best_score


def has_equivalent_message(conversation_id: int, notif, window_minutes: int = 10) -> bool:
    """True if the conversation already has a guest message within ±window_minutes
    of notif.sent_at. Direction-aware (guest->host), time-fuzzy, NOT text-exact
    (Airbnb auto-translates so text differs between Smoobu and email)."""
    from ..models import Message
    if not notif.sent_at:
        return False
    lo = notif.sent_at - timedelta(minutes=window_minutes)
    hi = notif.sent_at + timedelta(minutes=window_minutes)
    return db.session.query(Message.id).filter(
        Message.conversation_id == conversation_id,
        Message.sender_type == 'guest',
        Message.sent_at >= lo,
        Message.sent_at <= hi,
    ).first() is not None


def _as_bool(val, default=False):
    if val is None:
        return default
    return str(val).strip().lower() in ('1', 'true', 'yes', 'on')


def get_reconcile_config() -> dict:
    """Typed reconciliation settings with defaults. See spec section 7/9."""
    from ..models import AISettings
    try:
        threshold = float(AISettings.get('email_confidence_threshold', '0.8'))
    except (TypeError, ValueError):
        threshold = 0.8
    return {
        # Dormant by default: must be explicitly enabled in Settings after the
        # operator applies migration p18 and validates the parser against real
        # Airbnb/Booking emails. Prevents an unvalidated parser from auto-running
        # against live Gmail on a production restart.
        'enabled': _as_bool(AISettings.get('email_reconcile_enabled', 'false'), False),
        'threshold': threshold,
        'autoinsert_booking': _as_bool(AISettings.get('email_autoinsert_booking', 'true'), True),
        'autoinsert_airbnb': _as_bool(AISettings.get('email_autoinsert_airbnb', 'false'), False),
        'window_minutes': int(AISettings.get('email_dedup_window_minutes', '10') or 10),
    }


def resolve_channel(conv):
    """Return 'booking' | 'airbnb' | None for a Conversation, checking
    Conversation.platform first, then the guest's booking_channel detail."""
    plat = (conv.platform or '').lower()
    if plat in ('booking', 'booking.com'):
        return 'booking'
    if plat == 'airbnb':
        return 'airbnb'
    from ..models import GuestDetail
    detail = GuestDetail.query.filter_by(
        guest_id=conv.guest_id, detail_key='booking_channel'
    ).first()
    if detail and detail.detail_value:
        val = detail.detail_value.lower()
        if 'booking' in val:
            return 'booking'
        if 'airbnb' in val:
            return 'airbnb'
    return None


# ---------------------------------------------------------------------------
# Task 8: Orchestrator
# ---------------------------------------------------------------------------

# Gmail search queries — relay-domain funnel + 90-day window (matches Smoobu sync).
PLATFORM_QUERIES = {
    'booking': 'from:guest.booking.com newer_than:90d',
    'airbnb': 'from:airbnb.com newer_than:90d',
}


def _candidate_views(channel: str):
    """Build scorer input dicts for all conversations on a channel."""
    from ..models import Conversation, Guest, Property
    views = []
    for conv in Conversation.query.all():
        if resolve_channel(conv) != channel:
            continue
        guest = Guest.query.get(conv.guest_id)
        prop = Property.query.get(conv.property_id) if conv.property_id else None
        views.append({
            'conversation_id': conv.id,
            'channel': channel,
            'guest_name': guest.name if guest else None,
            'property_name': prop.name if prop else (conv.subject or None),
            'check_in': conv.check_in,
            'check_out': conv.check_out,
        })
    return views


def reconcile_from_email(gmail_service, max_per_platform: int = 50) -> dict:
    """Scan Airbnb/Booking notification emails and backfill missing guest messages.

    Returns stats: scanned, matched, auto_inserted, queued, skipped_dupe, unmatched.
    Read-only on Gmail; inserts only into EXISTING conversations.
    """
    from ..models import EmailBackfillCandidate
    from .message_router import get_message_router

    cfg = get_reconcile_config()
    stats = {'scanned': 0, 'matched': 0, 'auto_inserted': 0,
             'queued': 0, 'skipped_dupe': 0, 'unmatched': 0}
    if not cfg['enabled']:
        return stats

    router = get_message_router()

    for platform, query in PLATFORM_QUERIES.items():
        try:
            emails = gmail_service.get_recent_emails(
                max_results=max_per_platform, query=query, apply_filter=False)
        except Exception:
            logger.exception("email-reconcile: Gmail fetch failed for %s", platform)
            continue

        views = _candidate_views(platform)

        for email in emails:
            stats['scanned'] += 1
            notif = parse_notification(email)
            if not notif or not notif.message_text or not notif.sent_at:
                continue

            # Skip if already queued OR rejected for this email — a human's
            # rejection must never be reconsidered on a later scan.
            if EmailBackfillCandidate.query.filter_by(gmail_message_id=notif.gmail_id).first():
                continue

            # Global guard: if this email was already auto-inserted into ANY
            # conversation (possibly a different one due to duplicate-guest churn),
            # skip it to prevent duplicate messages across conversation rows.
            from ..models import Message
            if Message.query.filter_by(platform_message_id=f"email:{notif.gmail_id}").first():
                continue

            best, score = pick_best_match(notif, views)
            if not best:
                stats['unmatched'] += 1
                continue
            stats['matched'] += 1

            if has_equivalent_message(best['conversation_id'], notif, cfg['window_minutes']):
                stats['skipped_dupe'] += 1
                continue

            autoinsert = cfg['autoinsert_booking'] if platform == 'booking' else cfg['autoinsert_airbnb']
            if score >= cfg['threshold'] and autoinsert:
                router._store_message(
                    conversation_id=best['conversation_id'],
                    sender_type='guest',
                    content=notif.message_text,
                    platform_message_id=f"email:{notif.gmail_id}",
                    sent_at=notif.sent_at,
                    sent_via_app=False,
                )
                stats['auto_inserted'] += 1
            else:
                db.session.add(EmailBackfillCandidate(
                    gmail_message_id=notif.gmail_id,
                    platform=platform,
                    parsed_name=notif.guest_name,
                    parsed_text=notif.message_text,
                    parsed_timestamp=notif.sent_at,
                    guessed_conversation_id=best['conversation_id'],
                    confidence=score,
                    status='pending',
                ))
                db.session.commit()
                stats['queued'] += 1

    logger.info("email-reconcile: %s", stats)
    return stats
