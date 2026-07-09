# Reservation-number Matching for On-open Booking Fetch — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the on-open live Booking fetch match emails to the open chat by exact Buchungsnummer (Booking reservation number) — with a name+dates fallback — and rescue mis-filed pending candidates into the correct chat.

**Architecture:** Replace the live path's fuzzy `score>0` rule (which the apartment soft-veto breaks) with a three-tier match: (1) Buchungsnummer from the stored guest note, (2) Smoobu `reference-id` on demand, (3) name+exact-dates. A dedicated live handler stops skipping already-queued emails; instead it inserts a matched email and flips its stale `EmailBackfillCandidate` to `confirmed`. Only `email_reconcile.py` and its tests change — the route and `conversation.js` already call `fetch_booking_for_conversation` and are untouched.

**Tech Stack:** Flask blueprint (ChatBotAI), SQLAlchemy, pytest. Reuses `parse_notification`, `verify_sender_authenticity`, `has_equivalent_message`, `_iso_date`, `get_smoobu_service`.

## Global Constraints

- **Match key is the Buchungsnummer, exact.** Tier 1: `re.search(r'Buchungsnummer:\s*(\d+)', guest_note)`. Tier 2: Smoobu `reference-id`. Tier 3 (only when no number on either side): guest name is already guaranteed by the name-scoped Gmail search, so require the email's `check_in` **and** `check_out` to equal the conversation's exactly.
- **Exact-match only — never fuzzy on the number.** A wrong/stale number must fall through to the next tier, never mis-insert.
- **Security/dedup guards stay:** `verify_sender_authenticity` (DKIM/DMARC) runs first; the global `Message.platform_message_id == "email:{id}"` guard and `has_equivalent_message` still prevent duplicates.
- **Rescue:** on insert, a `pending` `EmailBackfillCandidate` with the same `gmail_message_id` is set to `status='confirmed'` (never deleted).
- **Live path only.** The background scan (`reconcile_from_email`, `auto_insert_all=False` behavior) is unchanged in outcome.
- **No new dependencies. No DB migration.** Tier 1 reads an existing `GuestDetail` (`detail_key='guest_note'`); Tier 2 is an on-demand Smoobu API call via `get_smoobu_service()`.
- Smoobu/Gmail failures are non-fatal: log and fall through (Tier 2 → Tier 3; a failed live fetch returns its stats with a `reason`).

---

### Task 1: Extract `_authentic_new_notif` (behavior-preserving refactor)

**Files:**
- Modify: `ChatBotAI/services/email_reconcile.py:665-742` (`_handle_notification_email`)
- Test: guarded by existing `ChatBotAI/tests/test_email_reconcile.py` scan tests (no new test)

**Interfaces:**
- Produces: `_authentic_new_notif(email, platform, stats) -> notif | None` — shared front-half: `scanned++`, parse, anti-spoof, skip-if-already-inserted. Returns the parsed notif to act on, or `None` to skip. Mutates `stats`.
- Consumes: existing `parse_notification`, `verify_sender_authenticity`.

- [ ] **Step 1: Add the helper above `_handle_notification_email`**

Insert immediately before `def _handle_notification_email` (line 665) in `ChatBotAI/services/email_reconcile.py`:

```python
def _authentic_new_notif(email, platform, stats):
    """Shared front-half for both the scan and live paths: count, parse,
    anti-spoof, and skip anything already inserted. Returns the parsed
    ParsedNotification to act on, or None to skip. Mutates `stats`."""
    from ..models import Message
    stats['scanned'] += 1
    notif = parse_notification(email)
    if not notif or not notif.message_text or not notif.sent_at:
        return None
    authentic, auth_info = verify_sender_authenticity(email, platform)
    if not authentic:
        stats['rejected_unauthenticated'] += 1
        logger.warning("email-reconcile: dropped unauthenticated %s email %s (%s)",
                       platform, notif.gmail_id, auth_info)
        return None
    if Message.query.filter_by(platform_message_id=f"email:{notif.gmail_id}").first():
        return None
    return notif
```

- [ ] **Step 2: Rewrite `_handle_notification_email` to use it**

Replace the body of `_handle_notification_email` (lines 665-742) with:

```python
def _handle_notification_email(email, platform, views, cfg, router, stats):
    """Background-scan handler: threshold-gated auto-insert, else queue for review."""
    from ..models import EmailBackfillCandidate
    notif = _authentic_new_notif(email, platform, stats)
    if notif is None:
        return

    # Scan path skips emails already queued/rejected (a human decision).
    if EmailBackfillCandidate.query.filter_by(gmail_message_id=notif.gmail_id).first():
        return

    best, score = pick_best_match(notif, views)
    if not best:
        stats['unmatched'] += 1
        return
    stats['matched'] += 1

    if has_equivalent_message(best['conversation_id'], notif, cfg['window_minutes']):
        stats['skipped_dupe'] += 1
        return

    autoinsert = cfg['autoinsert_booking'] if platform == 'booking' else cfg['autoinsert_airbnb']
    if score >= cfg['threshold'] and autoinsert:
        router._store_message(
            conversation_id=best['conversation_id'], sender_type='guest',
            content=notif.message_text,
            platform_message_id=f"email:{notif.gmail_id}",
            sent_at=notif.sent_at, sent_via_app=False,
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
```

Note: the `auto_insert_all` parameter and its live branch are removed here (the live path gets its own handler in Task 3). `reconcile_from_email` is updated in the same step — change its call (line ~770) from `_handle_notification_email(email, platform, views, cfg, router, stats, auto_insert_all=False)` to `_handle_notification_email(email, platform, views, cfg, router, stats)`.

- [ ] **Step 3: Run the scan/flush suites to prove behaviour is unchanged**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py ChatBotAI/tests/test_email_flush.py -v`
Expected: PASS — except the obsolete live-fetch tests that call the removed live branch. Those are replaced in Task 3; if any `test_live_fetch_*` fails here due to the removed `auto_insert_all`, leave it for Task 3 (do not delete yet). All `test_orchestrator_*`, dedup, and flush tests MUST pass.

- [ ] **Step 4: Commit**

```bash
git add ChatBotAI/services/email_reconcile.py
git commit -m "refactor(email): extract _authentic_new_notif shared front-half"
```

---

### Task 2: Matching helpers (Buchungsnummer + tier decision)

**Files:**
- Modify: `ChatBotAI/services/email_reconcile.py` (add helpers near the live-fetch section, after `_conv_view`)
- Test: `ChatBotAI/tests/test_email_reconcile.py` (append unit tests)

**Interfaces:**
- Produces:
  - `booking_ref_from_note(guest_id) -> str | None` — Tier 1: extract Buchungsnummer from the guest's `guest_note` detail.
  - `conversation_booking_ref(conv, smoobu_service=None) -> str | None` — Tier 1, then Tier 2 (lazy Smoobu `reference-id`).
  - `email_matches_conversation(notif, conv, conv_ref) -> bool` — exact ref match, else exact check-in **and** check-out.
- Consumes: existing `_iso_date`, `get_smoobu_service`.

- [ ] **Step 1: Write the failing unit tests**

Append to `ChatBotAI/tests/test_email_reconcile.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py -k "booking_ref_from_note or email_matches or email_ref or email_no_match or email_checkin" -v`
Expected: FAIL — the three functions don't exist yet (ImportError).

- [ ] **Step 3: Implement the helpers**

Insert into `ChatBotAI/services/email_reconcile.py` immediately after `_conv_view` (after line 644):

```python
def booking_ref_from_note(guest_id) -> str | None:
    """Tier 1: the Buchungsnummer stored in the guest's Smoobu note, or None.
    Booking reservations carry 'Buchungsnummer: <digits>' in the reservation
    note, which Smoobu enrichment stores as the guest_note detail."""
    from ..models import GuestDetail
    d = GuestDetail.query.filter_by(guest_id=guest_id, detail_key='guest_note').first()
    if not d or not d.detail_value:
        return None
    m = re.search(r'Buchungsnummer:\s*(\d+)', d.detail_value)
    return m.group(1) if m else None


def conversation_booking_ref(conv, smoobu_service=None) -> str | None:
    """The conversation's Booking reservation number (Buchungsnummer), or None.
    Tier 1: the stored guest note (free). Tier 2: Smoobu 'reference-id' (one API
    call, only when the note yields nothing). Smoobu failure is non-fatal."""
    ref = booking_ref_from_note(conv.guest_id)
    if ref:
        return ref
    if not conv.smoobu_reservation_id:
        return None
    svc = smoobu_service
    if svc is None:
        from .smoobu_service import get_smoobu_service
        svc = get_smoobu_service()
    if not svc:
        return None
    try:
        res = svc.get_reservation(conv.smoobu_reservation_id)
    except Exception:
        logger.exception("live booking fetch: smoobu get_reservation failed for conv %s", conv.id)
        return None
    val = (res or {}).get('reference-id')
    return str(val) if val else None


def email_matches_conversation(notif, conv, conv_ref) -> bool:
    """Does this Booking email belong to this conversation?

    Exact Buchungsnummer match wins. Otherwise (no number on one side) the guest
    name is already guaranteed by the name-scoped Gmail search, so require the
    email's check-in AND check-out to equal the conversation's exactly — check-in
    alone is what mis-files a short stay onto an overlapping longer one."""
    if conv_ref and notif.booking_ref and str(notif.booking_ref) == str(conv_ref):
        return True
    return bool(
        notif.check_in and notif.check_out and conv.check_in and conv.check_out
        and _iso_date(notif.check_in) == _iso_date(conv.check_in)
        and _iso_date(notif.check_out) == _iso_date(conv.check_out)
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py -k "booking_ref_from_note or email_matches or email_ref or email_no_match or email_checkin" -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/email_reconcile.py ChatBotAI/tests/test_email_reconcile.py
git commit -m "feat(email): Buchungsnummer extraction and tiered email-conversation match"
```

---

### Task 3: Live handler with rescue + rewire `fetch_booking_for_conversation`

**Files:**
- Modify: `ChatBotAI/services/email_reconcile.py` (`_new_stats`, add `_handle_live_booking_email`, rewire `fetch_booking_for_conversation`)
- Test: `ChatBotAI/tests/test_email_reconcile.py` (replace the obsolete zero-score test; add rescue + tier tests)

**Interfaces:**
- Consumes: `_authentic_new_notif` (Task 1), `email_matches_conversation` / `conversation_booking_ref` (Task 2), `has_equivalent_message`.
- Produces: `_handle_live_booking_email(email, conv, conv_ref, cfg, router, stats)` — the live per-chat handler (tiered match + rescue). `fetch_booking_for_conversation` unchanged in signature.

- [ ] **Step 1: Drop the now-unused `skipped_lowscore` key**

In `ChatBotAI/services/email_reconcile.py`, replace `_new_stats` (lines 659-662) with:

```python
def _new_stats() -> dict:
    return {'scanned': 0, 'matched': 0, 'auto_inserted': 0, 'queued': 0,
            'skipped_dupe': 0, 'unmatched': 0, 'rejected_unauthenticated': 0}
```

- [ ] **Step 2: Add the live handler**

Insert into `ChatBotAI/services/email_reconcile.py` immediately before `fetch_booking_for_conversation` (before line 802):

```python
def _handle_live_booking_email(email, conv, conv_ref, cfg, router, stats):
    """Live per-chat handler: insert the email into THIS conversation if it
    matches (Buchungsnummer, else exact dates), and rescue a mis-filed pending
    candidate by confirming it. Unlike the scan, it does NOT skip already-queued
    emails — that skip is exactly what stranded mis-filed messages."""
    from ..models import EmailBackfillCandidate
    notif = _authentic_new_notif(email, 'booking', stats)
    if notif is None:
        return
    if not email_matches_conversation(notif, conv, conv_ref):
        return
    if has_equivalent_message(conv.id, notif, cfg['window_minutes']):
        stats['skipped_dupe'] += 1
        return
    router._store_message(
        conversation_id=conv.id, sender_type='guest', content=notif.message_text,
        platform_message_id=f"email:{notif.gmail_id}", sent_at=notif.sent_at,
        sent_via_app=False,
    )
    stats['auto_inserted'] += 1
    stats['matched'] += 1
    # Rescue: a pending candidate for this same email (possibly filed under the
    # wrong conversation) is now handled — confirm it so it leaves the review tray
    # and can never be promoted into the wrong chat.
    cand = EmailBackfillCandidate.query.filter_by(
        gmail_message_id=notif.gmail_id, status='pending').first()
    if cand:
        cand.status = 'confirmed'
        db.session.commit()
```

- [ ] **Step 3: Rewire `fetch_booking_for_conversation`**

In `fetch_booking_for_conversation`, replace the block from `cfg = get_reconcile_config()` (line 833) through the end of the function (line 852) with:

```python
    cfg = get_reconcile_config()
    conv_ref = conversation_booking_ref(conv)
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
        _handle_live_booking_email(email, conv, conv_ref, cfg, router, stats)

    logger.info("live booking fetch conv %s: %s", conversation_id, stats)
    return stats
```

(The `_conv_view`/`views` local is no longer used by the live path; remove the `views = [_conv_view(conv, 'booking')]` line if present in that block.)

- [ ] **Step 4: Replace the obsolete live-fetch test and add rescue + tier tests**

In `ChatBotAI/tests/test_email_reconcile.py`, DELETE the whole `test_live_fetch_does_not_insert_zero_score` function (it monkeypatched `pick_best_match`, which the live path no longer uses). Then append:

```python
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
```

- [ ] **Step 5: Run tests to verify they fail, then the file's full suite**

Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py -k live_fetch -v`
Expected: the 5 new `test_live_fetch_*` above initially FAIL until Steps 1–3 are in place; after them, PASS. Then run the full file:
Run: `python -m pytest ChatBotAI/tests/test_email_reconcile.py ChatBotAI/tests/test_email_flush.py -v`
Expected: PASS (no `skipped_lowscore`/`pick_best_match` references remain in live tests; scan tests still green).

- [ ] **Step 6: Commit**

```bash
git add ChatBotAI/services/email_reconcile.py ChatBotAI/tests/test_email_reconcile.py
git commit -m "feat(email): reservation-number match + candidate rescue on live fetch"
```

---

## Self-Review

**Spec coverage:**
- Tier 1 Buchungsnummer from note → `booking_ref_from_note` (Task 2). ✅
- Tier 2 Smoobu `reference-id`, lazy, non-fatal → `conversation_booking_ref` (Task 2), `test_live_fetch_matches_by_smoobu_reference_id` (Task 3). ✅
- Tier 3 name+exact dates → `email_matches_conversation` (Task 2), `test_live_fetch_matches_by_dates_when_no_note`. ✅
- Rescue mis-filed pending candidate → confirmed → `_handle_live_booking_email` + `test_live_fetch_rescues_misfiled_candidate` (Task 3). ✅
- Whole live path replaces `score>0`; scan unchanged → live path uses `_handle_live_booking_email`, `_handle_notification_email` stays threshold/queue (Tasks 1, 3). ✅
- Guards kept (anti-spoof, `email:{id}`, `has_equivalent_message`) → `_authentic_new_notif` + live handler (Tasks 1, 3). ✅
- No migration, no new deps → Tier 1 reads existing `GuestDetail`; Tier 2 uses existing `get_smoobu_service`. ✅
- Exact-match-only / safe fallthrough → `email_matches_conversation` returns bool, no fuzzy number compare; `test_live_fetch_no_insert_when_ref_and_dates_differ`. ✅

**Placeholder scan:** none — every step has full code and asserted tests.

**Type consistency:** `_authentic_new_notif(email, platform, stats)`, `booking_ref_from_note(guest_id)`, `conversation_booking_ref(conv, smoobu_service=None)`, `email_matches_conversation(notif, conv, conv_ref)`, `_handle_live_booking_email(email, conv, conv_ref, cfg, router, stats)` are used with matching names/arities across tasks. `_new_stats` loses `skipped_lowscore` (Task 3 Step 1) — no remaining code references it after the live branch and the zero-score test are removed. Booking ref compared as `str` on both sides.
