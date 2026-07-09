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
from .apartment_names import code_from_smoobu_id, codes_from_property_text

# --- Relay domains: these subdomains are used ONLY for two-way guest
# messaging, never for confirmations/payouts/reviews. They are the funnel. ---
BOOKING_SENDER_DOMAIN = 'guest.booking.com'
AIRBNB_REPLY_DOMAIN = 'reply.airbnb.com'

ParsedNotification = namedtuple("ParsedNotification", [
    "platform", "gmail_id", "thread_id", "guest_name", "message_text",
    "sent_at", "property_name", "check_in", "check_out", "booking_ref",
])


# Expected DKIM/DMARC signing-domain family per platform. A DKIM signature is
# "aligned" when it was produced by the platform's own domain (or a subdomain).
_PLATFORM_AUTH_DOMAIN = {
    'booking': 'booking.com',
    'airbnb': 'airbnb.com',
}


def _trusted_auth_results(email: dict) -> str:
    """Return the Authentication-Results line Gmail stamped on receipt, else ''.

    Only the line whose authserv-id is 'mx.google.com' is trustworthy: Gmail
    adds it AFTER the message arrives at our mailbox, so a sender cannot forge
    it. Any OTHER Authentication-Results header may have been injected upstream
    by an attacker and must be ignored.
    """
    for ar in (email.get('authentication_results') or []):
        if (ar or '').strip().lower().startswith('mx.google.com'):
            return ar
    return ''


def _ar_verdict(flat_ar: str, mech: str):
    """Top-level verdict ('pass'/'fail'/...) for an auth mechanism, or None.
    Expects parenthetical groups already stripped (see verify_sender_authenticity)."""
    m = re.search(r'\b' + mech + r'=(\w+)', flat_ar)
    return m.group(1).lower() if m else None


def verify_sender_authenticity(email: dict, platform: str):
    """Tier-1 anti-spoof gate. Returns (is_authentic: bool, info: dict).

    Trusts ONLY Gmail's own Authentication-Results line and requires BOTH:
      * DMARC = pass, AND
      * a DKIM signature that PASSED and is aligned to the platform's domain.

    SPF is recorded but NOT required: mail forwarded through the user's
    googlemail alias authenticates the forwarder rather than the platform, yet
    the platform's DKIM signature survives forwarding intact.
    """
    expected = _PLATFORM_AUTH_DOMAIN.get(platform)
    ar = _trusted_auth_results(email)
    if not ar or not expected:
        return False, {'reason': 'no_trusted_auth_results'}

    # Strip parenthetical groups so we read only TOP-LEVEL verdicts: SPF comments
    # "(google.com: ...)", the DMARC policy "(p=REJECT ...)", and the nested
    # arc=(... spf=pass dkim=pass dmarc=pass ...) block — never ARC's copies.
    flat = re.sub(r'\([^)]*\)', '', ar)

    dmarc = _ar_verdict(flat, 'dmarc')
    spf = _ar_verdict(flat, 'spf')

    dkim_aligned = False
    for m in re.finditer(r'dkim=pass\b[^;]*?header\.[id]=@?([^\s;]+)', flat):
        d = m.group(1).lower().rstrip('.')
        if d == expected or d.endswith('.' + expected):
            dkim_aligned = True
            break

    ok = (dmarc == 'pass') and dkim_aligned
    return ok, {'dmarc': dmarc, 'spf': spf, 'dkim_aligned': dkim_aligned,
                'expected_domain': expected}


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


# Month names -> number. German + English, long + short forms, so Booking
# emails in either language ("12. Juni 2026" / "Thu 18 Jun 2026") parse.
_MONTHS = {
    # German long
    'januar': 1, 'februar': 2, 'märz': 3, 'maerz': 3, 'april': 4, 'mai': 5,
    'juni': 6, 'juli': 7, 'august': 8, 'september': 9, 'oktober': 10,
    'november': 11, 'dezember': 12,
    # English long
    'january': 1, 'february': 2, 'march': 3, 'may': 5, 'june': 6, 'july': 7,
    'october': 10, 'december': 12,
    # Short forms (de+en)
    'jan': 1, 'feb': 2, 'mar': 3, 'mär': 3, 'apr': 4, 'jun': 6, 'jul': 7,
    'aug': 8, 'sep': 9, 'sept': 9, 'oct': 10, 'okt': 10, 'nov': 11,
    'dec': 12, 'dez': 12,
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


def _parse_date_any(text: str):
    """Parse a Booking/Airbnb date in German or English -> datetime.date or None.
    Tolerates weekday prefixes and dotted/short month names:
    'Mo., 15. Juni 2026', 'Montag, 27. Juni 2026', 'Thu 18 Jun 2026', '16. Juni 2026'.
    """
    if not text:
        return None
    m = re.search(r'(\d{1,2})\.?\s+([A-Za-zÄÖÜäöüé]+)\.?\s+(\d{4})', text)
    if not m:
        return None
    day, month_name, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
    month = _MONTHS.get(month_name)
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


def _clean_join(parts):
    """Join captured message lines into one clean string (collapse whitespace)."""
    text = re.sub(r'\s+', ' ', ' '.join(parts)).strip()
    return text or None


def _collect_message(lines, start_idx, is_stop):
    """Collect message lines from start_idx until a stop marker. Skips blank
    lines (so multi-paragraph guest messages survive) and never breaks early on
    them — only an explicit stop marker ends the message."""
    out = []
    for ln in lines[start_idx:]:
        s = ln.strip()
        if is_stop(s):
            break
        if s:
            out.append(s)
    return _clean_join(out)


# Reservation-detail keys (de+en). Used to know where one value ends and the
# next field begins, even when the next field has its value inline on the line.
_DETAIL_LABELS = (
    'buchungsnummer', 'booking number', 'check-in', 'check-out',
    'name des gastes', 'guest name', 'unterkunftsname', 'property name',
    'gesamtzahl', 'total guests', 'total rooms', '© copyright', 'antworten', 'reply',
)


def _looks_like_label(line: str) -> bool:
    """True if the line begins a reservation-detail field, so value capture stops.
    Covers both 'Label:' (value on next line) and 'Label: value' (inline)."""
    low = line.lower()
    if any(low.startswith(lb) for lb in _DETAIL_LABELS):
        return True
    return bool(re.match(r'^[A-Za-zÄÖÜäöü ./-]{2,30}:\s*$', line))


def _value_block_after(body: str, labels):
    """Value after the first matching label, joining wrapped continuation lines
    (Booking wraps long property names across two lines). Stops at a blank line
    or the next reservation-detail label. Tries each label in order (multi-lang)."""
    lines = [ln.strip() for ln in body.splitlines()]
    low_labels = [lb.lower() for lb in labels]
    for i, ln in enumerate(lines):
        low = ln.lower()
        for lb in low_labels:
            if low.startswith(lb):
                collected = []
                inline = ln[len(lb):].strip().lstrip(':').strip()
                if inline:
                    collected.append(inline)
                for nxt in lines[i + 1:]:
                    if not nxt or _looks_like_label(nxt):
                        break
                    collected.append(nxt)
                    if len(collected) >= 3:  # property names are at most ~2 lines
                        break
                return ' '.join(collected).strip() or None
    return None


# Lines that end a Booking guest message (German + English) + interactive chrome.
_BOOKING_STOP = (
    'antworten', 'reply', 'buchungsangaben', 'reservation details',
    'buchungsnummer', 'booking number', 'name des gastes', 'guest name',
    'kostenlos akzeptieren', 'mit gebühren akzeptieren', 'je nach verfügbarkeit',
    'nicht akzeptiert', 'sonstiges', '-->',
)
_AIRBNB_STOP = (
    'antworten', 'reply', 'du kannst auch direkt', 'die ursprüngliche nachricht',
)


def _is_booking_stop(line: str) -> bool:
    l = line.strip().lower()
    if not l:
        return False
    if set(l) <= {'_'}:                       # row of button separators
        return True
    if l.startswith('am ') and 'schrieb' in l:  # quoted history (de)
        return True
    if re.match(r'^on .+wrote:$', l):           # quoted history (en)
        return True
    return any(l.startswith(s) for s in _BOOKING_STOP)


def _is_airbnb_stop(line: str) -> bool:
    l = line.strip().lower()
    return bool(l) and any(l.startswith(s) for s in _AIRBNB_STOP)


def _airbnb_dates(body: str):
    """Airbnb bodies render check-in/check-out as two dates on one line
    ('16. Juni 2026 19. Juni 2026'). Best-effort; (None, None) if not found."""
    m = re.search(
        r'(\d{1,2}\.?\s+[A-Za-zÄÖÜäöü]+\.?\s+\d{4})\s+(\d{1,2}\.?\s+[A-Za-zÄÖÜäöü]+\.?\s+\d{4})',
        body)
    if not m:
        return None, None
    return _parse_date_any(m.group(1)), _parse_date_any(m.group(2))


def parse_booking_notification(email: dict):
    body = email.get('body') or ''
    sender = (email.get('sender_email') or '')
    _ref_candidate = sender.split('@')[0].split('-')[0]
    booking_ref = _ref_candidate if re.fullmatch(r'\d+', _ref_candidate or '') else None
    if not booking_ref:
        ref = _value_block_after(body, ['Buchungsnummer', 'Booking number'])
        booking_ref = ref if (ref and re.fullmatch(r'\d+', ref)) else None

    # Name from the reservation-details label (de/en); most reliable.
    name = (_value_after_label(body, 'Name des Gastes')
            or _value_after_label(body, 'Guest name'))

    # Message intro: German 'Nachricht von <Name>:' or English '<Name> said:'.
    # The message text starts on the NEXT line (often after a blank line), which
    # is why the old single-anchor approach returned empty for many real emails.
    lines = [ln.strip() for ln in body.splitlines()]
    start = None
    for i, s in enumerate(lines):
        low = s.lower()
        if low.startswith('nachricht von') or low.endswith(' said:'):
            start = i
            break
    message = _collect_message(lines, start + 1, _is_booking_stop) if start is not None else None

    # Fallback name from the intro line if the label was missing.
    if not name and start is not None:
        intro = lines[start]
        if intro.lower().startswith('nachricht von'):
            name = intro[len('nachricht von'):].strip().rstrip(':').strip() or None
        elif intro.lower().endswith(' said:'):
            name = intro[:-len(' said:')].strip() or None

    check_in = _parse_date_any(_value_after_label(body, 'Check-in') or '')
    check_out = _parse_date_any(_value_after_label(body, 'Check-out') or '')
    prop = _value_block_after(body, ['Unterkunftsname', 'Property name'])
    return ParsedNotification(
        platform='booking', gmail_id=email.get('id'), thread_id=email.get('thread_id'),
        guest_name=name, message_text=message, sent_at=_parse_email_date(email.get('date')),
        property_name=prop, check_in=check_in, check_out=check_out, booking_ref=booking_ref,
    )


def parse_airbnb_notification(email: dict):
    body = email.get('body') or ''
    subject = email.get('subject') or ''
    lines = [ln.strip() for ln in body.splitlines()]

    # Role marker distinguishes the guest from our own co-host replies:
    #   'Buchende Person'  -> the booking guest (an INCOMING message we want)
    #   'Co-Gastgeber:in'  -> our team's outgoing reply (NOT a guest message)
    role_idx = next((i for i, s in enumerate(lines) if s == 'Buchende Person'), None)
    if role_idx is None:
        return None  # host/co-host or unrecognized; not an incoming guest message

    name = next((lines[j] for j in range(role_idx - 1, -1, -1) if lines[j]), None)
    message = _collect_message(lines, role_idx + 1, _is_airbnb_stop)

    prop = None
    m = re.search(r'Buchung für\s+[„"]?([^"\n]+?)[""]?(?:,|$)', subject)
    if m:
        prop = m.group(1).strip().strip('„""')

    check_in, check_out = _airbnb_dates(body)
    return ParsedNotification(
        platform='airbnb', gmail_id=email.get('id'), thread_id=email.get('thread_id'),
        guest_name=name, message_text=message, sent_at=_parse_email_date(email.get('date')),
        property_name=prop, check_in=check_in, check_out=check_out, booking_ref=None,
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


def _iso_date(d) -> str:
    """Coerce a date/datetime/'YYYY-MM-DD' string to a 'YYYY-MM-DD' string."""
    if not d:
        return ''
    if hasattr(d, 'isoformat'):
        return d.isoformat()[:10]
    return str(d)[:10]


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

    # Property signal. For Booking, prefer exact apartment-code matching: the
    # email's Unterkunftsname carries the concept name ("Biberburg" = B7) while our
    # Property stores the code, so the loose token overlap is always 0 for Booking.
    # Match boosts; mismatch soft-vetoes (queues for review, blocks auto-insert).
    email_codes = codes_from_property_text(notif.property_name) if notif.platform == 'booking' else set()
    conv_code = conv.get('apartment_code')
    if email_codes and conv_code:
        if conv_code.upper() in email_codes:
            score += 0.30
        else:
            score = max(0.0, score - 0.50)
    elif _property_overlap(notif.property_name, conv.get('property_name')):
        score += 0.30

    # Exact reservation dates are strong corroboration. Compare as ISO strings:
    # the notif carries datetime.date but Conversation stores check_in as a
    # 'YYYY-MM-DD' string, so a raw == would never match.
    if notif.check_in and conv.get('check_in') and _iso_date(notif.check_in) == _iso_date(conv['check_in']):
        score += 0.15
    if notif.check_out and conv.get('check_out') and _iso_date(notif.check_out) == _iso_date(conv['check_out']):
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
    """True if the conversation already has a *Smoobu-origin* guest message within
    ±window_minutes of notif.sent_at. Direction-aware (guest->host), time-fuzzy,
    NOT text-exact (Airbnb auto-translates so text differs between Smoobu and email).

    Prior 'email:' inserts are excluded on purpose: this window only guards against
    re-inserting an email copy of a message that already arrived via Smoobu. Two
    distinct email candidates in the same burst sit seconds apart, so a time-only
    match against other email inserts would wrongly swallow the whole burst after
    the first. Email-vs-email true duplicates are caught exactly by
    _store_message's platform_message_id check, not here."""
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
        db.or_(Message.platform_message_id.is_(None),
               ~Message.platform_message_id.like('email:%')),
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
        # Gmail date window: only notifications newer than this many days are
        # scanned. Default 30 so stale (e.g. May) emails don't get matched.
        'days': int(AISettings.get('email_reconcile_days', '30') or 30),
    }


def promote_email_candidates(conversation_id: int, min_confidence: float) -> list:
    """Insert pending EmailBackfillCandidate rows matched to `conversation_id`
    whose confidence >= min_confidence, oldest first. Dedup-guarded and
    idempotent (confirmed rows are never reconsidered). Returns the ids of NEW
    messages actually inserted — a candidate whose message already exists is
    still marked confirmed but not counted.

    Note: MessageRouter._store_message commits per insert; the trailing commit
    here flushes the final candidate's status change."""
    from types import SimpleNamespace
    from ..models import EmailBackfillCandidate
    from .message_router import get_message_router

    cands = EmailBackfillCandidate.query.filter_by(
        guessed_conversation_id=conversation_id, status='pending'
    ).filter(
        EmailBackfillCandidate.confidence >= min_confidence
    ).order_by(EmailBackfillCandidate.parsed_timestamp.asc()).all()
    if not cands:
        return []

    window = get_reconcile_config()['window_minutes']
    router = get_message_router()
    inserted_ids = []
    for cand in cands:
        shim = SimpleNamespace(sent_at=cand.parsed_timestamp)
        if has_equivalent_message(conversation_id, shim, window):
            continue  # leave pending; an equivalent message already exists
        msg, is_new = router._store_message(
            conversation_id=conversation_id, sender_type='guest',
            content=cand.parsed_text,
            platform_message_id=f"email:{cand.gmail_message_id}",
            sent_at=cand.parsed_timestamp, sent_via_app=False,
        )
        cand.status = 'confirmed'
        if is_new:
            inserted_ids.append(msg.id)
    db.session.commit()
    return inserted_ids


def promote_all_email_candidates(min_confidence: float) -> dict:
    """Flush every pending EmailBackfillCandidate with confidence >= min_confidence
    into its guessed conversation, reusing promote_email_candidates per conversation.
    Records the inserted message ids in AISettings['email_last_flush_message_ids']
    (JSON) so undo_last_flush() can remove exactly those rows.

    Returns {'inserted': N, 'conversations': M, 'skipped_no_conv': K} where
    skipped_no_conv counts pending >= floor candidates that had no conversation to
    file into (they stay in the review tray)."""
    import json
    from ..models import EmailBackfillCandidate, AISettings

    pending = EmailBackfillCandidate.query.filter_by(status='pending').filter(
        EmailBackfillCandidate.confidence >= min_confidence
    ).all()
    conv_ids = sorted({c.guessed_conversation_id for c in pending
                       if c.guessed_conversation_id is not None})
    skipped_no_conv = sum(1 for c in pending if c.guessed_conversation_id is None)

    all_ids = []
    for conv_id in conv_ids:
        all_ids.extend(promote_email_candidates(conv_id, min_confidence))

    # Only overwrite the undo record when this flush actually inserted something.
    # A second click that finds nothing pending must NOT clobber the previous
    # flush's recorded ids, or its inserts become unrecoverable via "Rückgängig".
    if all_ids:
        AISettings.set('email_last_flush_message_ids', json.dumps(all_ids),
                       'Message ids inserted by the last email flush (for undo)')
    return {'inserted': len(all_ids),
            'conversations': len(conv_ids),
            'skipped_no_conv': skipped_no_conv}


def undo_last_flush() -> int:
    """Delete the messages recorded by the last flush and reset their candidates to
    'pending' so they can be re-reviewed or re-flushed. Precise to the recorded batch
    even if the daemon inserted other email messages in the meantime. No-op if there
    is no recorded batch."""
    import json
    from ..models import EmailBackfillCandidate, AISettings, Message

    ids = json.loads(AISettings.get('email_last_flush_message_ids', '[]'))
    if not ids:
        return 0

    removed = 0
    for msg in Message.query.filter(Message.id.in_(ids)).all():
        pmid = msg.platform_message_id or ''
        if pmid.startswith('email:'):
            gmail_id = pmid.split('email:', 1)[1]
            cand = EmailBackfillCandidate.query.filter_by(
                gmail_message_id=gmail_id).first()
            if cand:
                cand.status = 'pending'
        db.session.delete(msg)
        removed += 1

    AISettings.set('email_last_flush_message_ids', '[]')  # commits internally
    return removed


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

# Gmail search — relay-domain funnel. Booking only: Smoobu lacks the Booking
# messaging scope, so Booking guest messages arrive solely as @guest.booking.com
# notification emails. Airbnb messaging works via Smoobu, so it is not scanned.
_PLATFORM_SENDER = {
    'booking': 'from:guest.booking.com',
}


def platform_queries(days: int) -> dict:
    return {p: f'{sender} newer_than:{days}d' for p, sender in _PLATFORM_SENDER.items()}


def _conv_view(conv, channel):
    """One scorer-input dict for a conversation."""
    from ..models import Guest, Property
    guest = Guest.query.get(conv.guest_id)
    prop = Property.query.get(conv.property_id) if conv.property_id else None
    return {
        'conversation_id': conv.id,
        'channel': channel,
        'guest_name': guest.name if guest else None,
        # Smoobu conversation subjects are generic ("Reservation 12345"), which
        # would never overlap a real property name — fall back to None instead.
        'property_name': prop.name if prop else None,
        'apartment_code': code_from_smoobu_id(prop.smoobu_apartment_id) if prop else None,
        'check_in': conv.check_in,
        'check_out': conv.check_out,
    }


def _candidate_views(channel: str):
    """Build scorer input dicts for all conversations on a channel."""
    from ..models import Conversation
    return [_conv_view(conv, channel) for conv in Conversation.query.all()
            if resolve_channel(conv) == channel]


def _safe_query_term(term: str) -> str:
    """Strip characters that would break out of a quoted Gmail search term."""
    return (term or '').replace('"', '')


def _new_stats() -> dict:
    return {'scanned': 0, 'matched': 0, 'auto_inserted': 0, 'queued': 0,
            'skipped_dupe': 0, 'unmatched': 0, 'rejected_unauthenticated': 0,
            'skipped_lowscore': 0}


def _handle_notification_email(email, platform, views, cfg, router, stats,
                               auto_insert_all):
    """Process one notification email into `views`, mutating `stats`.

    Shared by the background scan (auto_insert_all=False: threshold-gated
    insert, else queue to the review tray) and the live per-chat fetch
    (auto_insert_all=True: insert any score>0 match, never queue).
    Anti-spoof and dedup guards are identical in both paths.
    """
    from ..models import EmailBackfillCandidate, Message
    stats['scanned'] += 1
    notif = parse_notification(email)
    if not notif or not notif.message_text or not notif.sent_at:
        return

    # Tier-1 anti-spoof gate: trust only Gmail's own DKIM/DMARC verdict aligned
    # to the platform domain. Spoofed mail is dropped — never inserted or queued.
    authentic, auth_info = verify_sender_authenticity(email, platform)
    if not authentic:
        stats['rejected_unauthenticated'] += 1
        logger.warning("email-reconcile: dropped unauthenticated %s email %s (%s)",
                       platform, notif.gmail_id, auth_info)
        return

    # Skip if already queued/rejected, or already inserted into ANY conversation.
    if EmailBackfillCandidate.query.filter_by(gmail_message_id=notif.gmail_id).first():
        return
    if Message.query.filter_by(platform_message_id=f"email:{notif.gmail_id}").first():
        return

    best, score = pick_best_match(notif, views)
    if not best:
        stats['unmatched'] += 1
        return
    stats['matched'] += 1

    if has_equivalent_message(best['conversation_id'], notif, cfg['window_minutes']):
        stats['skipped_dupe'] += 1
        return

    def _insert():
        router._store_message(
            conversation_id=best['conversation_id'], sender_type='guest',
            content=notif.message_text,
            platform_message_id=f"email:{notif.gmail_id}",
            sent_at=notif.sent_at, sent_via_app=False,
        )
        stats['auto_inserted'] += 1

    if auto_insert_all:
        # Live per-chat path: name-scoped search already narrows to this guest;
        # insert every positive match, skip non-matches (never queue).
        if score > 0:
            _insert()
        else:
            stats['skipped_lowscore'] += 1
        return

    # Background-scan path: threshold-gated auto-insert, otherwise queue for review.
    autoinsert = cfg['autoinsert_booking'] if platform == 'booking' else cfg['autoinsert_airbnb']
    if score >= cfg['threshold'] and autoinsert:
        _insert()
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


def reconcile_from_email(gmail_service, max_per_platform: int = 50) -> dict:
    """Scan Booking notification emails and backfill missing guest messages.

    Returns stats: scanned, matched, auto_inserted, queued, skipped_dupe, unmatched.
    Read-only on Gmail; inserts only into EXISTING conversations.
    """
    from .message_router import get_message_router

    cfg = get_reconcile_config()
    stats = _new_stats()
    if not cfg['enabled']:
        return stats

    router = get_message_router()

    for platform, query in platform_queries(cfg['days']).items():
        try:
            emails = gmail_service.get_recent_emails(
                max_results=max_per_platform, query=query, apply_filter=False)
        except Exception:
            logger.exception("email-reconcile: Gmail fetch failed for %s", platform)
            continue

        views = _candidate_views(platform)
        for email in emails:
            _handle_notification_email(email, platform, views, cfg, router, stats,
                                       auto_insert_all=False)

    logger.info("email-reconcile: %s", stats)
    return stats


# ---------------------------------------------------------------------------
# Live per-chat Booking fetch (on chat open)
# ---------------------------------------------------------------------------

_LIVE_FETCH_DEFAULT_THROTTLE_MIN = 15
# ponytail: in-memory throttle; a server restart at worst permits one extra
# fetch. Move to a Conversation column only if multi-worker fetches become a
# Gmail-quota problem.
_last_live_fetch: dict = {}


def _live_fetch_throttled(conversation_id: int, now: datetime) -> bool:
    from ..models import AISettings
    try:
        mins = int(AISettings.get('email_onopen_live_throttle_minutes',
                                  str(_LIVE_FETCH_DEFAULT_THROTTLE_MIN))
                   or _LIVE_FETCH_DEFAULT_THROTTLE_MIN)
    except (TypeError, ValueError):
        mins = _LIVE_FETCH_DEFAULT_THROTTLE_MIN
    last = _last_live_fetch.get(conversation_id)
    return last is not None and (now - last) < timedelta(minutes=mins)


def fetch_booking_for_conversation(gmail_service, conversation_id: int, now=None) -> dict:
    """Live per-chat Booking fetch: search Gmail scoped to this guest, auto-insert
    every positive match (score>0). Booking-only, throttled, never queues. Returns
    a stats dict (auto_inserted counts inserts; 'reason' set on early no-op)."""
    from ..models import Conversation, Guest, AISettings
    from .message_router import get_message_router

    now = now or datetime.utcnow()
    stats = _new_stats()

    if AISettings.get('email_onopen_live_enabled', 'true') == 'false':
        stats['reason'] = 'disabled'
        return stats

    conv = Conversation.query.get(conversation_id)
    if not conv or resolve_channel(conv) != 'booking':
        stats['reason'] = 'not_booking'
        return stats

    guest = Guest.query.get(conv.guest_id)
    if not guest or not guest.name:
        stats['reason'] = 'no_guest_name'
        return stats

    if _live_fetch_throttled(conversation_id, now):
        stats['reason'] = 'throttled'
        return stats
    # Record the attempt BEFORE fetching so a slow/empty/failed Gmail call still
    # throttles subsequent opens.
    _last_live_fetch[conversation_id] = now

    cfg = get_reconcile_config()
    views = [_conv_view(conv, 'booking')]
    name = _safe_query_term(guest.name)
    query = f'from:guest.booking.com "{name}" newer_than:{cfg["days"]}d'
    try:
        emails = gmail_service.get_recent_emails(
            max_results=50, query=query, apply_filter=False)
    except Exception:
        logger.exception("live booking fetch: Gmail fetch failed for conv %s",
                         conversation_id)
        stats['reason'] = 'gmail_error'
        return stats

    router = get_message_router()
    for email in emails:
        _handle_notification_email(email, 'booking', views, cfg, router, stats,
                                   auto_insert_all=True)

    logger.info("live booking fetch conv %s: %s", conversation_id, stats)
    return stats
