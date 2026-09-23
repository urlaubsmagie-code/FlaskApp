# Email-Thread Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backfill existing conversations with the missing two-sided messages (guest *and* our team's replies) found in the guest's Gmail email thread, when Smoobu didn't deliver them.

**Architecture:** A new focused module `services/email_thread_backfill.py` reuses the hardened pieces of `services/email_reconcile.py` and `services/gmail_service.py`. Matching is anchored on the guest's real email address (strong tier, auto-inserts) with a name-fallback tier (confirmation-gated, button only). Messages insert via `MessageRouter._store_message` (idempotent by `platform_message_id = "email:<gmail_id>"`), with the orchestrator owning conversation-timestamp updates so old history never resurfaces a chat. A per-chat button ships first; an opt-in background pass follows.

**Tech Stack:** Python 3.14, Flask, SQLAlchemy, Flask-Login, pytest. Google Gmail API via the existing `GmailService`.

## Global Constraints

- **Insert path:** always `MessageRouter._store_message(conversation_id, sender_type, content, platform_message_id, sent_at, sent_via_app)` → returns `(Message, is_new: bool)`. Never insert `Message()` directly.
- **Idempotency id:** `platform_message_id = f"email:{gmail_id}"` (same convention as `email_reconcile`/`email_review`). Gives cross-feature dedup for free.
- **`sent_via_app = False`** on every backfilled message (synced, not app-sent — keeps statistics correct).
- **No resurfacing:** after inserting, set `conv.last_message_at = max(existing_last_message_at, newest_inserted_sent_at)`; bump `conv.updated_at = datetime.utcnow()`. Never set `last_message_at` to "now" for historical messages.
- **Direction:** sender address ∈ host set → `sender_type='owner'`; else `'guest'`.
- **Anti-spoof:** `guest`-direction messages must pass a generic DKIM/DMARC check; `owner`-direction messages (from our own account) are trusted without the check.
- **Scope:** existing conversations only. Never create conversations. No AI/memory pass (set `is_processed=True` on inserts).
- **Settings live in `AISettings`** via `AISettings.get(key, default)` / `AISettings.set(key, value)`.
- **TDD:** every function gets a failing test first. Tests use `create_app(config_map['testing'])`.

---

### Task 1: Module skeleton — host addresses & config

**Files:**
- Create: `services/email_thread_backfill.py`
- Test: `tests/test_email_thread_backfill.py`

**Interfaces:**
- Produces:
  - `DEFAULT_HOST_ADDRESSES: set[str]`
  - `get_host_addresses() -> set[str]` — lowercased host email set from `AISettings` key `email_host_addresses` (comma-separated), falling back to defaults.
  - `get_thread_backfill_config() -> dict` — keys `{'auto_enabled': bool, 'lookback_days': int, 'window_minutes': int}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_email_thread_backfill.py
import pytest
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, AISettings


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def test_host_addresses_default_and_override(app):
    from ChatBotAI.services.email_thread_backfill import get_host_addresses
    # defaults present, lowercased
    defaults = get_host_addresses()
    assert 'buchungsanfrage.urlaubsmagie@gmail.com' in defaults
    assert 'urlaubsmagie@host.smoobu.com' in defaults
    # override via settings (comma-separated, mixed case + spaces)
    AISettings.set('email_host_addresses', 'Foo@Bar.com, baz@qux.de')
    over = get_host_addresses()
    assert over == {'foo@bar.com', 'baz@qux.de'}


def test_thread_backfill_config_defaults(app):
    from ChatBotAI.services.email_thread_backfill import get_thread_backfill_config
    cfg = get_thread_backfill_config()
    assert cfg['auto_enabled'] is False
    assert cfg['lookback_days'] == 180
    assert cfg['window_minutes'] == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_email_thread_backfill.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ChatBotAI.services.email_thread_backfill'`

- [ ] **Step 3: Write minimal implementation**

```python
# services/email_thread_backfill.py
"""Reconstruct existing conversations from two-sided Gmail email threads.

See docs/superpowers/specs/2026-06-26-email-thread-backfill-design.md.
"""
import logging
from typing import Optional

from ..models import AISettings

logger = logging.getLogger(__name__)

DEFAULT_HOST_ADDRESSES = {
    'buchungsanfrage.urlaubsmagie@gmail.com',
    'buchungsanfrage.urlaubsmagie@googlemail.com',
    'urlaubsmagie@gmail.com',
    'urlaubsmagie@host.smoobu.com',
}


def get_host_addresses() -> set:
    """Lowercased set of addresses that count as 'us' (owner side)."""
    raw = AISettings.get('email_host_addresses', None)
    if not raw:
        return set(DEFAULT_HOST_ADDRESSES)
    return {part.strip().lower() for part in raw.split(',') if part.strip()}


def get_thread_backfill_config() -> dict:
    """Typed settings for thread backfill, with safe defaults."""
    def _bool(key, default):
        return AISettings.get(key, 'true' if default else 'false') == 'true'

    def _int(key, default):
        try:
            return int(AISettings.get(key, str(default)))
        except (TypeError, ValueError):
            return default

    return {
        'auto_enabled': _bool('email_thread_backfill_auto', False),
        'lookback_days': _int('email_thread_backfill_lookback_days', 180),
        'window_minutes': _int('email_thread_backfill_window_minutes', 10),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest ChatBotAI/tests/test_email_thread_backfill.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/email_thread_backfill.py ChatBotAI/tests/test_email_thread_backfill.py
git commit -m "feat(email-backfill): module skeleton — host addresses + config"
```

---

### Task 2: Direction, junk filter, usable-email detection

**Files:**
- Modify: `services/email_thread_backfill.py`
- Test: `tests/test_email_thread_backfill.py`

**Interfaces:**
- Consumes: `get_host_addresses()` (Task 1).
- Produces:
  - `classify_direction(email: dict, host_addresses: set) -> str` — `'owner'` | `'guest'`.
  - `is_backfillable(email: dict, cleaned_body: str) -> bool` — False for bounces / empty bodies.
  - `RELAY_ALIAS_DOMAINS: tuple[str, ...]`
  - `guest_email_is_usable(email_str: Optional[str]) -> bool`
- Email dict shape (from `GmailService._parse_email`): keys `id, thread_id, subject, sender_email, to, date, body, authentication_results (list), snippet`.

- [ ] **Step 1: Write the failing test**

```python
def test_classify_direction(app):
    from ChatBotAI.services.email_thread_backfill import classify_direction, get_host_addresses
    hosts = get_host_addresses()
    assert classify_direction({'sender_email': 'buchungsanfrage.urlaubsmagie@gmail.com'}, hosts) == 'owner'
    assert classify_direction({'sender_email': 'GUEST@gmail.com'}, hosts) == 'guest'  # case-insensitive


def test_is_backfillable_filters_junk(app):
    from ChatBotAI.services.email_thread_backfill import is_backfillable
    assert is_backfillable({'sender_email': 'g@x.com', 'subject': 'Re: Frage'}, 'Hallo, eine Frage') is True
    # bounce by subject
    assert is_backfillable({'sender_email': 'g@x.com', 'subject': 'Message not delivered'}, 'x') is False
    # bounce by sender
    assert is_backfillable({'sender_email': 'mailer-daemon@googlemail.com', 'subject': 'Re'}, 'x') is False
    # empty cleaned body
    assert is_backfillable({'sender_email': 'g@x.com', 'subject': 'Re'}, '   ') is False


def test_guest_email_is_usable(app):
    from ChatBotAI.services.email_thread_backfill import guest_email_is_usable
    assert guest_email_is_usable('dbrachholz@gmail.com') is True
    assert guest_email_is_usable('') is False
    assert guest_email_is_usable(None) is False
    assert guest_email_is_usable('12345-abc@guest.booking.com') is False  # relay alias
    assert guest_email_is_usable('x@reply.airbnb.com') is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_email_thread_backfill.py -k "direction or backfillable or usable" -q`
Expected: FAIL — `ImportError: cannot import name 'classify_direction'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to services/email_thread_backfill.py

RELAY_ALIAS_DOMAINS = ('@guest.booking.com', '@reply.airbnb.com', '@guest.airbnb.com', '@m.booking.com')
_BOUNCE_SUBJECT_PREFIXES = ('message not delivered', 'mail delivery failed', 'undeliverable', 'delivery status notification')


def classify_direction(email: dict, host_addresses: set) -> str:
    sender = (email.get('sender_email') or '').strip().lower()
    return 'owner' if sender in host_addresses else 'guest'


def is_backfillable(email: dict, cleaned_body: str) -> bool:
    if not cleaned_body or not cleaned_body.strip():
        return False
    sender = (email.get('sender_email') or '').strip().lower()
    if sender.startswith('mailer-daemon@') or 'postmaster@' in sender:
        return False
    subject = (email.get('subject') or '').strip().lower()
    if any(subject.startswith(p) for p in _BOUNCE_SUBJECT_PREFIXES):
        return False
    return True


def guest_email_is_usable(email_str: Optional[str]) -> bool:
    if not email_str:
        return False
    addr = email_str.strip().lower()
    if '@' not in addr:
        return False
    return not any(addr.endswith(dom) for dom in RELAY_ALIAS_DOMAINS)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest ChatBotAI/tests/test_email_thread_backfill.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/email_thread_backfill.py ChatBotAI/tests/test_email_thread_backfill.py
git commit -m "feat(email-backfill): direction classify, junk filter, usable-email check"
```

---

### Task 3: Generic anti-spoof check for guest messages

**Files:**
- Modify: `services/email_thread_backfill.py`
- Test: `tests/test_email_thread_backfill.py`

**Interfaces:**
- Produces: `guest_message_is_authentic(email: dict) -> bool` — True if any `authentication_results` line shows `dmarc=pass` or `dkim=pass`. Empty/missing AR → False (conservative).

Rationale: the existing `verify_sender_authenticity` is domain-aligned to booking/airbnb relay domains, which does not apply to arbitrary direct-guest domains (gmail.com, gmx.de, …). We use a generic DKIM/DMARC-pass check instead.

- [ ] **Step 1: Write the failing test**

```python
def test_guest_message_is_authentic(app):
    from ChatBotAI.services.email_thread_backfill import guest_message_is_authentic
    assert guest_message_is_authentic({'authentication_results': [
        'mx.google.com; dkim=pass header.i=@gmail.com; spf=pass; dmarc=pass']}) is True
    assert guest_message_is_authentic({'authentication_results': [
        'mx.google.com; dkim=fail; spf=softfail; dmarc=fail']}) is False
    assert guest_message_is_authentic({'authentication_results': []}) is False
    assert guest_message_is_authentic({}) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_email_thread_backfill.py -k authentic -q`
Expected: FAIL — `ImportError: cannot import name 'guest_message_is_authentic'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to services/email_thread_backfill.py

def guest_message_is_authentic(email: dict) -> bool:
    """Generic DKIM/DMARC pass check for inbound guest emails (anti-spoof)."""
    ar_list = email.get('authentication_results') or []
    blob = ' '.join(ar_list).lower()
    return ('dmarc=pass' in blob) or ('dkim=pass' in blob)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest ChatBotAI/tests/test_email_thread_backfill.py -k authentic -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/email_thread_backfill.py ChatBotAI/tests/test_email_thread_backfill.py
git commit -m "feat(email-backfill): generic DKIM/DMARC anti-spoof check for guest messages"
```

---

### Task 4: Cross-source dedup helper

**Files:**
- Modify: `services/email_thread_backfill.py`
- Test: `tests/test_email_thread_backfill.py`

**Interfaces:**
- Produces: `conversation_has_equivalent(conversation_id: int, sender_type: str, content: str, sent_at: datetime, window_minutes: int) -> bool` — True if the conversation already has a same-direction message with equivalent normalized content within ±window. Reuses `email_reconcile._normalize_content` if present; otherwise normalizes inline.

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime, timedelta
from ChatBotAI.models import Guest, Conversation, Message


def _conv_with_message(content, sender_type, sent_at):
    g = Guest(name='Daniela')
    db.session.add(g); db.session.commit()
    c = Conversation(guest_id=g.id, platform='smoobu', platform_id=f'smoobu-{g.id}',
                     subject='x', last_message_at=sent_at)
    db.session.add(c); db.session.commit()
    m = Message(conversation_id=c.id, sender_type=sender_type, content=content, sent_at=sent_at)
    db.session.add(m); db.session.commit()
    return c


def test_conversation_has_equivalent(app):
    from ChatBotAI.services.email_thread_backfill import conversation_has_equivalent
    base = datetime(2026, 5, 7, 8, 30)
    c = _conv_with_message('Hallo, eine Frage zur Wohnung', 'guest', base)
    # same direction, equivalent content, within window -> True
    assert conversation_has_equivalent(c.id, 'guest', 'hallo,  eine frage zur wohnung', base + timedelta(minutes=3), 10) is True
    # different direction -> False
    assert conversation_has_equivalent(c.id, 'owner', 'Hallo, eine Frage zur Wohnung', base, 10) is False
    # outside window -> False
    assert conversation_has_equivalent(c.id, 'guest', 'Hallo, eine Frage zur Wohnung', base + timedelta(minutes=30), 10) is False
    # different content -> False
    assert conversation_has_equivalent(c.id, 'guest', 'Etwas ganz anderes', base, 10) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_email_thread_backfill.py -k equivalent -q`
Expected: FAIL — `ImportError: cannot import name 'conversation_has_equivalent'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to services/email_thread_backfill.py
from datetime import timedelta
from ..models import Message


def _normalize(text: str) -> str:
    return ' '.join((text or '').split()).strip().lower()


def conversation_has_equivalent(conversation_id: int, sender_type: str,
                                content: str, sent_at, window_minutes: int) -> bool:
    if sent_at is None:
        return False
    lo = sent_at - timedelta(minutes=window_minutes)
    hi = sent_at + timedelta(minutes=window_minutes)
    target = _normalize(content)
    rows = Message.query.filter(
        Message.conversation_id == conversation_id,
        Message.sender_type == sender_type,
        Message.sent_at >= lo,
        Message.sent_at <= hi,
    ).all()
    return any(_normalize(r.content) == target for r in rows)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest ChatBotAI/tests/test_email_thread_backfill.py -k equivalent -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/email_thread_backfill.py ChatBotAI/tests/test_email_thread_backfill.py
git commit -m "feat(email-backfill): cross-source dedup helper (direction + time window)"
```

---

### Task 5: Thread discovery (Tier 1) with host-participation filter

**Files:**
- Modify: `services/email_thread_backfill.py`
- Test: `tests/test_email_thread_backfill.py`

**Interfaces:**
- Consumes: `get_host_addresses()`, `GmailService.get_recent_emails(max_results, query, apply_filter)`, `GmailService.get_thread(thread_id) -> list[dict]`.
- Produces:
  - `thread_has_host(messages: list, host_addresses: set) -> bool`
  - `find_guest_thread_messages(gmail, guest_email: str, lookback_days: int) -> list[dict]` — returns flattened, de-duplicated (by `id`) email dicts across all threads where `guest_email` appears AND a host address participates. Search query: `from:<addr> OR to:<addr> newer_than:<N>d`, `apply_filter=False`.

- [ ] **Step 1: Write the failing test**

```python
class _FakeGmail:
    """Stubs the two GmailService methods this feature calls."""
    def __init__(self, search_results, threads):
        self._search = search_results          # {query_substr: [email,...]}
        self._threads = threads                # {thread_id: [email,...]}
    def get_recent_emails(self, max_results=10, query=None, apply_filter=True):
        for key, val in self._search.items():
            if key in (query or ''):
                return val
        return []
    def get_thread(self, thread_id):
        return self._threads.get(thread_id, [])


def test_thread_has_host(app):
    from ChatBotAI.services.email_thread_backfill import thread_has_host, get_host_addresses
    hosts = get_host_addresses()
    msgs = [{'sender_email': 'dbrachholz@gmail.com'},
            {'sender_email': 'buchungsanfrage.urlaubsmagie@gmail.com'}]
    assert thread_has_host(msgs, hosts) is True
    assert thread_has_host([{'sender_email': 'dbrachholz@gmail.com'}], hosts) is False


def test_find_guest_thread_messages_tier1(app):
    from ChatBotAI.services.email_thread_backfill import find_guest_thread_messages
    guest = 'dbrachholz@gmail.com'
    thread = [
        {'id': 'g1', 'thread_id': 't1', 'sender_email': guest, 'subject': 'Frage', 'body': 'Hallo'},
        {'id': 'g2', 'thread_id': 't1', 'sender_email': 'buchungsanfrage.urlaubsmagie@gmail.com',
         'subject': 'Re: Frage', 'body': 'Hallo Daniela'},
    ]
    # a second thread with NO host participation must be dropped
    foreign = [{'id': 'x1', 'thread_id': 't2', 'sender_email': guest, 'subject': 'Spam', 'body': 'hi'}]
    gmail = _FakeGmail(
        search_results={guest: [{'id': 'g1', 'thread_id': 't1'}, {'id': 'x1', 'thread_id': 't2'}]},
        threads={'t1': thread, 't2': foreign},
    )
    out = find_guest_thread_messages(gmail, guest, lookback_days=180)
    ids = sorted(m['id'] for m in out)
    assert ids == ['g1', 'g2']  # t2 dropped (no host), no duplicates
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_email_thread_backfill.py -k "host or tier1" -q`
Expected: FAIL — `ImportError: cannot import name 'thread_has_host'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to services/email_thread_backfill.py

def thread_has_host(messages: list, host_addresses: set) -> bool:
    return any((m.get('sender_email') or '').strip().lower() in host_addresses for m in messages)


def find_guest_thread_messages(gmail, guest_email: str, lookback_days: int) -> list:
    """Tier 1: all messages from guest↔us threads anchored on guest_email."""
    host_addresses = get_host_addresses()
    addr = guest_email.strip()
    query = f'(from:{addr} OR to:{addr}) newer_than:{lookback_days}d'
    hits = gmail.get_recent_emails(max_results=50, query=query, apply_filter=False)
    thread_ids = []
    seen_threads = set()
    for h in hits:
        tid = h.get('thread_id')
        if tid and tid not in seen_threads:
            seen_threads.add(tid)
            thread_ids.append(tid)
    out, seen_msgs = [], set()
    for tid in thread_ids:
        messages = gmail.get_thread(tid)
        if not thread_has_host(messages, host_addresses):
            continue
        for m in messages:
            mid = m.get('id')
            if mid and mid not in seen_msgs:
                seen_msgs.add(mid)
                out.append(m)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest ChatBotAI/tests/test_email_thread_backfill.py -k "host or tier1" -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/email_thread_backfill.py ChatBotAI/tests/test_email_thread_backfill.py
git commit -m "feat(email-backfill): tier-1 thread discovery with host-participation filter"
```

---

### Task 6: Orchestrator — insert both directions into a conversation

**Files:**
- Modify: `services/email_thread_backfill.py`
- Test: `tests/test_email_thread_backfill.py`

**Interfaces:**
- Consumes: everything above; `GmailService._clean_email_body`, `MessageRouter._store_message`, `get_message_router()`.
- Produces:
  - `backfill_conversation_from_email(gmail, conversation_id: int, allow_name_fallback: bool = False, confirm_thread_id: Optional[str] = None) -> dict`
    Returns `{'inserted': int, 'skipped_dupes': int, 'skipped_unauth': int, 'candidates': list[dict], 'matched': bool}`.
    - Tier 1 (guest email usable): insert both directions, auto.
    - Tier 2 (no usable email): if `confirm_thread_id` given → insert that thread; else if `allow_name_fallback` → return `candidates` (thread summaries), insert nothing.

Candidate summary dict: `{'thread_id': str, 'subject': str, 'message_count': int, 'date_range': str, 'participant': str}`.

- [ ] **Step 1: Write the failing test**

```python
from ChatBotAI.services.gmail_service import GmailService  # for monkeypatching _clean_email_body if needed


def test_backfill_inserts_both_directions_tier1(app, monkeypatch):
    from ChatBotAI.services import email_thread_backfill as etb
    guest_addr = 'dbrachholz@gmail.com'
    g = Guest(name='Daniela Brachholz', email=guest_addr)
    db.session.add(g); db.session.commit()
    conv = Conversation(guest_id=g.id, platform='smoobu', platform_id=f'smoobu-{g.id}',
                        subject='Reservation 1', last_message_at=datetime(2026, 1, 1))
    db.session.add(conv); db.session.commit()

    thread = [
        {'id': 'g1', 'thread_id': 't1', 'sender_email': guest_addr, 'subject': 'Frage',
         'date': 'Thu, 7 May 2026 08:30:00 +0000', 'body': 'Hallo, eine Frage',
         'authentication_results': ['dmarc=pass dkim=pass']},
        {'id': 'g2', 'thread_id': 't1', 'sender_email': 'buchungsanfrage.urlaubsmagie@gmail.com',
         'subject': 'Re: Frage', 'date': 'Thu, 7 May 2026 08:42:00 +0000',
         'body': 'Hallo Daniela, ja klar', 'authentication_results': []},
    ]
    gmail = _FakeGmail(search_results={guest_addr: [{'id': 'g1', 'thread_id': 't1'}]},
                       threads={'t1': thread})

    res = etb.backfill_conversation_from_email(gmail, conv.id)
    assert res['matched'] is True
    assert res['inserted'] == 2
    msgs = Message.query.filter_by(conversation_id=conv.id).order_by(Message.sent_at).all()
    assert [m.sender_type for m in msgs] == ['guest', 'owner']
    assert msgs[0].platform_message_id == 'email:g1'
    assert msgs[1].platform_message_id == 'email:g2'
    assert all(m.sent_via_app is False for m in msgs)
    # idempotent: second run inserts nothing
    res2 = etb.backfill_conversation_from_email(gmail, conv.id)
    assert res2['inserted'] == 0
    assert res2['skipped_dupes'] == 2


def test_backfill_rejects_unauthenticated_guest(app):
    from ChatBotAI.services import email_thread_backfill as etb
    g = Guest(name='Spoof', email='spoof@evil.com'); db.session.add(g); db.session.commit()
    conv = Conversation(guest_id=g.id, platform='smoobu', platform_id=f'smoobu-{g.id}',
                        subject='x', last_message_at=datetime(2026, 1, 1))
    db.session.add(conv); db.session.commit()
    thread = [
        {'id': 's1', 'thread_id': 't9', 'sender_email': 'spoof@evil.com', 'subject': 'hi',
         'date': 'Thu, 7 May 2026 08:30:00 +0000', 'body': 'malicious',
         'authentication_results': ['dmarc=fail']},
        {'id': 's2', 'thread_id': 't9', 'sender_email': 'urlaubsmagie@gmail.com', 'subject': 'Re',
         'date': 'Thu, 7 May 2026 09:00:00 +0000', 'body': 'ok', 'authentication_results': []},
    ]
    gmail = _FakeGmail(search_results={'spoof@evil.com': [{'id': 's1', 'thread_id': 't9'}]},
                       threads={'t9': thread})
    res = etb.backfill_conversation_from_email(gmail, conv.id)
    assert res['inserted'] == 1            # owner message inserted (trusted)
    assert res['skipped_unauth'] == 1      # guest spoof rejected
    types = [m.sender_type for m in Message.query.filter_by(conversation_id=conv.id)]
    assert types == ['owner']


def test_backfill_no_usable_email_returns_candidates(app):
    from ChatBotAI.services import email_thread_backfill as etb
    g = Guest(name='Raymond', email=None); db.session.add(g); db.session.commit()
    conv = Conversation(guest_id=g.id, platform='smoobu', platform_id=f'smoobu-{g.id}',
                        subject='Reservation 5', check_in=datetime(2026, 5, 29).date(),
                        check_out=datetime(2026, 5, 31).date(), last_message_at=datetime(2026, 1, 1))
    db.session.add(conv); db.session.commit()
    thread = [{'id': 'n1', 'thread_id': 'tn', 'sender_email': 'raymond@gmail.com', 'subject': 'Parking',
               'date': 'Fri, 29 May 2026 10:00:00 +0000', 'body': 'parking?',
               'authentication_results': ['dmarc=pass']},
              {'id': 'n2', 'thread_id': 'tn', 'sender_email': 'urlaubsmagie@gmail.com', 'subject': 'Re',
               'date': 'Fri, 29 May 2026 11:00:00 +0000', 'body': 'yes', 'authentication_results': []}]
    gmail = _FakeGmail(search_results={'Raymond': [{'id': 'n1', 'thread_id': 'tn'}]},
                       threads={'tn': thread})
    res = etb.backfill_conversation_from_email(gmail, conv.id, allow_name_fallback=True)
    assert res['inserted'] == 0
    assert len(res['candidates']) == 1
    assert res['candidates'][0]['thread_id'] == 'tn'
    assert res['candidates'][0]['message_count'] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_email_thread_backfill.py -k backfill -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'backfill_conversation_from_email'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to services/email_thread_backfill.py
from email.utils import parsedate_to_datetime

from ..models import db, Conversation, Guest
from .gmail_service import GmailService
from .message_router import get_message_router


def _email_dt(email: dict):
    raw = email.get('date')
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt is not None and dt.tzinfo is not None:
            dt = dt.astimezone(tz=None).replace(tzinfo=None)
        return dt
    except (TypeError, ValueError):
        return None


def _insert_messages(conversation_id: int, emails: list, host_addresses: set,
                     window_minutes: int) -> dict:
    router = get_message_router()
    inserted = skipped_dupes = skipped_unauth = 0
    newest = None
    for em in emails:
        body = GmailService._clean_email_body(em.get('body') or '')
        if not is_backfillable(em, body):
            continue
        direction = classify_direction(em, host_addresses)
        if direction == 'guest' and not guest_message_is_authentic(em):
            skipped_unauth += 1
            continue
        sent_at = _email_dt(em)
        if conversation_has_equivalent(conversation_id, direction, body, sent_at, window_minutes):
            skipped_dupes += 1
            continue
        gmail_id = em.get('id')
        msg, is_new = router._store_message(
            conversation_id=conversation_id, sender_type=direction, content=body,
            platform_message_id=f"email:{gmail_id}", sent_at=sent_at, sent_via_app=False,
        )
        if is_new:
            msg.is_processed = True
            inserted += 1
            if sent_at and (newest is None or sent_at > newest):
                newest = sent_at
        else:
            skipped_dupes += 1
    if inserted:
        conv = Conversation.query.get(conversation_id)
        from datetime import datetime as _dt
        if newest and (not conv.last_message_at or newest > conv.last_message_at):
            conv.last_message_at = newest
        conv.updated_at = _dt.utcnow()
        db.session.commit()
    return {'inserted': inserted, 'skipped_dupes': skipped_dupes, 'skipped_unauth': skipped_unauth}


def _candidate_summary(thread_id: str, messages: list) -> dict:
    dates = [d for d in (_email_dt(m) for m in messages) if d]
    drange = ''
    if dates:
        drange = f"{min(dates):%Y-%m-%d} … {max(dates):%Y-%m-%d}"
    participant = next((m.get('sender_email') for m in messages
                        if m.get('sender_email')), '')
    subject = next((m.get('subject') for m in messages if m.get('subject')), '')
    return {'thread_id': thread_id, 'subject': subject, 'message_count': len(messages),
            'date_range': drange, 'participant': participant}


def backfill_conversation_from_email(gmail, conversation_id: int,
                                     allow_name_fallback: bool = False,
                                     confirm_thread_id: Optional[str] = None) -> dict:
    host_addresses = get_host_addresses()
    cfg = get_thread_backfill_config()
    conv = Conversation.query.get(conversation_id)
    if not conv:
        return {'matched': False, 'inserted': 0, 'skipped_dupes': 0,
                'skipped_unauth': 0, 'candidates': []}
    guest = Guest.query.get(conv.guest_id)
    base = {'inserted': 0, 'skipped_dupes': 0, 'skipped_unauth': 0, 'candidates': []}

    # Tier 2 confirm: caller picked a specific thread from a name-fallback search.
    if confirm_thread_id:
        messages = gmail.get_thread(confirm_thread_id)
        if not thread_has_host(messages, host_addresses):
            return {**base, 'matched': False}
        stats = _insert_messages(conversation_id, messages, host_addresses, cfg['window_minutes'])
        return {**base, **stats, 'matched': True}

    # Tier 1: usable guest email anchors a high-trust search.
    if guest and guest_email_is_usable(guest.email):
        emails = find_guest_thread_messages(gmail, guest.email, cfg['lookback_days'])
        if not emails:
            return {**base, 'matched': False}
        stats = _insert_messages(conversation_id, emails, host_addresses, cfg['window_minutes'])
        return {**base, **stats, 'matched': True}

    # Tier 2 discovery: no usable email — name search, return candidates only.
    if allow_name_fallback and guest and guest.name:
        hits = gmail.get_recent_emails(
            max_results=50, query=f'"{guest.name}" newer_than:{cfg["lookback_days"]}d',
            apply_filter=False)
        seen, candidates = set(), []
        for h in hits:
            tid = h.get('thread_id')
            if not tid or tid in seen:
                continue
            seen.add(tid)
            messages = gmail.get_thread(tid)
            if thread_has_host(messages, host_addresses):
                candidates.append(_candidate_summary(tid, messages))
        return {**base, 'matched': bool(candidates), 'candidates': candidates}

    return {**base, 'matched': False}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest ChatBotAI/tests/test_email_thread_backfill.py -q`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/email_thread_backfill.py ChatBotAI/tests/test_email_thread_backfill.py
git commit -m "feat(email-backfill): orchestrator inserts both directions (tier1 auto, tier2 candidates)"
```

---

### Task 7: Per-chat endpoint

**Files:**
- Modify: `routes.py` (add route near the existing `conversation_recover_emails`, ~line 4745)
- Test: `tests/test_email_thread_backfill.py`

**Interfaces:**
- Consumes: `backfill_conversation_from_email`, `get_gmail_service`.
- Produces: `POST /chatbot/api/conversation/<int:conversation_id>/import-email-thread`
  Body (optional): `{'allow_name_fallback': bool, 'confirm_thread_id': str}`.
  Returns: `{'success': True, 'inserted': int, 'skipped_dupes': int, 'skipped_unauth': int, 'candidates': [...]}` or `{'success': False, 'error': str}` (503 if Gmail not authenticated).

- [ ] **Step 1: Write the failing test**

```python
def test_import_email_thread_endpoint(app, client, monkeypatch):
    from ChatBotAI.services import email_thread_backfill as etb
    g = Guest(name='Daniela', email='dbrachholz@gmail.com'); db.session.add(g); db.session.commit()
    conv = Conversation(guest_id=g.id, platform='smoobu', platform_id=f'smoobu-{g.id}',
                        subject='x', last_message_at=datetime(2026, 1, 1))
    db.session.add(conv); db.session.commit()

    # stub gmail factory + the backfill to avoid real network.
    # NOTE: the route does `from .services.gmail_service import get_gmail_service`
    # at call time, so patch it at its SOURCE module (not ChatBotAI.routes).
    class _Auth:
        def is_authenticated(self): return True
    monkeypatch.setattr('ChatBotAI.services.gmail_service.get_gmail_service', lambda: _Auth())
    monkeypatch.setattr(etb, 'backfill_conversation_from_email',
                        lambda gmail, cid, **kw: {'matched': True, 'inserted': 2,
                                                  'skipped_dupes': 0, 'skipped_unauth': 0, 'candidates': []})
    resp = client.post(f'/chatbot/api/conversation/{conv.id}/import-email-thread')
    assert resp.status_code == 200
    assert resp.get_json() == {'success': True, 'inserted': 2, 'skipped_dupes': 0,
                               'skipped_unauth': 0, 'candidates': []}
```

Add this admin-session `client` fixture to the test file (top, after the `app` fixture):

```python
@pytest.fixture
def client(app):
    from ChatBotAI.models import User
    user = User(username='tester', display_name='Tester', is_admin=True)
    user.set_password('pw')
    db.session.add(user); db.session.commit()
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True
    return c
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_email_thread_backfill.py -k import_email_thread -q`
Expected: FAIL — 404 (route not registered)

- [ ] **Step 3: Write minimal implementation**

```python
# routes.py — add after conversation_recover_emails (~line 4745)
@chatbot_bp.route('/api/conversation/<int:conversation_id>/import-email-thread', methods=['POST'])
@login_required
def conversation_import_email_thread(conversation_id: int):
    """Backfill an existing conversation from the guest's two-sided Gmail thread."""
    from .services.email_thread_backfill import backfill_conversation_from_email
    from .services.gmail_service import get_gmail_service
    Conversation.query.get_or_404(conversation_id)
    gmail = get_gmail_service()
    if not gmail or not gmail.is_authenticated():
        return jsonify({'success': False, 'error': 'Gmail not connected'}), 503
    payload = request.get_json(silent=True) or {}
    res = backfill_conversation_from_email(
        gmail, conversation_id,
        allow_name_fallback=bool(payload.get('allow_name_fallback')),
        confirm_thread_id=payload.get('confirm_thread_id'),
    )
    return jsonify({'success': True, 'inserted': res['inserted'],
                    'skipped_dupes': res['skipped_dupes'],
                    'skipped_unauth': res['skipped_unauth'],
                    'candidates': res['candidates']})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest ChatBotAI/tests/test_email_thread_backfill.py -k import_email_thread -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/routes.py ChatBotAI/tests/test_email_thread_backfill.py
git commit -m "feat(email-backfill): per-chat import-email-thread endpoint"
```

---

### Task 8: Opt-in background pass

**Files:**
- Modify: `services/email_thread_backfill.py` (add `run_thread_backfill_pass`)
- Modify: `app.py` (call it inside `_start_background_sync`, after the existing email-reconcile block, ~line 388)
- Test: `tests/test_email_thread_backfill.py`

**Interfaces:**
- Produces: `run_thread_backfill_pass(gmail, max_conversations: int = 200) -> dict` — iterates conversations whose guest has a usable email, runs Tier-1 backfill on each; returns `{'conversations': int, 'inserted': int}`. Only runs Tier 1 (no name fallback).

- [ ] **Step 1: Write the failing test**

```python
def test_run_thread_backfill_pass_tier1_only(app, monkeypatch):
    from ChatBotAI.services import email_thread_backfill as etb
    g1 = Guest(name='A', email='a@gmail.com')          # usable -> processed
    g2 = Guest(name='B', email='x@guest.booking.com')  # relay alias -> skipped
    g3 = Guest(name='C', email=None)                   # no email -> skipped
    db.session.add_all([g1, g2, g3]); db.session.commit()
    for i, g in enumerate((g1, g2, g3)):
        db.session.add(Conversation(guest_id=g.id, platform='smoobu',
                                    platform_id=f'smoobu-{i}', subject='x',
                                    last_message_at=datetime(2026, 1, 1)))
    db.session.commit()

    calls = []
    def fake_backfill(gmail, cid, **kw):
        calls.append((cid, kw))
        return {'matched': True, 'inserted': 1, 'skipped_dupes': 0, 'skipped_unauth': 0, 'candidates': []}
    monkeypatch.setattr(etb, 'backfill_conversation_from_email', fake_backfill)

    stats = etb.run_thread_backfill_pass(gmail=object())
    assert stats['conversations'] == 1   # only g1's conversation
    assert stats['inserted'] == 1
    assert all(kw.get('allow_name_fallback') is False for _, kw in calls)  # never name-fallback
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_email_thread_backfill.py -k backfill_pass -q`
Expected: FAIL — `AttributeError: ... has no attribute 'run_thread_backfill_pass'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to services/email_thread_backfill.py

def run_thread_backfill_pass(gmail, max_conversations: int = 200) -> dict:
    """Background Tier-1 backfill over conversations with a usable guest email."""
    conversations = inserted = 0
    convs = (Conversation.query
             .join(Guest, Conversation.guest_id == Guest.id)
             .filter(Guest.email.isnot(None))
             .order_by(Conversation.updated_at.desc())
             .limit(max_conversations)
             .all())
    for conv in convs:
        guest = Guest.query.get(conv.guest_id)
        if not guest or not guest_email_is_usable(guest.email):
            continue
        try:
            res = backfill_conversation_from_email(gmail, conv.id, allow_name_fallback=False)
        except Exception:
            logger.exception("thread backfill failed for conv %s", conv.id)
            continue
        if res.get('inserted'):
            conversations += 1
            inserted += res['inserted']
    return {'conversations': conversations, 'inserted': inserted}
```

```python
# app.py — inside _start_background_sync, AFTER the existing email-reconcile block (~line 388)
        # Two-sided Gmail thread backfill (opt-in; fills owner+guest gaps Smoobu missed)
        try:
            from .services.email_thread_backfill import run_thread_backfill_pass, get_thread_backfill_config
            if get_thread_backfill_config()['auto_enabled']:
                from .services.gmail_service import get_gmail_service
                gmail = get_gmail_service()
                if gmail and gmail.is_authenticated():
                    tstats = run_thread_backfill_pass(gmail)
                    if tstats['inserted']:
                        logger.info("Thread backfill: inserted %d across %d conversations",
                                    tstats['inserted'], tstats['conversations'])
        except Exception:
            logger.exception("Thread backfill pass error")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest ChatBotAI/tests/test_email_thread_backfill.py -q`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/email_thread_backfill.py ChatBotAI/app.py ChatBotAI/tests/test_email_thread_backfill.py
git commit -m "feat(email-backfill): opt-in background thread-backfill pass"
```

---

### Task 9: UI button on the conversation page

**Files:**
- Modify: `templates/chatbot/conversation.html` (add button beside the existing "find emails" recover button)
- Modify: `static/js/conversation.js` (handler + Tier-2 confirm list)
- Modify: `templates/chatbot/base.html` (bump `conversation.js?v=` cache version — current is v26 per project notes; set to next integer)

**Interfaces:**
- Consumes: `POST /api/conversation/<id>/import-email-thread`.

- [ ] **Step 1: Locate the existing recover-emails button markup**

Run: `rg -n "recover-emails|find emails|recoverEmails" ChatBotAI/templates/chatbot/conversation.html ChatBotAI/static/js/conversation.js`
Expected: shows the existing button + its JS handler to mirror.

- [ ] **Step 2: Add the button (mirror existing recover button)**

In `conversation.html`, next to the recover-emails button, add:

```html
<button id="import-email-thread-btn" class="btn-secondary" title="E-Mail-Verlauf (Gast + wir) in diesen Chat übernehmen">
  E-Mail-Verlauf holen
</button>
<div id="email-thread-candidates" class="email-thread-candidates" hidden></div>
```

- [ ] **Step 3: Add the JS handler**

In `conversation.js` (mirror the existing recover handler; `CONVERSATION_ID` is already defined there):

```javascript
const importBtn = document.getElementById('import-email-thread-btn');
if (importBtn) {
  importBtn.addEventListener('click', async () => {
    importBtn.disabled = true;
    try {
      const r = await fetch(`/chatbot/api/conversation/${CONVERSATION_ID}/import-email-thread`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ allow_name_fallback: true }),
      });
      const data = await r.json();
      if (!data.success) { alert(data.error || 'Fehler'); return; }
      if (data.inserted > 0) { location.reload(); return; }
      const box = document.getElementById('email-thread-candidates');
      if (data.candidates && data.candidates.length) {
        box.hidden = false;
        box.innerHTML = data.candidates.map(c =>
          `<div class="cand"><span>${c.participant} — ${c.message_count} Nachrichten (${c.date_range})</span>
           <button data-tid="${c.thread_id}">Übernehmen</button></div>`).join('');
        box.querySelectorAll('button[data-tid]').forEach(b =>
          b.addEventListener('click', async () => {
            const rr = await fetch(`/chatbot/api/conversation/${CONVERSATION_ID}/import-email-thread`, {
              method: 'POST', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ confirm_thread_id: b.dataset.tid }),
            });
            if ((await rr.json()).inserted >= 0) location.reload();
          }));
      } else {
        alert('Keine passenden E-Mails gefunden.');
      }
    } finally { importBtn.disabled = false; }
  });
}
```

- [ ] **Step 4: Bump cache version**

In `base.html`, find `conversation.js?v=26` and change to `conversation.js?v=27`.
Run: `rg -n "conversation.js\?v=" ChatBotAI/templates/chatbot/base.html`
Expected: shows the bumped version.

- [ ] **Step 5: Manual smoke check + commit**

Start the dev server, open a conversation whose guest has a real email, click **E-Mail-Verlauf holen**, confirm messages appear (or a candidate list shows for a no-email guest).

```bash
git add ChatBotAI/templates/chatbot/conversation.html ChatBotAI/static/js/conversation.js ChatBotAI/templates/chatbot/base.html
git commit -m "feat(email-backfill): conversation-page button + tier-2 confirm list"
```

---

## Final verification

- [ ] Run the whole feature suite: `python -m pytest ChatBotAI/tests/test_email_thread_backfill.py -q` → all pass.
- [ ] Run the full suite to check no regressions: `python -m pytest ChatBotAI/tests/ -q`.
- [ ] Confirm the host-address list with the user; if an `info@` address is used, set `AISettings.set('email_host_addresses', '<comma list>')`.
- [ ] Leave `email_thread_backfill_auto` **off**; enable only after the button is trusted.

## Notes / deviations from the design doc

- **`platform_message_id` convention:** the design doc said `gmail-<id>`; this plan uses **`email:<gmail_id>`** to match the existing `email_reconcile`/`email_review` convention, which also yields cross-feature dedup. (Design doc should be considered superseded on this detail.)
- **Anti-spoof:** uses a *generic* DKIM/DMARC-pass check (`guest_message_is_authentic`) rather than the domain-aligned `verify_sender_authenticity`, because direct-guest domains vary and aren't booking/airbnb relay domains.
