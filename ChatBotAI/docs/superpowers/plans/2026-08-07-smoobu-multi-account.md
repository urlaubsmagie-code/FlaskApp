# Smoobu Multi-Account (Sonnenhof) — Implementation Plan

**Date:** 2026-08-07
**Goal:** Connect a second Smoobu account (new Sonnenhof apartment) to UMI —
messages, reservations, properties (rooms/rules) — without ever sending a
message on the wrong account.
**Approach:** tagged accounts (chosen over try-key-1-then-key-2).

## Research findings (verified, not assumed)

| # | Finding | Evidence |
|---|---------|----------|
| 1 | `GET /api/me` returns the account identity | Live call with the prod key → `{"id":385537,"firstName":"Urlaubsmagie","lastName":"GmbH","email":"urlaubsmagie@googlemail.com"}` |
| 2 | **Every webhook carries the account id** in `user` | 19,675 logged webhooks in `instance/smoobu_webhooks.log`, all `"user": 385537`; sample: `{"action":"newMessage","user":385537,"data":{...}}` |
| 3 | (1) and (2) are the same number → account routing needs **no manual tagging**: the key self-identifies, the webhook self-identifies | 385537 both sides |
| 4 | Every send/sync call site already has the `Conversation` in hand | 10 call sites: `message_router.py:704,854`, `quick_replies.py:83`, `routes.py:1415,2485,4409,4476,4568,4730,4776`, `email_reconcile.py:678` |
| 5 | `Property.smoobu_apartment_id` is **globally unique** in our schema | `models.py:474`, `uq_property_smoobu_apartment_id` from `p4` — collision risk across accounts, must become composite |
| 6 | `Conversation.smoobu_reservation_id` is indexed, **not** unique, and is only ever set by the sync itself | `models.py:269`; writes only at `smoobu_service.py:789,1247` |
| 7 | The service is a module-level singleton with ~30 `get_smoobu_service()` call sites | `services/smoobu_service.py:1820-1836` |
| 8 | Latest migration revision is `p21_knowledge_street` | `migrations/versions/` |

**Consequence:** `get_smoobu_service()` stays as-is (account 1) so ~20 unrelated
call sites don't move. Only the 10 conversation-scoped sites, the daemon, and
the webhook become account-aware.

## Design

**Account registry.** `AISettings`:
- `smoobu_api_key` + new `smoobu_account_id` (account 1, backfilled = 385537)
- `smoobu_api_key_2` + `smoobu_account_id_2` (Sonnenhof)

On connect the route calls `/me`, stores the returned id. No manual entry, no
typo risk. A key whose `/me` id already exists is rejected (same account twice).

**Service registry** in `smoobu_service.py`:
```
get_smoobu_service()              # unchanged → account 1  (back-compat)
get_smoobu_services()             # [SmoobuService, ...] for daemon/webhook fan-out
get_smoobu_service_for(conv_or_property)   # by tag, falls back to account 1
```
`SmoobuService` gains `self.account_id`, set from its settings pair.

**DB (migration p22):**
- `property.smoobu_account_id` (String(20), nullable, index)
- `conversation.smoobu_account_id` (String(20), nullable, index)
- backfill both to `'385537'` where a smoobu id is present
- drop `uq_property_smoobu_apartment_id`, add
  `uq_property_account_apartment (smoobu_account_id, smoobu_apartment_id)`

Nullable + fallback-to-account-1 means the migration is non-breaking: an
un-tagged row behaves exactly as today.

**Routing rules:**
- send / per-conversation sync / reservation fetch → `get_smoobu_service_for(conversation)`
- webhook → `payload['user']` → matching service; unknown id → log + ignore
- daemon → loop `get_smoobu_services()`, each account independently
  (one dead key must not stop the other)
- `sync_properties` / `sync_messages` stamp `smoobu_account_id = self.account_id`
  on every row they create

**Rooms / rules for the new apartment:** nothing new. `sync_properties()` already
imports rooms, max guests, check-in/out times per apartment; `house_rules` and
knowledge entries are edited per property in the UI as they are today.

## Status — steps 1-8 implemented 2026-08-07, prod DB untouched

All code is on the working tree; 302 tests green. Migration p22 verified on a
**copy** of the prod DB (upgrade → downgrade → upgrade). Nothing applied live.

Extra findings during implementation:
- `property.smoobu_apartment_id` has **no** unique index or constraint in the
  live DB at all — an earlier batch migration rebuilt the table and the startup
  schema-repair re-added the column without it. p22 restores uniqueness as the
  composite index. (No duplicates exist today: 53 rows, 0 dupes.)
- The live DB carries a leftover `_alembic_tmp_conversation` table from an
  aborted migration. Harmless now, but it blocks any future SQLite batch
  rebuild of `conversation`. Worth dropping separately.
- `p22.downgrade()` intentionally keeps the two columns (dropping a column
  rebuilds the table, which breaks the FTS5 triggers); it only reverts the
  indexes.
- The account id is **self-healing**: `SmoobuService.ensure_account_id()` runs
  at the start of each daemon cycle, calls `/me` once and stamps the untagged
  rows. Verified on the DB copy: 3181 conversations + 53 properties tagged
  `385537`.

## Smoobu's new HMAC auth (discovered 2026-08-10 with the Sonnenhof key)

The Sonnenhof account issues a **token pair**, not a legacy key:
`Label` = `X-API-Key` (`usr_live_…`), `Verschlüsselung` = the HMAC secret.

Verified live against the Sonnenhof account (`/me`, `/apartments`,
`/reservations`, `/threads` — all 200):

```
canonical = METHOD 
 PATH 
 QUERY 
 TIMESTAMP 
 NONCE 
 SHA256hex(body) 
 API_KEY
X-Signature = base64( HMAC-SHA256(secret, canonical) )
```
- PATH **includes** the `/api` prefix (`/api/me`, not `/me`) — `/me` returns 401.
- The secret is used as the **literal string** shown in the dialog; base64-decoding
  it fails.
- QUERY is the alphabetically sorted query string; empty for POSTs with a body.
- TIMESTAMP is ISO-8601 UTC (`…Z`), valid ±5 min; NONCE is a fresh uuid4.
- The body must be serialized by us (not by `requests`) so the hash covers the
  exact bytes sent.

Headers: `X-API-Key`, `X-Timestamp`, `X-Nonce`, `X-Signature` — all four required.

**Legacy `Api-Key` is sunset 2026-09-25** for all Smoobu users, so the primary
account (385537) must move to a token pair before then. `SmoobuService` already
supports both: HMAC when a secret is stored, legacy header when it isn't.

Sonnenhof account: id **1782807**, Anna-Lena Hübbers, sonnenhof.um@gmail.com —
**not one apartment**: 20+ rooms, 114 reservations, 550 threads, 591 unread.

## No-history policy for new accounts (decided 2026-08-10)

Sonnenhof has 550 threads / 591 unread. The team does **not** want that history
imported — only messages that arrive from the connect moment on.

`AISettings.smoobu_sync_from[_N]` holds the cutoff, written automatically when a
*new* account is connected (skipped when chats for that account already exist,
so rotating the primary key doesn't suddenly cut it off). Three guards:

| Where | Guard | Why |
|-------|-------|-----|
| `sync_conversation_messages` message loop | skip `msg_time < cutoff` | webhook-triggered fetch of an old thread imports only the new message |
| `sync_recent_threads` | skip when `latest_message.created_at < cutoff` | no API call at all for history threads |
| `sync_messages` (/reservations) | skip unknown reservations with `modified_at < cutoff` | otherwise 114 message fetches per cycle, forever |

Consequence: the per-chat manual sync button also honours the cutoff — a
Sonnenhof chat cannot pull its pre-cutoff history. Add an explicit override
only if the team asks for it.

## Steps

| # | Step | Files | Risk |
|---|------|-------|------|
| 1 | `/me` support + `account_id` on `SmoobuService`; registry functions | `services/smoobu_service.py` | low |
| 2 | Migration p22 (2 columns, backfill, composite unique) | `migrations/versions/p22_*.py`, `models.py` | **prod DB** |
| 3 | Stamp `smoobu_account_id` on Property/Conversation creation + `_resolve_property_id` filters by account | `services/smoobu_service.py` | med |
| 4 | Route the 10 conversation-scoped call sites through `get_smoobu_service_for()` | `message_router.py`, `quick_replies.py`, `routes.py`, `email_reconcile.py` | med |
| 5 | Webhook dispatch by `payload['user']` | `routes.py:4037+` | med |
| 6 | Daemon loops all accounts (per-account lock, per-account status file line) | `app.py:_start_background_sync` | med |
| 7 | Settings UI: second Smoobu card (connect/disconnect/status/sync properties), account label on the property list | `templates/chatbot/settings.html`, `static/js/*`, `routes.py:3991-4035` | low |
| 8 | Tests: routing picks the right key, webhook by `user`, unknown account ignored, untagged row falls back to account 1 | `tests/test_smoobu_multi_account.py` | low |
| 9 | Connect Sonnenhof key, run property sync, register the webhook URL in the second Smoobu account | live | **pending — needs the key** |

## Rollback

- Step 2: `flask db downgrade` restores the old unique index; the app runs
  unchanged with the columns present but unused. Take `instance/chatbot.db`
  backup first (`chatbot.db.bak-pre-p22-<date>`).
- Steps 1,3-8: single feature branch `feat/smoobu-multi-account`, revert the branch.
- Emergency: clear `smoobu_api_key_2` in Settings → the registry falls back to
  exactly today's single-account behaviour.

## Open items for the user

1. API key for the Sonnenhof Smoobu account (Settings → API in that account).
2. Admin access to that account to register the webhook URL
   `https://umteamsbz.com/chatbot/api/webhooks/smoobu` — without it the new
   account only syncs every 600s via the daemon.
3. Confirm both accounts share one inbox (assumed yes).
