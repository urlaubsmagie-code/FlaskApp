---
phase: 01-infrastructure-foundation
plan: 02
subsystem: database
tags: [fts5, sqlite, full-text-search, triggers]

# Dependency graph
requires:
  - phase: 01-01
    provides: Flask-Migrate infrastructure for migrations
provides:
  - FTS5 virtual table for message full-text search
  - Database triggers for automatic FTS index synchronization
  - Search utility functions with BM25 ranking
  - Guest name and subject denormalization in search index
affects: [07-search-feature, phase-7-search]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - FTS5 virtual table with porter stemmer and unicode61 tokenizer
    - Database triggers for INSERT/UPDATE/DELETE synchronization
    - Non-external-content FTS5 table for denormalized JOINed data

key-files:
  created:
    - migrations/versions/6a66ca2c2d11_add_fts5_search_index.py
    - utils/search.py
  modified:
    - utils/__init__.py

key-decisions:
  - "Use non-external-content FTS5 table to support denormalized guest_name and subject from JOINs"
  - "Direct DELETE in triggers instead of FTS5 'delete' command for non-external content table"
  - "Handle SQLite string datetime in search results (raw SQL returns strings)"

patterns-established:
  - "FTS5 search with bm25() ranking for relevance scoring"
  - "Triggers synchronize FTS index on message INSERT/UPDATE/DELETE"
  - "search_messages() as primary search interface with optional conversation filtering"

requirements-completed: [INFRA-03]

# Metrics
duration: 5min
completed: 2026-02-18
---

# Phase 1 Plan 02: FTS5 Full-Text Search Index Summary

**FTS5 virtual table with porter stemmer, automatic sync triggers, and search_messages() utility returning BM25-ranked results under 1ms**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-18T11:17:26Z
- **Completed:** 2026-02-18T11:22:33Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- FTS5 virtual table created with porter stemmer and unicode61 tokenizer
- Automatic triggers sync index on message INSERT/UPDATE/DELETE
- Guest name and conversation subject denormalized into search index
- Search performance under 1ms for small datasets (well under 500ms target)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create FTS5 migration with virtual table and triggers** - `3487934` (feat)
2. **Task 2: Create search utility module** - `7b35a3d` (feat)
3. **Task 3: Test FTS5 search with sample data** - `e320dc3` (fix - datetime handling)

## Files Created/Modified

- `migrations/versions/6a66ca2c2d11_add_fts5_search_index.py` - FTS5 virtual table and triggers migration
- `utils/search.py` - Search utility functions (search_messages, search_by_guest_name, rebuild_search_index)
- `utils/__init__.py` - Export search functions

## Decisions Made

1. **Non-external-content FTS5 table** - Originally tried external content mode (`content='message'`) but FTS5 can't read denormalized data (guest_name, subject) from JOINs during rebuild. Switched to regular FTS5 table with manual population.

2. **Direct DELETE in triggers** - For non-external-content tables, use simple DELETE instead of the FTS5 'delete' special command which requires matching the original content.

3. **SQLite string datetime handling** - Raw SQL on SQLite returns datetime as strings. Added isinstance() check in search results to handle both string and datetime types.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Changed from external content to regular FTS5 table**
- **Found during:** Task 1 (applying migration)
- **Issue:** External content FTS5 (`content='message'`) expects columns directly in message table, but guest_name and subject come from JOINed tables
- **Fix:** Removed `content='message', content_rowid='id'` from CREATE VIRTUAL TABLE, changed triggers to use DELETE instead of FTS5 'delete' command, changed rebuild to use INSERT instead of rebuild command
- **Files modified:** migrations/versions/6a66ca2c2d11_add_fts5_search_index.py
- **Verification:** Migration applies successfully, search returns results
- **Committed in:** 3487934 (Task 1 commit)

**2. [Rule 1 - Bug] Fixed datetime string handling in search results**
- **Found during:** Task 3 (testing search)
- **Issue:** sent_at and updated_at returned as strings from raw SQL, causing `.isoformat()` AttributeError
- **Fix:** Added isinstance() check to handle both string and datetime types
- **Files modified:** utils/search.py
- **Verification:** Search returns results without errors
- **Committed in:** e320dc3 (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both fixes necessary for correct operation. No scope creep.

## Issues Encountered

- Initial migration attempt failed because FTS5 external content mode doesn't support denormalized data from JOINs. Had to clean up partially-applied migration and fix approach.
- Alembic downgrade tried to go too far (past ef8fc18f76c4), causing trigger error. Manually reset alembic_version table.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- FTS5 search infrastructure complete and tested
- Ready for Phase 7 search feature to build on search_messages() utility
- WAL mode (from 01-01) combined with FTS5 enables concurrent search operations

## Self-Check: PASSED

All files and commits verified:
- migrations/versions/6a66ca2c2d11_add_fts5_search_index.py: FOUND
- utils/search.py: FOUND
- utils/__init__.py: FOUND
- Commit 3487934: FOUND
- Commit 7b35a3d: FOUND
- Commit e320dc3: FOUND

---
*Phase: 01-infrastructure-foundation*
*Completed: 2026-02-18*
