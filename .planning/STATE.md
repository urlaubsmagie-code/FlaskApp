# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-17)

**Core value:** The system remembers EVERYTHING about every guest permanently
**Current focus:** Phase 2 - Polling Core

## Current Position

Phase: 2 of 8 (Polling Core)
Plan: 1 of 3 in current phase
Status: Executing Phase 2
Last activity: 2026-02-18 — Completed 02-01-PLAN.md

Progress: [###░░░░░░░] 18%

## Performance Metrics

**Velocity:**
- Total plans completed: 3
- Average duration: 5 min
- Total execution time: 0.23 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-infrastructure-foundation | 2 | 12 min | 6 min |
| 02-polling-core | 1 | 2 min | 2 min |

**Recent Trend:**
- Last 5 plans: 01-01 (7 min), 01-02 (5 min), 02-01 (2 min)
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

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

## Session Continuity

Last session: 2026-02-18
Stopped at: Completed 02-01-PLAN.md (PollingManager class)
Resume file: .planning/phases/02-polling-core/02-02-PLAN.md
