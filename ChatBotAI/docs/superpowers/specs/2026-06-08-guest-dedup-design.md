# Guest Deduplication + Prevention — Design

**Date:** 2026-06-08
**Status:** Approved (design), pending implementation plan
**Scope:** ChatBotAI — clean up duplicate `Guest` rows from Smoobu sync AND fix the root cause so new bookings stop creating duplicates.

## Problem

Live DB (`instance/chatbot.db`) holds **4,506 guests**, of which **463 names are duplicated** for **~2,657 redundant rows**. Worst offenders: Nathalie Roos ×247, Steven Amaya ×175, Edgars Iskrovs ×172, Gero Thannisch ×98, Benjamin Schmidt ×90.

**Root cause:** `services/smoobu_service.py` (~line 674) creates each Smoobu guest with `smoobu_guest_id = reservation_id`. Every booking has a unique `reservation_id`, so the same person becomes a new `Guest` on every reservation. The existing fallback match (email → name → smoobu_guest_id) is fragile, and migration `p17`'s partial unique index on `smoobu_guest_id` cannot catch these because each row has a *different* `smoobu_guest_id`.

**Data characteristics (drive the strategy):**
- The large duplicate groups have **no email and no phone** (name-only) → most redundant rows can only be matched by name.
- `email` is a **unique** column (1,107 populated) → no email-based dupes possible.
- `phone` (1,730) and `name` are **not** unique.
- `booking_id` / `airbnb_id` are unused (0 populated) — all guests originate from Smoobu.
- **4 name-groups have multiple distinct emails** and **6 have multiple distinct phones** → proof that different people can share a name. These must NOT be blindly merged.

## Decisions (from brainstorming)

| Decision | Choice |
|---|---|
| Scope | Cleanup **and** prevention |
| Match key | Name-safe + email/phone: merge by shared email/phone, and same-name groups **only when no conflicting email/phone**; skip + report conflicts |
| Merge policy | Richest profile wins + backfill |
| Prevention | Identity-based matching in Smoobu sync; stop overloading `smoobu_guest_id` with `reservation_id` |
| Safety | Standalone script: `--dry-run` → backup → `--apply` |
| `find_or_create_guest` | Leave as-is for now (not unified onto shared matcher) |

## Architecture

One shared matching module is the single source of truth for "same guest", used by both the cleanup script and the prevention path so behavior cannot drift.

### Component 1 — `services/guest_matching.py` (new)
- **Normalizers:** `normalize_email` (lowercase, trim); `normalize_phone` (digits only); `normalize_name` (trim, collapse internal whitespace, casefold).
- **Match rule (safe):** two guests are the same iff they share a normalized email, OR a normalized phone, OR an identical normalized name with **no conflicting** email/phone between them.
- **Conflict definition:** a candidate name-group is a conflict if its members collectively have >1 distinct normalized email or >1 distinct normalized phone.

### Component 2 — `scripts/dedup_guests.py` (new)
- **Grouping:** transitive grouping over all guests by normalized email/phone/name. A name-only group is eligible only if it has ≤1 distinct email and ≤1 distinct phone. Conflict groups are **skipped and logged**, never auto-merged.
- **Winner selection:** (1) prefer a row with email or phone; (2) tie-break by most conversations; (3) then lowest `id`.
- **Consolidation (per group, one transaction):**
  - Backfill winner's null `email` / `phone` / `notes` from losers (values are consistent within an eligible group).
  - `first_contact` = earliest, `last_contact` = latest, `total_stays` = sum.
  - Reassign `Conversation.guest_id` and `GuestDetail.guest_id` (and any other Guest FK confirmed during planning) to the winner.
  - Dedupe identical `GuestDetail` rows on the winner (same detail_type + value).
  - Delete loser `Guest` rows.
- **Modes:**
  - `--dry-run` (default): print eligible-group count, total rows to delete, a sample of the largest merges, and all skipped conflict groups. No writes.
  - `--apply`: WAL checkpoint → timestamped backup `instance/chatbot.db.bak-pre-dedup-<ts>` → execute. Idempotent (a second run finds 0 eligible groups).

### Component 3 — Prevention in `services/smoobu_service.py` (~lines 664–687)
- Replace the inline email→name→`smoobu_guest_id=reservation_id` logic with a call to the shared matcher (email → phone → safe-name).
- **Stop setting `smoobu_guest_id = reservation_id`.** The reservation identity already lives on `Conversation.smoobu_reservation_id`.
- Planning-time check: does the Smoobu reservation detail payload expose a *stable* guest id (distinct from reservation id)? If yes, store it in `smoobu_guest_id` and prefer it in matching.
- Keep the existing `IntegrityError` re-query fallback for the email-unique race.

## Safety, testing, logging

- **Rollback:** restore the timestamped `.bak`. Documented in a `DEDUP_LOG.md` step table (per project log-doc convention).
- **Tests:**
  - Unit tests for `guest_matching` — email/phone/name matches and conflict-skip behavior.
  - Merge test against a copy DB asserting: no orphaned `Conversation`/`GuestDetail` rows, expected post-merge counts, and idempotency on re-run.
- **Order of execution:** ship + verify prevention first (so cleanup isn't immediately re-polluted), then run cleanup `--dry-run`, review, then `--apply`.

## Risks / edge cases

- Backfilling an email onto the winner cannot collide with an out-of-group guest because `email` is unique and an eligible group has ≤1 distinct email. Safe.
- ~4,506 guests fit comfortably in memory; no batching needed.
- Conflict groups (4 multi-email, 6 multi-phone) are intentionally left for manual review, reported by `--dry-run`.
- Name normalization could over-merge genuinely different people who share a name and have no contact info (e.g. Benjamin Schmidt ×90). Accepted trade-off per the chosen strategy; the backup is the safety net.

## Out of scope

- `memory_service.find_or_create_guest` refactor (left as-is).
- Any change to `Conversation` / `Message` schema.
- Airbnb/WhatsApp/Booking platform-id matching (those id columns are unused).
