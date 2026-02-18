# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-17)

**Core value:** The system remembers EVERYTHING about every guest permanently
**Current focus:** Phase 3 - Unread Tracking

## Current Position

Phase: 3 of 8 (Unread Tracking)
Plan: 2 of 2 in current phase
Status: Phase Complete
Last activity: 2026-02-18 — Completed 03-02-PLAN.md

Progress: [#######░░░] 44%

## Performance Metrics

**Velocity:**
- Total plans completed: 7
- Average duration: 3 min
- Total execution time: 0.35 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-infrastructure-foundation | 2 | 12 min | 6 min |
| 02-polling-core | 3 | 6 min | 2 min |
| 03-unread-tracking | 2 | 2 min | 1 min |

**Recent Trend:**
- Last 5 plans: 02-01 (2 min), 02-02 (2 min), 02-03 (2 min), 03-01 (1 min), 03-02 (1 min)
- Trend: Improving

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

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

## Session Continuity

Last session: 2026-02-18
Stopped at: Completed 03-02-PLAN.md (Unread Visual Indicators) - Phase 03 complete
Resume file: .planning/phases/04-search-filter/04-01-PLAN.md
