# Phase 1: Infrastructure Foundation - Context

**Gathered:** 2026-02-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Database is prepared for filtering, search, and concurrent access. This phase adds the `is_read` field to conversations, enables WAL mode for concurrent database access, and sets up full-text search on messages. No UI changes — pure backend infrastructure.

</domain>

<decisions>
## Implementation Decisions

### Full-text Search Scope
- Index **everything searchable**: message content, guest names, and subjects/topics
- **Exclude** guest memory items (GuestDetail) from FTS — memories are visible on profiles, not through search
- Search should cover conversations and their associated guest names for findability

### Search Ranking
- Claude's Discretion: Choose ranking approach (relevance vs chronological) based on what makes sense for the use case

### Text Matching
- Claude's Discretion: Handle case-insensitivity and accent normalization based on SQLite FTS5 capabilities

### Migration Behavior
- Existing conversations default to **is_read = True** (all marked read, no blue dots on initial launch)
- Backup **recommended** before migrations — warn user and confirm, but don't block
- Migrations are **manual** — run via explicit command (e.g., `flask db upgrade`), not auto-applied on startup

### Claude's Discretion
- Search result ranking algorithm
- Case/accent handling in FTS
- Migration rollback strategy (all-or-nothing vs partial)
- Exact FTS5 configuration and tokenizer

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches for SQLite FTS5 and Flask-Migrate patterns.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-infrastructure-foundation*
*Context gathered: 2026-02-17*
