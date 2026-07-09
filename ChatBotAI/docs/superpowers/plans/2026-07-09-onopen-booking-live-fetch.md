# On-open Live Booking Email Fetch — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make email reconciliation Booking-only, and add an auto/throttled/async per-conversation live Gmail fetch that pulls a chat's Booking messages in when the chat is opened, auto-inserting every positive match.

**Architecture:** Refactor the per-email pipeline inside `reconcile_from_email` into a shared helper, then reuse it from a new `fetch_booking_for_conversation` that searches Gmail scoped to one guest (`from:guest.booking.com "<name>"`), scores against that single conversation, and auto-inserts any match (`score > 0`). A new POST route triggers it; `conversation.js` calls that route on page load and refreshes the thread if anything was inserted. The background scan is narrowed to Booking only.

**Tech Stack:** Flask blueprint (`ChatBotAI`), SQLAlchemy models, pytest, vanilla JS (`conversation.js`), Gmail API via `GmailService`.

## Global Constraints

- **Booking-only:** the background scan and the live fetch operate on Booking (`@guest.booking.com`) only. Airbnb is dropped from the scan loop (parsing functions stay in the module, unused by the scan).
- **Security gates are mandatory, never simplified away:** `verify_sender_authenticity` (DKIM/DMARC anti-spoof) and dedup (`has_equivalent_message` + global `email:{gmail_id}` guard) run on every email in both paths.
- **"Match" for the live path = `score_conversation_match(...) > 0`.** A same-name / wrong-apartment email scores `0.0` and is NOT inserted or queued.
- **Live path never queues:** it auto-inserts matches or skips; it never writes `EmailBackfillCandidate` rows.
- **No new dependencies. No DB migration.** New settings are `AISettings` key-value rows read with defaults.
- **Failures never block the chat:** the route and the client call must swallow errors.
- All new `AISettings` keys and defaults, verbatim: `email_onopen_live_enabled` = `'true'`; `email_onopen_live_throttle_minutes` = `'15'`.

---

### Task 1: Narrow the background scan to Booking-only

**Files:**
- Modify: `ChatBotAI/services/email_reconcile.py:619-622` (`_PLATFORM_SENDER`)
- Test: `ChatBotAI/tests/test_email_reconcile.py` (add one test; update one existing test)

**Interfaces:**
- Consumes: existing `platform_queries(days)`, `reconcile_from_email(gmail_service)`.
- Produces: `_PLATFORM_SENDER` containing only the `booking` key.

- [ ] **Step 1: Write the failing test**

Append to `ChatBotAI/tests/test_email_reconcile.py`:

```python
from ChatBotAI.services.email_reconcile import platform_queries


def test_platform_queries_is_booking_only():
    q = platform_queries(30)
    assert set(q.keys()) == {'booking'}
    assert q['booking'] == 'from:guest.booking.com newer_than:30d'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py::test_platform_queries_is_booking_only -v`
Expected: FAIL — keys are `{'booking', 'airbnb'}`.

- [ ] **Step 3: Make the change**

In `ChatBotAI/services/email_reconcile.py`, replace the `_PLATFORM_SENDER` dict (lines 619-622):

```python
# Gmail search — relay-domain funnel. Booking only: Smoobu lacks the Booking
# messaging scope, so Booking guest messages arrive solely as @guest.booking.com
# notification emails. Airbnb messaging works via Smoobu, so it is not scanned.
_PLATFORM_SENDER = {
    'booking': 'from:guest.booking.com',
}
```

- [ ] **Step 4: Update the now-obsolete Airbnb orchestrator test**

In `ChatBotAI/tests/test_email_reconcile.py`, replace the body of `test_orchestrator_queues_low_confidence_airbnb` (around lines 534-552) so it asserts Airbnb is no longer scanned:

```python
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
```

- [ ] **Step 5: Run the reconcile tests and verify they pass**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py -v`
Expected: PASS (including the new `test_platform_queries_is_booking_only` and the updated Airbnb test).

- [ ] **Step 6: Commit**

```bash
git add ChatBotAI/services/email_reconcile.py ChatBotAI/tests/test_email_reconcile.py
git commit -m "feat(email): scan Booking notifications only, drop Airbnb from reconcile"
```

---

### Task 2: Extract the shared per-email handler (behavior-preserving refactor)

**Files:**
- Modify: `ChatBotAI/services/email_reconcile.py:652-745` (`reconcile_from_email`)
- Test: guarded by the existing `ChatBotAI/tests/test_email_reconcile.py` orchestrator tests (no new test).

**Interfaces:**
- Produces:
  - `_new_stats() -> dict` — the stats dict both callers use.
  - `_handle_notification_email(email, platform, views, cfg, router, stats, auto_insert_all)` — runs parse → anti-spoof → dedup → match → insert/queue for one email, mutating `stats`. When `auto_insert_all` is True it inserts any `score > 0` match and NEVER queues; when False it uses the scan's threshold/autoinsert behaviour.
- Consumes: existing `parse_notification`, `verify_sender_authenticity`, `pick_best_match`, `has_equivalent_message`, `get_reconcile_config`.

- [ ] **Step 1: Add the two helpers above `reconcile_from_email`**

Insert immediately before `def reconcile_from_email` (line 652) in `ChatBotAI/services/email_reconcile.py`:

```python
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
```

- [ ] **Step 2: Rewrite `reconcile_from_email` to use the helpers**

Replace the whole body of `reconcile_from_email` (lines 652-745) with:

```python
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
```

- [ ] **Step 3: Run the full reconcile suite to prove behaviour is unchanged**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py ChatBotAI/tests/test_email_flush.py -v`
Expected: PASS — every existing orchestrator/dedup/flush test still green.

- [ ] **Step 4: Commit**

```bash
git add ChatBotAI/services/email_reconcile.py
git commit -m "refactor(email): extract shared per-email handler from reconcile_from_email"
```

---

### Task 3: `fetch_booking_for_conversation` + throttle + settings

**Files:**
- Modify: `ChatBotAI/services/email_reconcile.py` (`_candidate_views` refactor + new functions, near lines 629-649)
- Test: `ChatBotAI/tests/test_email_reconcile.py` (append new tests)

**Interfaces:**
- Consumes: `_handle_notification_email`, `_new_stats`, `get_reconcile_config`, `resolve_channel`, `_safe_query_term`, `code_from_smoobu_id`.
- Produces:
  - `_conv_view(conv, channel) -> dict` — one scorer-input dict for a conversation.
  - `fetch_booking_for_conversation(gmail_service, conversation_id, now=None) -> dict` — live Booking fetch for one chat; returns a stats dict whose `auto_inserted` counts inserted messages and whose optional `reason` explains an early no-op (`'disabled'`, `'not_booking'`, `'no_guest_name'`, `'throttled'`, `'gmail_error'`).
  - Module state `_last_live_fetch: dict[int, datetime]` (throttle memory).

- [ ] **Step 1: Refactor `_candidate_views` to use a per-conversation helper**

In `ChatBotAI/services/email_reconcile.py`, replace `_candidate_views` (lines 629-649) with:

```python
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
```

- [ ] **Step 2: Write the failing tests**

Append to `ChatBotAI/tests/test_email_reconcile.py`:

```python
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


def test_live_fetch_does_not_insert_zero_score(app, monkeypatch):
    # The live rule is "insert iff score > 0". A zero score (e.g. the
    # same-name/wrong-apartment soft-veto) must NOT insert and must NOT queue.
    # Force the score deterministically rather than depend on apartment-config.
    _er._last_live_fetch.clear()
    g = Guest(name='Carolin Janowski'); db.session.add(g); db.session.flush()
    conv = Conversation(guest_id=g.id, platform='booking',
                        check_in=_d(2026, 6, 12), check_out=_d(2026, 6, 14))
    db.session.add(conv); db.session.commit()

    email = _email(id='glive3', sender_email='5843975682-x@guest.booking.com',
                   date='Mon, 09 Jun 2026 13:24:00 +0200', body=BOOKING_BODY,
                   authentication_results=[BOOKING_AR_DIRECT])
    query = f'from:guest.booking.com "Carolin Janowski" newer_than:30d'
    gmail = FakeGmail({query: [email]})

    # _handle_notification_email looks up pick_best_match at module scope.
    monkeypatch.setattr(_er, 'pick_best_match', lambda notif, views: (views[0], 0.0))

    stats = fetch_booking_for_conversation(gmail, conv.id)
    assert stats['auto_inserted'] == 0
    assert stats['skipped_lowscore'] == 1
    assert EmailBackfillCandidate.query.filter_by(gmail_message_id='glive3').first() is None
    assert Message.query.filter_by(conversation_id=conv.id).count() == 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py -k live_fetch -v`
Expected: FAIL with `ImportError` / `AttributeError` — `fetch_booking_for_conversation` and `_last_live_fetch` don't exist yet.

- [ ] **Step 4: Implement the live fetch + throttle**

Insert into `ChatBotAI/services/email_reconcile.py`, immediately after `reconcile_from_email`:

```python
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
```

- [ ] **Step 5: Run the live-fetch tests and verify they pass**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py -k live_fetch -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Run the whole email suite to confirm no regressions**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py ChatBotAI/tests/test_email_flush.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add ChatBotAI/services/email_reconcile.py ChatBotAI/tests/test_email_reconcile.py
git commit -m "feat(email): live per-chat Booking fetch with in-memory throttle"
```

---

### Task 4: Route — `POST /api/conversation/<id>/fetch-booking-live`

**Files:**
- Modify: `ChatBotAI/routes.py` (add route next to `conversation_recover_emails`, ~line 4924)
- Test: `ChatBotAI/tests/test_email_reconcile.py` (append; reuses the existing `client` fixture)

**Interfaces:**
- Consumes: `fetch_booking_for_conversation`, `get_gmail_service`.
- Produces: JSON `{'success': True, 'inserted': N, 'reason': <str|None>}`; always HTTP 200, never raises to the client.

- [ ] **Step 1: Write the failing test**

Append to `ChatBotAI/tests/test_email_reconcile.py` (the `client` fixture is defined earlier in this file):

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py -k fetch_booking_live_route -v`
Expected: FAIL — route returns 404 (endpoint not registered).

- [ ] **Step 3: Add the route**

In `ChatBotAI/routes.py`, immediately after the `conversation_recover_emails` function (ends at line 4933), add:

```python
@chatbot_bp.route('/api/conversation/<int:conversation_id>/fetch-booking-live', methods=['POST'])
@login_required
def conversation_fetch_booking_live(conversation_id):
    """Live per-chat Booking email fetch, called on chat open. Booking-only,
    throttled server-side, auto-inserts positive matches. Never raises to the
    client — a failed fetch must not block the conversation view."""
    Conversation.query.get_or_404(conversation_id)
    from .services.gmail_service import get_gmail_service
    from .services.email_reconcile import fetch_booking_for_conversation
    gmail = get_gmail_service()
    if not gmail or not gmail.is_authenticated():
        return jsonify({'success': True, 'inserted': 0, 'reason': 'gmail_disconnected'})
    try:
        stats = fetch_booking_for_conversation(gmail, conversation_id)
    except Exception:
        current_app.logger.exception(
            "fetch-booking-live failed for conv %s", conversation_id)
        return jsonify({'success': True, 'inserted': 0, 'reason': 'error'})
    return jsonify({'success': True, 'inserted': stats.get('auto_inserted', 0),
                    'reason': stats.get('reason')})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py -k fetch_booking_live_route -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/routes.py ChatBotAI/tests/test_email_reconcile.py
git commit -m "feat(email): add POST fetch-booking-live route for on-open live fetch"
```

---

### Task 5: Client — fire live fetch on chat open

**Files:**
- Modify: `ChatBotAI/static/js/conversation.js` (add a `DOMContentLoaded` handler near the existing ones at lines 1323 / 1356; `conversationId` and `messagePoller` are already in scope)

**Interfaces:**
- Consumes: the `POST /chatbot/api/conversation/${conversationId}/fetch-booking-live` route (Task 4), the module-scope `messagePoller` (defined at line 1211) and `conversationId` (line 12).

- [ ] **Step 1: Add the on-open trigger**

In `ChatBotAI/static/js/conversation.js`, add after the existing `DOMContentLoaded` block that ends around line 1356:

```javascript
// On chat open: live-fetch this chat's Booking emails. The server is the source
// of truth for "is this a Booking chat?" (resolve_channel) and applies its own
// throttle, so we POST unconditionally — it short-circuits cheaply for non-Booking
// chats with no Gmail call. Runs async; never blocks the thread from rendering.
document.addEventListener('DOMContentLoaded', function() {
    fetch(`/chatbot/api/conversation/${conversationId}/fetch-booking-live`, {
        method: 'POST'
    })
        .then(r => (r.ok ? r.json() : null))
        .then(data => {
            if (data && data.inserted > 0) {
                // Pull the newly inserted messages in via the existing incremental
                // poller (fetches messages after maxKnownMessageId).
                messagePoller.stop();
                messagePoller.start();
            }
        })
        .catch(err => console.debug('booking live-fetch skipped:', err));
});
```

- [ ] **Step 2: Manual verification (no JS test harness in this repo)**

Start the app (`python app.py`), open a Booking conversation whose guest has a recent `@guest.booking.com` message in Gmail, and confirm in DevTools → Network:
- a `POST .../fetch-booking-live` fires on load and returns `{"success":true,"inserted":N}`,
- when `N > 0`, the new guest message(s) appear in the thread within a poll cycle,
- opening the same chat again immediately returns `inserted:0, reason:"throttled"`,
- opening a non-Booking (email/Smoobu) chat returns `reason:"not_booking"` with no Gmail latency.

Confirm the server log shows `live booking fetch conv <id>: {...}` for the Booking open only.

- [ ] **Step 3: Commit**

```bash
git add ChatBotAI/static/js/conversation.js
git commit -m "feat(email): trigger on-open live Booking fetch from conversation view"
```

---

## Self-Review

**Spec coverage:**
- Background scan → Booking-only → Task 1. ✅
- Live per-chat fetch, name-anchored, auto-insert `score>0`, never queues → Task 3 (`_handle_notification_email` `auto_insert_all` branch + `fetch_booking_for_conversation`). ✅
- Auto / throttled (15 min default) / async → throttle in Task 3, async trigger in Task 5. ✅
- Anti-spoof + dedup mandatory in both paths → preserved in the shared handler (Task 2). ✅
- Settings `email_onopen_live_enabled` / `email_onopen_live_throttle_minutes` with defaults → Task 3 (read via `AISettings.get` with defaults; no migration). ✅
- Endpoint mirroring `recover-emails`, never raises → Task 4. ✅
- Out-of-scope items (no Booking-ref storage, no Airbnb parser changes, no review-tray change) → respected. ✅
- Verification (scan Booking-only; live inserts; no-op non-Booking; no-op throttled; zero-score not inserted/queued) → Tasks 1 & 3 tests. ✅

**Placeholder scan:** none — every code step contains full code; every test has assertions.

**Type consistency:** `_handle_notification_email(email, platform, views, cfg, router, stats, auto_insert_all)`, `_conv_view(conv, channel)`, `_new_stats()`, `fetch_booking_for_conversation(gmail_service, conversation_id, now=None)`, and module state `_last_live_fetch` are used with matching names/arities across Tasks 2–4. Route returns `inserted` from `stats['auto_inserted']`; client reads `data.inserted`. Consistent.
