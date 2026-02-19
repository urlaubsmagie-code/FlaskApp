# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-17)

**Core value:** The system remembers EVERYTHING about every guest permanently
**Current focus:** Phase 8 - Profile Editing

## Current Position

Phase: 8 of 8 (Profile Editing)
Plan: 2 of 2 in current phase
Status: Complete
Last activity: 2026-02-19 — Completed 08-02-PLAN.md (Profile Editing UI)

Progress: [##########] 100%

## Performance Metrics

**Velocity:**
- Total plans completed: 16
- Average duration: 2.5 min
- Total execution time: 0.67 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-infrastructure-foundation | 2 | 12 min | 6 min |
| 02-polling-core | 3 | 6 min | 2 min |
| 03-unread-tracking | 3 | 4 min | 1.3 min |
| 04-platform-filtering | 2 | 4 min | 2 min |
| 05-status-filtering | 1 | 1 min | 1 min |
| 06-guest-filtering | 1 | 4 min | 4 min |
| 07-search | 2 | 4 min | 2 min |
| 08-profile-editing | 2 | 5 min | 2.5 min |

**Recent Trend:**
- Last 5 plans: 06-01 (4 min), 07-01 (2 min), 07-02 (2 min), 08-01 (1 min), 08-02 (4 min)
- Trend: Stable

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Initialization]: Polling over WebSocket (simpler, sufficient for 10-50 conversations)
- [Initialization]: Gmail only for v1 (reduce scope, already integrated)
- [Initialization]: Feature complete over polish (ship working features first)
- [01-01]: server_default='1' for is_read so existing conversations marked as read
- [01-01]: Migrations directory inside ChatBotAI package for self-contained module
- [01-01]: Check app.extensions to prevent double db.init_app() when blueprint registered
- [01-02]: Non-external-content FTS5 table for denormalized data (guest_name, subject from JOINs)
- [01-02]: Direct DELETE in triggers for non-external content FTS5 tables
- [01-02]: Handle SQLite string datetime in raw SQL search results
- [02-01]: Recursive setTimeout over setInterval to prevent call stacking
- [02-01]: Immediate poll on start() and on tab visible
- [02-01]: AbortController recreated per request (they can only abort once)
- [02-02]: Added data-status attribute for faster filter operations
- [02-02]: XSS prevention with escapeHtml() for user-generated content
- [02-02]: Filter and search reapplied after each polling update
- [02-03]: 10-second poll interval for conversation (faster than inbox for active viewing)
- [02-03]: Track message IDs immediately after send/AI-generate to prevent duplicates
- [02-03]: Dual-format addMessageToUI for backward compatibility
- [03-01]: PATCH over POST for idempotent state change
- [03-01]: Blue dot via ::before pseudo-element for clean DOM
- [03-01]: sr-only class follows WCAG accessibility pattern
- [03-02]: data-is-read attribute for JavaScript state tracking during polling
- [03-02]: Fire-and-forget PATCH call on conversation view (no await, no UI feedback needed)
- [03-02]: Check both updated_at and is_read changes to trigger card updates
- [03-03]: Nested guest/last_message in to_dict() for complete API serialization
- [04-01]: history.replaceState over pushState to avoid cluttering browser history
- [04-01]: Singleton pattern ensures single source of truth for filter state
- [04-01]: Combined filter logic supports platform, status, and search simultaneously
- [04-02]: Empty string for 'All' button data-filter-* value (null when parsed)
- [04-02]: Role and aria-label attributes for filter group accessibility
- [04-02]: Initialize filters before polling to apply URL state on page load
- [05-01]: No code changes needed - Phase 4 implementation satisfies all FILT-02 requirements
- [06-01]: Count conversations per guest from DOM rather than API for accuracy
- [06-01]: Only show guests with conversations in dropdown
- [06-01]: Sort guests alphabetically by name for easy scanning
- [06-01]: Guest badge class uses just 'guest' (not 'guest-{id}') since ID is numeric
- [07-01]: Sanitize snippets by escaping HTML then restoring only <mark> tags
- [07-01]: Group search results by conversation with first_snippet and match_count
- [07-01]: setSearch() does not call applyFilters - search handler does server fetch
- [07-01]: Search badge truncates queries longer than 20 characters
- [07-02]: Debounce at 300ms with 2-char minimum for search trigger
- [07-02]: Check isSearchMode in updateInboxList to prevent polling interference
- [07-02]: Search snippets injected after .conversation-preview element
- [07-02]: Restore search from URL on page load via setTimeout for async flow
- [08-01]: Use 409 Conflict for duplicate email (standard HTTP semantics)
- [08-01]: Set confidence=1.0 for manual edits (user corrections are authoritative)
- [08-01]: Trim whitespace on all input fields (prevent accidental trailing spaces)
- [08-02]: Native HTML dialog element over custom modal (better accessibility, backdrop handling)
- [08-02]: contenteditable='plaintext-only' for inline editing (prevents HTML injection)
- [08-02]: escapeHtml function for XSS prevention when inserting user content
- [08-02]: Data attributes (data-detail-id, data-editable) for JavaScript state tracking

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

## Session Continuity

Last session: 2026-02-19
Stopped at: Completed 08-02-PLAN.md (Profile Editing UI) - Phase 8 complete, all plans executed
Resume file: None - project complete
