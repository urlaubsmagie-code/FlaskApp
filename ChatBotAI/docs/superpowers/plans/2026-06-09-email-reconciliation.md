# Email Reconciliation Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read Airbnb/Booking.com guest-message notification emails from Gmail and backfill guest messages that Smoobu's API/webhook dropped, into existing conversations, auto-inserting high-confidence matches and queuing fuzzy ones for one-click review.

**Architecture:** A new `services/email_reconcile.py` module holds pure functions (classify → parse → score) plus one DB-touching orchestrator. The orchestrator runs as a new step in the existing 10-minute Smoobu daemon (`app.py`), right after `_reconcile_read_states()`. High-confidence matches insert via the existing idempotent `MessageRouter._store_message()` choke point; low-confidence matches become `EmailBackfillCandidate` rows shown on a new `/chatbot/email-review` page. Trust behavior is driven by `AISettings` keys so Airbnb auto-insert can be enabled later without code changes.

**Tech Stack:** Flask, SQLAlchemy, Flask-Migrate (Alembic), pytest, existing `GmailService` (google-api-python-client), Jinja2 templates.

**Spec:** `docs/superpowers/specs/2026-06-09-email-reconciliation-design.md`

---

## File Structure

**Create:**
- `services/email_reconcile.py` — classification, parsing, scoring (pure) + `reconcile_from_email()` orchestrator + `get_reconcile_config()`.
- `tests/test_email_reconcile.py` — unit tests (pure functions) + DB-backed tests (dedup, orchestrator, endpoints).
- `migrations/versions/p18_email_backfill_candidate.py` — new table.
- `templates/chatbot/email_review.html` — review tray page.

**Modify:**
- `models.py` — add `EmailBackfillCandidate` model.
- `services/gmail_service.py` — `_parse_email()` also captures the `Reply-To` header.
- `app.py` — call `reconcile_from_email()` in the daemon after `_reconcile_read_states()`.
- `routes.py` — page route `/email-review` + API routes (pending-count, confirm, reject).
- `templates/chatbot/base.html` — sidebar nav entry + pending badge.

**Shared types (locked — used across tasks):**

```python
# defined in services/email_reconcile.py (Task 3)
from collections import namedtuple

ParsedNotification = namedtuple("ParsedNotification", [
    "platform",       # 'booking' | 'airbnb'
    "gmail_id",       # str  — Gmail message id (idempotency key)
    "thread_id",      # str
    "guest_name",     # str | None
    "message_text",   # str | None
    "sent_at",        # datetime (naive UTC)
    "property_name",  # str | None
    "check_in",       # datetime.date | None
    "check_out",      # datetime.date | None
    "booking_ref",    # str | None  (Booking only; stored for audit, not used to join yet)
])
```

A **conversation view** passed to the scorer is a plain dict with keys:
`{"conversation_id": int, "channel": 'booking'|'airbnb', "guest_name": str|None, "property_name": str|None, "check_in": date|None, "check_out": date|None}`.

---

## Task 1: `EmailBackfillCandidate` model + migration p18

**Files:**
- Modify: `models.py` (add model after `AISettings`, around line 585)
- Create: `migrations/versions/p18_email_backfill_candidate.py`
- Test: `tests/test_email_reconcile.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_email_reconcile.py`:

```python
import pytest
from datetime import datetime
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, EmailBackfillCandidate


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py::test_email_backfill_candidate_roundtrip -v`
Expected: FAIL with `ImportError: cannot import name 'EmailBackfillCandidate'`

- [ ] **Step 3: Add the model**

In `models.py`, immediately after the `AISettings` class (after line 585), add:

```python
class EmailBackfillCandidate(db.Model):
    """A guest message found in an Airbnb/Booking notification email that may be
    missing from a conversation. High-confidence matches are inserted directly;
    low-confidence ones land here for one-click review. See
    docs/superpowers/specs/2026-06-09-email-reconciliation-design.md.
    """
    __tablename__ = 'email_backfill_candidate'

    id = db.Column(db.Integer, primary_key=True)
    # Idempotency: one candidate per source email. Prevents re-queuing on re-scan.
    gmail_message_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    platform = db.Column(db.String(20), nullable=False)  # 'airbnb' | 'booking'
    parsed_name = db.Column(db.String(255))
    parsed_text = db.Column(db.Text)
    parsed_timestamp = db.Column(db.DateTime)
    guessed_conversation_id = db.Column(
        db.Integer, db.ForeignKey('conversation.id', ondelete='SET NULL'), nullable=True
    )
    confidence = db.Column(db.Float, default=0.0)
    # 'pending' | 'confirmed' | 'rejected'
    status = db.Column(db.String(20), nullable=False, default='pending', index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'gmail_message_id': self.gmail_message_id,
            'platform': self.platform,
            'parsed_name': self.parsed_name,
            'parsed_text': self.parsed_text,
            'parsed_timestamp': self.parsed_timestamp.isoformat() if self.parsed_timestamp else None,
            'guessed_conversation_id': self.guessed_conversation_id,
            'confidence': self.confidence,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<EmailBackfillCandidate {self.platform} {self.status} conf={self.confidence}>'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py::test_email_backfill_candidate_roundtrip -v`
Expected: PASS (in-memory testing DB calls `db.create_all()`, so the table exists automatically)

- [ ] **Step 5: Write the production migration**

Create `migrations/versions/p18_email_backfill_candidate.py`:

```python
"""Add email_backfill_candidate table for the email reconciliation pass.

Revision ID: p18_email_backfill
Revises: p17_guest_dedup
Create Date: 2026-06-09

Stores guest messages discovered in Airbnb/Booking notification emails that
were not auto-inserted (low confidence). Reviewed via /chatbot/email-review.
"""
from alembic import op
import sqlalchemy as sa


revision = 'p18_email_backfill'
down_revision = 'p17_guest_dedup'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'email_backfill_candidate',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('gmail_message_id', sa.String(length=255), nullable=False),
        sa.Column('platform', sa.String(length=20), nullable=False),
        sa.Column('parsed_name', sa.String(length=255), nullable=True),
        sa.Column('parsed_text', sa.Text(), nullable=True),
        sa.Column('parsed_timestamp', sa.DateTime(), nullable=True),
        sa.Column('guessed_conversation_id', sa.Integer(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['guessed_conversation_id'], ['conversation.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_email_backfill_candidate_gmail_message_id',
                    'email_backfill_candidate', ['gmail_message_id'], unique=True)
    op.create_index('ix_email_backfill_candidate_status',
                    'email_backfill_candidate', ['status'], unique=False)


def downgrade():
    op.drop_index('ix_email_backfill_candidate_status', table_name='email_backfill_candidate')
    op.drop_index('ix_email_backfill_candidate_gmail_message_id', table_name='email_backfill_candidate')
    op.drop_table('email_backfill_candidate')
```

- [ ] **Step 6: Verify migration is on the chain (do not run on prod yet)**

Run: `cd ChatBotAI && python -m flask db heads`
Expected: lists `p18_email_backfill` as a head. (If the dev DB is separate, `python -m flask db upgrade` should apply cleanly.)

- [ ] **Step 7: Commit**

```bash
git add ChatBotAI/models.py ChatBotAI/migrations/versions/p18_email_backfill_candidate.py ChatBotAI/tests/test_email_reconcile.py
git commit -m "feat(email-reconcile): add EmailBackfillCandidate model + migration p18

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Capture `Reply-To` in GmailService

Airbnb classification needs the `Reply-To` header (the `@reply.airbnb.com` relay address), which `_parse_email()` does not currently return.

**Files:**
- Modify: `services/gmail_service.py:426-439` (the `_parse_email` return dict)
- Test: `tests/test_email_reconcile.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_email_reconcile.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py::test_parse_email_captures_reply_to -v`
Expected: FAIL with `KeyError: 'reply_to'`

- [ ] **Step 3: Add `reply_to` to the parse output**

In `services/gmail_service.py`, in the `_parse_email` return dict (after the `'to': headers.get('to', ''),` line at 433), add:

```python
            'reply_to': headers.get('reply-to', ''),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py::test_parse_email_captures_reply_to -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/gmail_service.py ChatBotAI/tests/test_email_reconcile.py
git commit -m "feat(email-reconcile): capture Reply-To header in GmailService parse

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Classification (relay-domain funnel)

**Files:**
- Create: `services/email_reconcile.py`
- Test: `tests/test_email_reconcile.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_email_reconcile.py`:

```python
from ChatBotAI.services.email_reconcile import classify_notification


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py -k classify -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ChatBotAI.services.email_reconcile'`

- [ ] **Step 3: Create the module with classification**

Create `services/email_reconcile.py`:

```python
"""Email reconciliation: backfill guest messages from Airbnb/Booking
notification emails that Smoobu dropped.

Pure functions (classify/parse/score) are unit-tested without a DB. The
reconcile_from_email() orchestrator and DB helpers live at the bottom.

See docs/superpowers/specs/2026-06-09-email-reconciliation-design.md.
"""
import logging
import re
from collections import namedtuple
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# --- Relay domains: these subdomains are used ONLY for two-way guest
# messaging, never for confirmations/payouts/reviews. They are the funnel. ---
BOOKING_SENDER_DOMAIN = 'guest.booking.com'
AIRBNB_REPLY_DOMAIN = 'reply.airbnb.com'

# Structural safety-net markers (final reject of anything that slipped through).
BOOKING_MARKER = 'oberhalb dieser Zeile'          # "##- ... Antwort oberhalb dieser Zeile -##"
AIRBNB_MARKER = 'direkt auf diese E-Mail antworten'

ParsedNotification = namedtuple("ParsedNotification", [
    "platform", "gmail_id", "thread_id", "guest_name", "message_text",
    "sent_at", "property_name", "check_in", "check_out", "booking_ref",
])


def classify_notification(email: dict):
    """Return 'booking', 'airbnb', or None for a parsed Gmail email dict."""
    sender = (email.get('sender_email') or '').lower()
    reply_to = (email.get('reply_to') or '').lower()
    body = email.get('body') or ''

    if sender.endswith('@' + BOOKING_SENDER_DOMAIN):
        if BOOKING_MARKER in body:
            return 'booking'
        return 'booking'  # sender domain alone is authoritative; marker is a bonus

    if AIRBNB_REPLY_DOMAIN in reply_to or AIRBNB_REPLY_DOMAIN in (email.get('from') or '').lower():
        return 'airbnb'

    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py -k classify -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/email_reconcile.py ChatBotAI/tests/test_email_reconcile.py
git commit -m "feat(email-reconcile): classify Airbnb/Booking notification emails by relay domain

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Parse notification fields

> **First step — confirm anchors against a real email.** Before relying on the fixtures below, fetch one real Booking and one real Airbnb notification body so the anchor strings are exact. In a Flask shell:
> `python -m flask shell` then
> `from ChatBotAI.services.gmail_service import get_gmail_service; svc=get_gmail_service(); [print(repr(e['body'])) for e in svc.get_recent_emails(max_results=3, query='from:guest.booking.com', apply_filter=False)]`
> Adjust the anchor constants / fixtures in this task if the live text differs. The parser is anchor-driven, so only the constants change.

**Files:**
- Modify: `services/email_reconcile.py`
- Test: `tests/test_email_reconcile.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_email_reconcile.py`:

```python
from datetime import date
from ChatBotAI.services.email_reconcile import parse_notification

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py -k parse_booking or parse_airbnb -v`
Expected: FAIL with `ImportError: cannot import name 'parse_notification'`

- [ ] **Step 3: Implement parsing**

Append to `services/email_reconcile.py`:

```python
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
            # value may be inline ("Label: value") or on the next non-empty line
            inline = ln[len(label):].strip().lstrip(':').strip()
            if inline:
                return inline
            for nxt in lines[i + 1:]:
                if nxt:
                    return nxt
    return None


def _text_between(body: str, start_label: str, stop_labels):
    """Collect lines after start_label until a stop label/blank-marker. Trims chrome."""
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
    booking_ref = sender.split('@')[0].split('-')[0] or None
    name = _value_after_label(body, 'Name des Gastes')
    message = _text_between(body, 'Nachricht von',
                            stop_labels=['Antworten', 'Buchungsangaben', 'Buchungsnummer'])
    # "Nachricht von Carolin Janowski:" -> drop the name prefix from the first line
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
    # Guest name is the line immediately before "Buchende Person".
    name = None
    for i, ln in enumerate(lines):
        if ln.startswith('Buchende Person') and i > 0:
            name = lines[i - 1]
            break
    # Message: lines after "Buchende Person" until the translation separator / CTA.
    message = _text_between(body, 'Buchende Person',
                            stop_labels=['Die ursprüngliche Nachricht', 'Antworten',
                                         'Du kannst auch direkt'])
    # Property name = the listing title in the subject (after "Buchung für").
    prop = None
    m = re.search(r'Buchung für\s+[„"]?([^"\n]+?)["“]?(?:,|$)', subject)
    if m:
        prop = m.group(1).strip().strip('„"“')
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py -k "parse_booking or parse_airbnb" -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/email_reconcile.py ChatBotAI/tests/test_email_reconcile.py
git commit -m "feat(email-reconcile): parse guest name/message/dates/property from notifications

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Match scoring + best-match picker

**Files:**
- Modify: `services/email_reconcile.py`
- Test: `tests/test_email_reconcile.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_email_reconcile.py`:

```python
from datetime import date as _d
from ChatBotAI.services.email_reconcile import score_conversation_match, pick_best_match


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py -k "match" -v`
Expected: FAIL with `ImportError: cannot import name 'score_conversation_match'`

- [ ] **Step 3: Implement scoring**

Append to `services/email_reconcile.py`:

```python
from .guest_matching import normalize_name  # DRY: reuse existing normalizer


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py -k "match" -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/email_reconcile.py ChatBotAI/tests/test_email_reconcile.py
git commit -m "feat(email-reconcile): confidence scoring + best-match picker

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Fuzzy dedup check (DB)

A parsed message is "already have it" if the conversation has a guest message within ±N minutes (translation means text won't match exactly).

**Files:**
- Modify: `services/email_reconcile.py`
- Test: `tests/test_email_reconcile.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_email_reconcile.py`:

```python
from ChatBotAI.models import Guest, Conversation, Message
from ChatBotAI.services.email_reconcile import has_equivalent_message


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py -k dedup -v`
Expected: FAIL with `ImportError: cannot import name 'has_equivalent_message'`

- [ ] **Step 3: Implement dedup**

Append to `services/email_reconcile.py`:

```python
from datetime import timedelta


def has_equivalent_message(conversation_id: int, notif, window_minutes: int = 10) -> bool:
    """True if the conversation already has a guest message within ±window_minutes
    of notif.sent_at. Direction-aware (guest->host), time-fuzzy, NOT text-exact
    (Airbnb auto-translates so text differs between Smoobu and email)."""
    from .models import Message
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
```

Add this import near the top of the module (after `logger = ...`):

```python
from .models import db
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py -k dedup -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/email_reconcile.py ChatBotAI/tests/test_email_reconcile.py
git commit -m "feat(email-reconcile): fuzzy (time+direction) dedup against existing messages

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Config helper + channel resolver

`AISettings` stores values as strings. Provide typed accessors with defaults, and a helper to resolve a conversation's channel (stored either on `Conversation.platform` or as a `booking_channel` GuestDetail).

**Files:**
- Modify: `services/email_reconcile.py`
- Test: `tests/test_email_reconcile.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_email_reconcile.py`:

```python
from ChatBotAI.models import AISettings, GuestDetail
from ChatBotAI.services.email_reconcile import get_reconcile_config, resolve_channel


def test_config_defaults(app):
    cfg = get_reconcile_config()
    assert cfg['enabled'] is True
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
```

> If `GuestDetail`'s column names differ from `detail_type/detail_key/detail_value`, adjust this test and `resolve_channel` to match `models.py`. Verify with `grep -n "class GuestDetail" -A 20 ChatBotAI/models.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py -k "config or resolve_channel" -v`
Expected: FAIL with `ImportError: cannot import name 'get_reconcile_config'`

- [ ] **Step 3: Implement config + channel resolver**

Append to `services/email_reconcile.py`:

```python
def _as_bool(val, default=False):
    if val is None:
        return default
    return str(val).strip().lower() in ('1', 'true', 'yes', 'on')


def get_reconcile_config() -> dict:
    """Typed reconciliation settings with defaults. See spec §7/§9."""
    from .models import AISettings
    try:
        threshold = float(AISettings.get('email_confidence_threshold', '0.8'))
    except (TypeError, ValueError):
        threshold = 0.8
    return {
        'enabled': _as_bool(AISettings.get('email_reconcile_enabled', 'true'), True),
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
    from .models import GuestDetail
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py -k "config or resolve_channel" -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/email_reconcile.py ChatBotAI/tests/test_email_reconcile.py
git commit -m "feat(email-reconcile): typed config accessors + conversation channel resolver

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Orchestrator `reconcile_from_email()`

Ties it together: fetch per platform, classify+parse, build candidate views from the DB, match, dedup, then auto-insert (≥ threshold AND that platform's autoinsert enabled) or queue an `EmailBackfillCandidate`. Returns a stats dict.

**Files:**
- Modify: `services/email_reconcile.py`
- Test: `tests/test_email_reconcile.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_email_reconcile.py`:

```python
from ChatBotAI.services.email_reconcile import reconcile_from_email


class FakeGmail:
    """Returns canned emails per query; records nothing else."""
    def __init__(self, by_query):
        self._by_query = by_query
    def get_recent_emails(self, max_results=10, query=None, apply_filter=True):
        return self._by_query.get(query, [])


def test_orchestrator_autoinserts_high_confidence_booking(app):
    # Existing booking conversation with NO message in the window.
    g = Guest(name='Carolin Janowski'); db.session.add(g); db.session.flush()
    conv = Conversation(guest_id=g.id, platform='booking',
                        check_in=_d(2026, 6, 12), check_out=_d(2026, 6, 14))
    db.session.add(conv); db.session.commit()

    email = _email(id='gb1', thread_id='tb1',
                   sender_email='5843975682-x@guest.booking.com',
                   date='Mon, 09 Jun 2026 13:24:00 +0200', body=BOOKING_BODY)
    gmail = FakeGmail({'from:guest.booking.com newer_than:90d': [email]})

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

    stats = reconcile_from_email(gmail)
    assert stats['skipped_dupe'] == 1
    assert Message.query.filter_by(conversation_id=conv.id).count() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py -k orchestrator -v`
Expected: FAIL with `ImportError: cannot import name 'reconcile_from_email'`

- [ ] **Step 3: Implement the orchestrator**

Append to `services/email_reconcile.py`:

```python
# Gmail search queries — relay-domain funnel + 90-day window (matches Smoobu sync).
PLATFORM_QUERIES = {
    'booking': 'from:guest.booking.com newer_than:90d',
    'airbnb': 'from:airbnb.com newer_than:90d',
}


def _candidate_views(channel: str):
    """Build scorer input dicts for all conversations on a channel (last 90d)."""
    from .models import Conversation, Guest, Property
    views = []
    convs = Conversation.query.all()
    for conv in convs:
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
    from .models import EmailBackfillCandidate
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

            # Already queued (pending OR rejected) for this exact email? skip.
            if EmailBackfillCandidate.query.filter_by(gmail_message_id=notif.gmail_id).first():
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
```

> **Note:** confirm `get_message_router` is the accessor name with `grep -n "def get_message_router" ChatBotAI/services/message_router.py`. If it differs, adjust the import.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py -k orchestrator -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the whole module's tests**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py -v`
Expected: PASS (all tests so far)

- [ ] **Step 6: Commit**

```bash
git add ChatBotAI/services/email_reconcile.py ChatBotAI/tests/test_email_reconcile.py
git commit -m "feat(email-reconcile): orchestrator (fetch->match->dedup->insert/queue)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Wire the orchestrator into the daemon

**Files:**
- Modify: `app.py` (inside `_run_one_sync`, after the `_reconcile_read_states()` block, around line 367)

- [ ] **Step 1: Add the reconciliation call after read-state reconciliation**

In `app.py`, in `_run_one_sync`, immediately after the existing block:

```python
                                fixed = _reconcile_read_states()
                                if fixed > 0:
                                    logger.info("Background sync: reconciled %d conversations (already answered)", fixed)
```

add:

```python
                                # Email reconciliation: backfill guest messages Smoobu
                                # dropped, using Airbnb/Booking notification emails as an
                                # independent source. Guarded by AISettings + Gmail config.
                                try:
                                    from .services.email_reconcile import reconcile_from_email, get_reconcile_config
                                    if get_reconcile_config()['enabled']:
                                        from .services.gmail_service import get_gmail_service
                                        gmail = get_gmail_service()
                                        if gmail and gmail.is_authenticated():
                                            estats = reconcile_from_email(gmail)
                                            if estats['auto_inserted'] or estats['queued']:
                                                logger.info(
                                                    "Email reconcile: inserted %d, queued %d (scanned %d)",
                                                    estats['auto_inserted'], estats['queued'], estats['scanned'])
                                                print(
                                                    f"[ChatBotAI] Email reconcile: +{estats['auto_inserted']} inserted, "
                                                    f"{estats['queued']} queued (scanned {estats['scanned']})", flush=True)
                                except Exception:
                                    logger.exception("Email reconciliation error")
```

> Confirm the Gmail accessor + auth-check names: `grep -n "def get_gmail_service\|def is_authenticated\|def is_configured" ChatBotAI/services/gmail_service.py`. If the auth check is named differently (e.g. `is_configured()`), use that. If neither exists, guard with `try/except` around the first fetch instead (the orchestrator already swallows fetch errors).

- [ ] **Step 2: Smoke-test the import path**

Run: `cd ChatBotAI && python -c "import app; from services.email_reconcile import reconcile_from_email; print('ok')"`
Expected: prints `ok` with no ImportError. (Run from a context where the package imports cleanly; otherwise `python -m pytest ChatBotAI/tests/test_email_reconcile.py -v` still passing is sufficient evidence the module is healthy.)

- [ ] **Step 3: Commit**

```bash
git add ChatBotAI/app.py
git commit -m "feat(email-reconcile): run reconciliation pass in the 10-min daemon

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Review API + page route

**Files:**
- Modify: `routes.py` (add near the other page routes, ~line 372, and an API section)
- Test: `tests/test_email_reconcile.py`

- [ ] **Step 1: Write the failing test (confirm + reject endpoints)**

Append to `tests/test_email_reconcile.py`:

```python
@pytest.fixture
def client(app):
    return app.test_client()


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
```

> These routes are under `@login_required`. If the test client is redirected (302) to login, add a login helper mirroring an existing authenticated route test, or temporarily assert on the JSON for a logged-in session. Check how other authed routes are tested with `grep -rn "test_client\|login" ChatBotAI/tests/`. If no auth-test pattern exists, set `app.config['LOGIN_DISABLED'] = True` in the `client` fixture.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py -k "confirm or reject or pending_count" -v`
Expected: FAIL (404 — routes don't exist)

- [ ] **Step 3: Add the routes**

In `routes.py`, add the page route near the other page routes (after `knowledge_base`, ~line 378):

```python
@chatbot_bp.route('/email-review')
@login_required
def email_review():
    """Review tray for low-confidence email-backfill candidates."""
    candidates = EmailBackfillCandidate.query.filter_by(status='pending').order_by(
        EmailBackfillCandidate.created_at.desc()).all()
    rows = []
    for c in candidates:
        conv = Conversation.query.get(c.guessed_conversation_id) if c.guessed_conversation_id else None
        guest = Guest.query.get(conv.guest_id) if conv else None
        rows.append({'candidate': c, 'conversation': conv, 'guest': guest})
    return render_template('chatbot/email_review.html', rows=rows)
```

Ensure `EmailBackfillCandidate` is imported at the top of `routes.py` alongside the other models (find the existing `from .models import ...` line and add it).

Then add the API routes (place near other `/api/*` routes):

```python
@chatbot_bp.route('/api/email-review/pending-count')
@login_required
def email_review_pending_count():
    count = EmailBackfillCandidate.query.filter_by(status='pending').count()
    return jsonify({'count': count})


@chatbot_bp.route('/api/email-review/<int:candidate_id>/confirm', methods=['POST'])
@login_required
def email_review_confirm(candidate_id):
    from .services.message_router import get_message_router
    cand = EmailBackfillCandidate.query.get_or_404(candidate_id)
    if cand.status != 'pending':
        return jsonify({'success': False, 'error': 'already handled'}), 400
    # Allow the reviewer to correct the target conversation.
    target_id = request.get_json(silent=True) or {}
    conv_id = target_id.get('conversation_id') or cand.guessed_conversation_id
    if not conv_id:
        return jsonify({'success': False, 'error': 'no conversation'}), 400
    router = get_message_router()
    router._store_message(
        conversation_id=conv_id, sender_type='guest', content=cand.parsed_text,
        platform_message_id=f"email:{cand.gmail_message_id}", sent_at=cand.parsed_timestamp,
        sent_via_app=False,
    )
    cand.status = 'confirmed'
    db.session.commit()
    return jsonify({'success': True})


@chatbot_bp.route('/api/email-review/<int:candidate_id>/reject', methods=['POST'])
@login_required
def email_review_reject(candidate_id):
    cand = EmailBackfillCandidate.query.get_or_404(candidate_id)
    cand.status = 'rejected'
    db.session.commit()
    return jsonify({'success': True})
```

Confirm `db` is imported in `routes.py` (`grep -n "from .models import" routes.py`); add `db` if missing.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py -k "confirm or reject or pending_count" -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/routes.py ChatBotAI/tests/test_email_reconcile.py
git commit -m "feat(email-reconcile): review page + confirm/reject/pending-count API

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Review page template + sidebar nav + badge

**Files:**
- Create: `templates/chatbot/email_review.html`
- Modify: `templates/chatbot/base.html` (sidebar nav, after the knowledge `<li>` ~line 60)

- [ ] **Step 1: Create the template**

Create `templates/chatbot/email_review.html`. Mirror the structure of an existing simple page (e.g. open `templates/chatbot/knowledge.html` for the `{% extends %}` / block names — use the SAME block name it uses, typically `{% block content %}`):

```html
{% extends "chatbot/base.html" %}
{% block content %}
<div class="page-header">
  <h1 data-i18n="emailReview.title">E-Mail-Abgleich</h1>
  <p class="page-subtitle" data-i18n="emailReview.subtitle">
    Nachrichten aus Airbnb-/Booking-E-Mails, die Smoobu evtl. verpasst hat.
  </p>
</div>

{% if not rows %}
  <div class="empty-state" data-i18n="emailReview.empty">Nichts zu überprüfen.</div>
{% else %}
  <div class="email-review-list">
    {% for row in rows %}
    <div class="email-review-card" data-candidate-id="{{ row.candidate.id }}">
      <div class="erc-head">
        <span class="erc-platform erc-{{ row.candidate.platform }}">{{ row.candidate.platform }}</span>
        <span class="erc-conf">{{ '%.0f' % (row.candidate.confidence * 100) }}%</span>
        <span class="erc-time">{{ row.candidate.parsed_timestamp }}</span>
      </div>
      <div class="erc-name">{{ row.candidate.parsed_name }}</div>
      <div class="erc-text">{{ row.candidate.parsed_text }}</div>
      <div class="erc-match">
        {% if row.conversation %}
          → <a href="{{ url_for('chatbot.conversation_view', conversation_id=row.conversation.id) }}">
              {{ row.guest.name if row.guest else 'Konversation' }} #{{ row.conversation.id }}</a>
        {% else %}
          <span class="erc-nomatch" data-i18n="emailReview.noMatch">keine Konversation gefunden</span>
        {% endif %}
      </div>
      <div class="erc-actions">
        <button class="btn btn-primary" onclick="confirmCandidate({{ row.candidate.id }})"
                data-i18n="emailReview.confirm">Bestätigen</button>
        <button class="btn btn-secondary" onclick="rejectCandidate({{ row.candidate.id }})"
                data-i18n="emailReview.reject">Verwerfen</button>
      </div>
    </div>
    {% endfor %}
  </div>
{% endif %}

<script>
async function _post(url) {
  const r = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}});
  return r.ok;
}
async function confirmCandidate(id) {
  if (await _post(`/chatbot/api/email-review/${id}/confirm`)) {
    document.querySelector(`[data-candidate-id="${id}"]`)?.remove();
  }
}
async function rejectCandidate(id) {
  if (await _post(`/chatbot/api/email-review/${id}/reject`)) {
    document.querySelector(`[data-candidate-id="${id}"]`)?.remove();
  }
}
</script>
{% endblock %}
```

> Confirm the conversation route endpoint name with `grep -n "def conversation" ChatBotAI/routes.py` — adjust `chatbot.conversation_view` / the `conversation_id` arg name if different. Confirm the content block name matches `base.html`.

- [ ] **Step 2: Add the sidebar nav entry + badge**

In `templates/chatbot/base.html`, after the knowledge-base `<li class="nav-item">…</li>` (~line 60), add:

```html
                <li class="nav-item">
                    <a href="{{ url_for('chatbot.email_review') }}" class="nav-link {% if request.endpoint == 'chatbot.email_review' %}active{% endif %}">
                        <span class="nav-icon">✉️</span>
                        <span data-i18n="nav.emailReview">E-Mail-Abgleich</span>
                        <span id="emailReviewBadge" class="nav-badge" style="display:none"></span>
                    </a>
                </li>
```

Then, near the end of `base.html` before `</body>` (or in the existing shared script block), add a small badge updater:

```html
<script>
(function refreshEmailReviewBadge() {
  fetch('/chatbot/api/email-review/pending-count')
    .then(r => r.ok ? r.json() : {count: 0})
    .then(d => {
      const b = document.getElementById('emailReviewBadge');
      if (!b) return;
      if (d.count > 0) { b.textContent = d.count; b.style.display = ''; }
      else { b.style.display = 'none'; }
    }).catch(() => {});
  setTimeout(refreshEmailReviewBadge, 60000);
})();
</script>
```

- [ ] **Step 3: Manual verification in the running app**

Run the dev server (`python -m ChatBotAI.run`), log in, and:
1. Insert a test pending candidate via `flask shell` (mirror `_seed_pending_candidate`).
2. Confirm the sidebar badge shows `1`, the `/chatbot/email-review` page lists it, **Bestätigen** inserts the message into the linked conversation and removes the card, **Verwerfen** removes it without inserting.

Expected: all behaviors as described; no console errors.

- [ ] **Step 4: Commit**

```bash
git add ChatBotAI/templates/chatbot/email_review.html ChatBotAI/templates/chatbot/base.html
git commit -m "feat(email-reconcile): review tray page + sidebar nav badge

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Settings UI toggles + i18n + cache bumps

Surface the trust toggles (spec §9) and add translation keys.

**Files:**
- Modify: `templates/chatbot/settings.html` (add an "E-Mail-Abgleich" section)
- Modify: `static/js/i18n.js` (add `nav.emailReview`, `emailReview.*` keys for de + en; bump version)
- Modify: `templates/chatbot/base.html` (bump the i18n `?v=` query string)

- [ ] **Step 1: Add the settings section**

In `templates/chatbot/settings.html`, find how existing AISettings are rendered/saved (`grep -n "ai_settings\|AISettings\|name=" templates/chatbot/settings.html` and the settings-save route in `routes.py`). Add a section with these four keys, using the SAME form/save mechanism the page already uses for other settings:

- `email_reconcile_enabled` (checkbox, default on)
- `email_autoinsert_booking` (checkbox, default on)
- `email_autoinsert_airbnb` (checkbox, default off — labelled "Airbnb-Treffer automatisch einfügen (sobald zuverlässig)")
- `email_confidence_threshold` (number 0–1, step 0.05, default 0.8)

> The existing settings save path persists arbitrary keys via `AISettings.set`. If the page POSTs all named inputs generically, just adding the inputs is enough. If keys are whitelisted server-side, add these four to that whitelist in `routes.py`.

- [ ] **Step 2: Add i18n keys**

In `static/js/i18n.js`, add to BOTH the German and English dictionaries (matching the file's existing structure):

```javascript
// German
'nav.emailReview': 'E-Mail-Abgleich',
'emailReview.title': 'E-Mail-Abgleich',
'emailReview.subtitle': 'Nachrichten aus Airbnb-/Booking-E-Mails, die Smoobu evtl. verpasst hat.',
'emailReview.empty': 'Nichts zu überprüfen.',
'emailReview.confirm': 'Bestätigen',
'emailReview.reject': 'Verwerfen',
'emailReview.noMatch': 'keine Konversation gefunden',
```

```javascript
// English
'nav.emailReview': 'Email Reconcile',
'emailReview.title': 'Email Reconcile',
'emailReview.subtitle': 'Messages from Airbnb/Booking emails that Smoobu may have missed.',
'emailReview.empty': 'Nothing to review.',
'emailReview.confirm': 'Confirm',
'emailReview.reject': 'Reject',
'emailReview.noMatch': 'no conversation found',
```

- [ ] **Step 3: Bump cache version**

In `templates/chatbot/base.html`, find the i18n script tag (`grep -n "i18n.js?v=" templates/chatbot/base.html`) and increment the version (per memory the i18n is at v25 → set `?v=26`).

- [ ] **Step 4: Manual verification**

Reload the app with a hard refresh, switch language between DE/EN, confirm the nav label and page strings translate, and that toggling `email_autoinsert_airbnb` in Settings persists (re-open Settings → still checked).

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/templates/chatbot/settings.html ChatBotAI/static/js/i18n.js ChatBotAI/templates/chatbot/base.html
git commit -m "feat(email-reconcile): settings toggles + i18n strings + cache bump

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] **Run the full test suite**

Run: `python -m pytest ChatBotAI/tests/ -v`
Expected: all pass (existing tests + new `test_email_reconcile.py`).

- [ ] **Apply migration to the dev DB** (prod is applied separately by the user)

Run: `cd ChatBotAI && python -m flask db upgrade`
Expected: `p18_email_backfill` applies; `email_backfill_candidate` table exists.

- [ ] **End-to-end smoke** (with real Gmail, dev):
  Trigger one daemon cycle (restart dev server or call the manual sync route), watch the console for `Email reconcile: +N inserted, M queued`. Open `/chatbot/email-review` and verify any queued Airbnb candidates appear and confirm/reject works.

---

## Post-implementation notes (for the user / follow-ups, NOT in scope here)

- **Make Booking exact:** check whether Smoobu's reservation payload exposes the channel reference number (Booking's `5843975682`). If yes, persist it on `Conversation` and add an exact ref-join to `score_conversation_match` (Booking → certain).
- **Retire the review tray:** once Airbnb matching is trusted, set `email_autoinsert_airbnb = true` (and/or lower `email_confidence_threshold`) in Settings — no code change.
- **Deferred (YAGNI):** reply-by-email-out, creating new conversations from email-only, owner-message backfill.
