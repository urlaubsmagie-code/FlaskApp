# Plan: Eliminate Missing / Hidden Conversations

**Date:** 2026-05-22
**Trigger:** Smoobu thread for "Jana Uhlig" (booking 138003267) was visible at Smoobu's API on page 1 of `/threads`, but completely absent from our DB and inbox. Manual `sync_conversation_messages('138003267')` imported her instantly — proving the data was reachable, our sync just never reached for it.

**Objective:** 100% of Smoobu conversations must be ingested and visible in the inbox. Missing/hidden chats defeat the purpose of the project.

---

## Diagnosis (verified, not assumed)

### Ingestion layer — `services/smoobu_service.py`

1. **`sync_messages` only ever fetches page 1 of `/threads`** (`smoobu_service.py:403`). No pagination loop.
2. **Smoobu caps `/threads` page size at 25** regardless of `page_size=100`. With `page_count=567`, each daemon cycle sees the most recent 25 threads of ~14,000 total.
3. **`newMessage` webhook fires only for `sender='guest'` / `msg_type=inbox`** (`smoobu_service.py:554`). Outbound owner messages typed in Smoobu UI generate **zero webhooks**.
4. **Owner-only threads (e.g. proactive host outreach to upcoming arrivals) have no path into our system** unless they happen to be in the top 25 when the daemon polls. Jana's thread had 4 outbound owner messages, 0 guest replies → exactly this case.
5. **`_FULL_SYNC_COOLDOWN = 30s` is global**, not per-reservation. `force=True` bypasses the cooldown but does **not** fix the pagination cap.

### Display layer — `routes.py`, `inbox.html`, `inbox.js`, `filter-state.js`

6. **Server-side filter is benign**: only `Conversation.platform != 'playtest'`. No hidden `is_archived` / `user_id` / `cancelled_at` filter (`routes.py:249-261`).
7. **Initial page load shows 50 most-recent conversations**, "Load More" paginates server-side. No client cap.
8. **🐛 Search bar (`/api/search`) is FTS5 over `Message.content` only** (`routes.py:715-799`). It does **not** index `Guest.name`. Searching "Jana Uhlig" cannot find a guest whose name only appears in metadata. This is an independent bug worth fixing in the same wave.

### Data layer — `models.py`, migrations

9. **Migrations p16 (`cancelled_at`) and p17 (`guest_dedup_unique`) ARE applied.** The "server restart pending" note in memory is stale.
10. **Backfill idempotency is solid**:
    - `Conversation.platform_id` (e.g. `smoobu-138003267`) — uniquely indexed → no duplicate conversations
    - `Message.platform_message_id` — partial unique index from p14 → no duplicate messages, IntegrityError handled
    - `Guest`: dedup by email > phone > smoobu_guest_id with IntegrityError fallback. Some risk of name-level duplicates (see #11).
11. **Existing duplicate Guest problem** (out of scope for this plan, but flagged):
    - Nathalie Roos: 247 rows
    - Steven Amaya: 175 rows
    - 9 other names: 30-172 each
    - Total: 1000+ duplicate Guest rows
    - Cause: `smoobu_guest_id` is set to *reservation_id* (different per booking), not actual guest identity. p17's partial unique index can't catch this.

---

## Solution Options

### Option A — Minimal: paginate `/threads`

Walk all 567 pages of `/threads` per sync cycle, short-circuit when a page contains only threads whose `last_message_time` matches what we already have.

**Pros**: smallest possible change, fixes the cap.
**Cons**:
- Still misses threads Smoobu *omits* from `/threads` (we know it's flaky for some Booking.com convos)
- Doesn't change the fact that the daemon now does 567 API calls every 10 min during cold-start
- Doesn't help owner-only thread discovery if Smoobu's `/threads` ordering pushes them off

**Cost**: 1 file changed, ~30 LOC.

---

### Option B — Switch to `/reservations` discovery ⭐ **recommended**

Replace `/threads` polling with `/reservations?from=<today-90d>` as the primary discovery source. Paginate fully. For each reservation, call `sync_conversation_messages(reservation_id)`.

**Why this is better**:
- `/reservations` lists **every booking**, with or without messages — owner-only threads are guaranteed visible
- Bounded scope (90-day window covering recent + upcoming stays) keeps cost predictable
- `sync_conversation_messages` is the same code path manual sync uses; battle-tested, idempotent
- Cooperates with the webhook: webhook handles real-time guest messages (fast), daemon catches everything else (complete)

**Pros**:
- Complete coverage for the conversations users actually care about
- Bounded API cost (~50 pages × 50 reservations = ~2500 reservations checked per full pass)
- Owner-only threads work
- Survives Smoobu omitting threads from `/threads`

**Cons**:
- Each cycle hits `/reservations/{id}/messages` for every reservation in the window — but the existing `total_from_api <= len(known_ids)` quick-check short-circuits cheaply when nothing changed
- 90-day window means very-long-stay guests beyond the window need re-discovery (rare; can extend window if needed)

**Cost**: 1 file changed, ~60 LOC. Plus settings field for the window length.

---

### Option C — Hybrid: B + one-time historical backfill ⭐⭐ **recommended for full closure**

Option B for steady-state + a one-time backfill that walks **all 567 pages of `/threads`** to catch any pre-existing missed conversations (like Jana). Run once, gated behind a button in Settings.

**Pros**:
- Catches existing backlog (potentially many threads like Jana sitting un-imported right now)
- Steady-state cost matches Option B
- Backfill is idempotent — safe to re-run

**Cons**:
- One-time backfill takes ~5-10 minutes to walk all pages (run during low-traffic window)
- More code than B alone

**Cost**: Option B + 1 admin route + 1 Settings button + ~80 LOC.

---

### Option D — Paranoid: C + drift monitoring

Option C + a daily reconciliation job that compares `len(local Smoobu Conversations in last 90d)` vs `len(Smoobu reservations in last 90d)` and surfaces the delta in the Debug dashboard.

**Pros**: catches future drift before users notice
**Cons**: more code, more dashboard surface area, mostly redundant if B+C are solid.

**Cost**: C + ~50 LOC + dashboard tile. Worth doing later, not now.

---

## Adjacent fixes (small, do in the same wave)

Independent of which option above, these are cheap wins:

1. **Fix search to include `Guest.name`** — `/api/search` should `UNION` an FTS message hit with a `LIKE` match on `Guest.name`, `Guest.email`, `Guest.phone`. Otherwise users can't find guests by name unless their name appears in a message. (~15 LOC in `routes.py:715`.)
2. **Per-reservation sync cooldown** — replace the 30s global cooldown with a per-reservation timestamp so multiple users hitting "Sync" on different conversations don't block each other. (~10 LOC in `smoobu_service.py`.)
3. **`[WEBHOOK_MISS]` file logger** — already proposed last conversation; once C is live the `[WEBHOOK_MISS]` warnings become the canary for any remaining gaps. (~10 LOC in `app.py`.)

## Out of scope (separate plan)

- **1000+ duplicate Guest cleanup** — requires a name+email merge migration with manual review. Big and risky enough to deserve its own plan + dry-run report.

---

## Recommended path

**Option C + the three adjacent fixes.**

Sequence:
1. Patch `sync_messages` to use `/reservations`-based discovery (Option B).
2. Add `/api/smoobu/backfill-historical` admin route + Settings button (Option C add-on).
3. Fix search to include Guest.name/email/phone.
4. Per-reservation cooldown.
5. File logger for daemon warnings.
6. Run the historical backfill once. Observe `[WEBHOOK_MISS]` log for a week. If clean → declare problem solved.

**Estimated effort**: 1 focused work session, ~200 LOC across 3-4 files, no schema changes, no migrations.

**Risk**: Low. All changes are additive or replace one well-tested code path with another that uses the same downstream `sync_conversation_messages`. Idempotency already proven by the Jana repair.

---

## Decisions (locked 2026-05-22)

- **Chosen path: Option B** — `/reservations`-based discovery only. No historical backfill. Old chats are not relevant; users care about newest only.
- **Discovery window: 90 days** (rolling, `from=<today-90d>`). Covers recent stays + upcoming arrivals; longer-lead bookings still get caught when first created.
- **Bundle adjacent fixes**: yes. Search bar (Guest.name/email/phone), per-reservation cooldown, and `[WEBHOOK_MISS]` file logger go in the same wave.
