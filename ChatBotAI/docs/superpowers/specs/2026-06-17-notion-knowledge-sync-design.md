# Design: Notion → UMI Knowledge Base Sync

**Date:** 2026-06-17
**Status:** Approved for planning
**Author:** Brainstormed with user (Admin)

## Problem

The digital team maintains a rich, vetted "Wissensdatenbank" in Notion — a
**HANDBUCH ZUR GÄSTEBETREUUNG** (guest-care handbook) with house rules, fees,
check-in procedures, addresses, complaint-handling scripts, per-property notes,
and message templates (Vorlagen). UMI (the AI) currently answers from a small,
hand-curated `KnowledgeEntry` table and frequently lacks this information, so it
guesses or escalates unnecessarily.

We want to **connect Notion to the app** so that:

1. Guest-safe handbook content grounds UMI's answers (fed via the existing
   `KnowledgeEntry` → ContextFilter → prompt path).
2. The team's Vorlagen become `ReplyTemplate` rows usable in conversations.

**Critical constraint:** the same Notion workspace also contains highly
sensitive pages — door/key-box codes for 50+ apartments
(`🔑 Check-in Information und Schlüsselcodes`) and passwords (`Passwörter`) —
plus internal staff-only material (team meeting notes, phone procedures). A
naïve "sync everything into UMI" would let UMI leak a door code or password to a
guest. **Preventing that leak is the central design requirement.**

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Primary goal | Ground UMI's answers **and** import Vorlagen as ReplyTemplates (both in this spec) |
| Notion structure | Mix of free-form handbook pages + some tables; organized under one hub |
| Connection method | **Approach A** — native Notion API integration inside the Flask app |
| Sync direction | One-way, Notion → app (read-only on Notion) |
| Sync cadence | **Manual "Sync now" button** in Settings (no background job for v1) |
| Safety model | **Sync-all, block-by-keyword**, hardened into defense-in-depth (see §4) |
| Sync scope | **Everything recursively under the `HANDBUCH ZUR GÄSTEBETREUUNG` hub**, minus blocklist |

## Non-Goals (YAGNI)

- Scheduled / automatic / webhook-driven sync (manual button only for v1).
- Write-back to Notion (strictly one-way).
- Semantic / embedding-based retrieval. The existing keyword `ContextFilter`
  (`_filter_knowledge_entries`) already selects relevant entries per guest
  message, so a larger KB is usable as-is. Retrieval tuning is a noted
  follow-up, not part of this spec.
- Syncing the whole workspace. Scope is the handbook hub subtree.

## Architecture

```
Settings page                     services/notion_service.py
  [Sync now]  ──POST /chatbot/api/notion/sync──►  routes
                                                     │
                                                     ▼
                                          NotionService.sync()
                                            1. list_pages_under(root_hub_id)   (recursive)
                                            2. fetch_page_text(page_id)        (blocks → text)
                                            3. scrub(page)                     (§4 defense-in-depth)
                                            4. map_page(page) → entries/templates  (§5)
                                            5. upsert(entries, templates)      (§6 idempotent)
                                          → returns SyncStats (§7)
```

`notion_service.py` follows the established service pattern (cf.
`gmail_service.py`, `smoobu_service.py`): a module-level singleton retrieved via
`get_notion_service()`, initialized at app startup, configuration read from
`AISettings`. No existing file changes shape; integration points are additive.

### Components (each independently testable)

- **`NotionClient` wrapper** — thin adapter over the official `notion-client`
  SDK. Methods: `list_child_pages(page_id)` (recursive walk), `get_page(page_id)`
  → title + block tree, `block_tree_to_text(blocks)` → markdown-ish plain text.
  Pure-ish: network only in the client; conversion is a pure function.
- **`scrubber`** — pure functions, no I/O (see §4). The safety core.
- **`mapper`** — pure functions: `page_to_kb_entries(page)`,
  `page_to_template(page)`, `infer_category(page)`, `match_property(name)`
  (see §5).
- **`NotionService.sync()`** — orchestrator that wires client → scrubber →
  mapper → DB upsert, per-page error isolation, returns stats.

## Configuration (in `AISettings`, set via Settings UI)

- `notion_integration_token` — secret; the Notion internal-integration token.
- `notion_root_page_id` — the `HANDBUCH ZUR GÄSTEBETREUUNG` page id.
- `notion_block_keywords` — CSV blocklist; default:
  `schlüsselcode,schlüsselbox codes,code,passwör,password,pin,wlan-passwort,intern,🔑,🔒`.
- `notion_force_exclude_ids` / `notion_force_include_ids` — CSV page-id
  overrides (manual escape hatches, no code change needed for edge cases).
- `notion_sync_enabled` — feature dormant until a token is present; button is
  disabled otherwise.

**Prerequisite (one-time, manual):** the user creates a Notion *internal
integration*, shares the handbook hub page with it, and pastes the token into
Settings. Documented in the implementation plan and the help page.

## §4 Safety scrubber — defense-in-depth

The user chose "sync-all, block-by-keyword." Because a leaked door code is the
one genuinely costly failure, we layer three independent guards. A page must
survive **all** layers to reach UMI.

**Layer 1 — page-level block (drop the whole page):**
- title or body contains any `notion_block_keywords` term (case-insensitive), OR
- body contains a "codes" section heading (e.g. `Schlüsselbox Codes`), OR
- **code-density heuristic:** ≥3 code-shaped tokens on the page
  (`\b\d{4,6}\b` appearing near labels like `Code`, `Haustür`, an apartment
  code, or `PIN`), OR
- page id is in `notion_force_exclude_ids`.
A page in `notion_force_include_ids` skips Layer 1 (but NOT Layer 2).

**Layer 2 — value-level scrub (sanitize surviving entries):**
Before persisting any entry value, redact/drop substrings matching sensitive
patterns: `Haustür:?\s*\d+`, `\bCode\s*\d{3,6}\b`, `\b(PIN|WLAN[- ]?Passwort|Passwort)\b.*`,
standalone 4–6 digit codes adjacent to apartment labels. If scrubbing empties an
entry, the entry is dropped.

**Layer 3 — explicit overrides + audit:**
`notion_force_exclude_ids` always wins. Every blocked page and every scrubbed
value is recorded in the sync stats / log so the user can verify what was kept
vs. withheld after each run.

**Validation fixtures (real data, captured 2026-06-17):**
- `🔑 Check-in Information und Schlüsselcodes` → MUST be blocked at Layer 1
  (title keyword + "Schlüsselbox Codes" heading + dozens of code tokens).
- `💰 Extrakosten` → MUST pass and map to guest-safe entries.

## §5 Mapping rules

- **Handbook topic page → `KnowledgeEntry`(s):** split page text on `##`/`###`
  headings; each section becomes one entry (`label` = heading, `value` =
  section body, collapsed/trimmed). A page with no headings becomes one entry
  (`label` = page title). `category` inferred via `infer_category` (check-in
  pages → `checkin_checkout`, rule pages → `house_rules`, emergency → `emergency`,
  else `faq`/`general`). Never assigns `correction` or `escalation` (reserved).
- **Property association:** if the page (or its ancestor) names a known property
  (e.g. "Sonnenhof"), `match_property` resolves it to a `Property.id` and the
  entry is per-property; otherwise the entry is global (`property_id=NULL`).
- **Vorlagen → `ReplyTemplate`:** pages/rows under a "Vorlagen"/"Templates"
  section map to `ReplyTemplate` (`name` = title, `content` = body,
  `category` = inferred). Existing variable placeholders (`{guest_name}` etc.)
  are preserved verbatim.
- **Size:** entry values are trimmed to a sane cap so they remain useful to the
  keyword ContextFilter and the prompt budget.

## §6 Data model & idempotent upsert (migration p19)

Add to `KnowledgeEntry`:
- `source` `VARCHAR` default `'manual'` — one of `manual` / `ai` / `notion`.
- `notion_page_id` `VARCHAR` nullable, **indexed** — upsert key for Notion rows.
- `synced_at` `DATETIME` nullable.

Add to `ReplyTemplate`:
- `source` `VARCHAR` default `'manual'`.
- `notion_page_id` `VARCHAR` nullable, indexed.

**Upsert algorithm (per sync run):**
1. Build the set of entries/templates produced this run, keyed by
   `(notion_page_id, label)`.
2. For each produced item: update the matching `source='notion'` row in place,
   or insert if new.
3. **Reconcile deletions:** any `source='notion'` row whose `(page_id,label)` was
   NOT produced this run is deleted (its Notion source vanished or got blocked).
4. **Rows with `source` in (`manual`,`ai`) are never read, updated, or deleted**
   by the sync. Human-curated and AI-extracted knowledge is untouchable.

Migration is additive (new nullable columns + indexes); existing rows default to
`source='manual'`, preserving all current behavior.

## §7 Error handling & observability

- **Read-only on Notion.** No create/update/delete calls.
- **Per-page isolation:** each page fetch+map+scrub is wrapped; one malformed
  page logs an error and is skipped without aborting the run.
- **Stats returned & shown in Settings after sync:**
  `{pages_scanned, pages_blocked, kb_upserted, kb_deleted, templates_upserted,
  templates_deleted, values_scrubbed, errors}`, plus a list of blocked page
  titles so the user can confirm sensitive pages were withheld.
- **Token/connection errors:** missing/invalid token → friendly "Notion not
  connected" state (mirrors the existing Gmail error handling); button disabled
  when `notion_sync_enabled` is false.
- **Long-run safety:** the route runs the sync synchronously but the page count
  is bounded by the hub subtree; if it risks exceeding ~100s it must be made
  fire-and-forget (per the project's Cloudflare-524 rule) — flagged for the
  implementation plan to size.

## §8 Testing strategy

Pure functions are unit-tested without network or DB, using **fixtures taken
from the real pages fetched 2026-06-17**:
- Scrubber: `Schlüsselcodes` page → blocked (Layer 1); a synthetic entry with an
  embedded code → scrubbed (Layer 2); `Extrakosten` → passes.
- Mapper: `Extrakosten` → expected set of labeled entries with correct category;
  property page → correct `property_id`; Vorlage → `ReplyTemplate`.
- Category inference and property matching: table-driven cases.

Orchestrator tested with a `FakeNotion` (same pattern as `FakeGmail` in
`tests/test_email_reconcile.py`):
- High-level sync produces expected KB/template counts and stats.
- **Idempotency:** sync twice → no duplicates.
- **Deletion reconcile:** remove a page from the fake → its entry is deleted.
- **Isolation:** a pre-existing `source='manual'` entry is never modified.

## §9 UI

- Settings → new "Notion Wissensdatenbank" card: token field, root-page-id
  field, blocklist field, **[Sync now]** button, and a results panel showing the
  last run's stats + blocked-page list.
- German-first copy (project convention), English fallback via `i18n.js`.
- Imported KB entries appear in the existing `/chatbot/knowledge` page with a
  "Notion" source badge so the team can see provenance (and that Notion-sourced
  rows are managed by sync, not hand-edited).

## Dependencies

- New Python dependency: `notion-client` (official SDK), pinned in
  `requirements.txt`.
- Notion internal integration + token (one-time manual setup by the user).

## Open follow-ups (out of scope, noted)

- Retrieval tuning: `ai_service` currently feeds top-3 KB entries truncated to
  ~80 chars (compact prompt). With a richer KB this cap may need raising or
  relevance-ranking improvement. Track separately.
- Scheduled sync (daily) once manual sync is proven.
