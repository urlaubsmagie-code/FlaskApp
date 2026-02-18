---
phase: 03-unread-tracking
plan: 02
subsystem: ui
tags: [jinja2, javascript, polling, accessibility]

# Dependency graph
requires:
  - phase: 03-01
    provides: PATCH /api/conversations/{id}/read endpoint, CSS unread styles
  - phase: 02-02
    provides: inbox polling with updateInboxList()
provides:
  - Jinja template unread class rendering
  - JavaScript unread state handling in card creation/update
  - Auto mark-as-read on conversation view
affects: [inbox-display, conversation-view]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Jinja conditional class with data attribute for JS sync
    - Fire-and-forget API call pattern for non-blocking updates
    - Polling update detection via data attribute comparison

key-files:
  created: []
  modified:
    - templates/chatbot/inbox.html
    - templates/chatbot/conversation.html

key-decisions:
  - "data-is-read attribute for JavaScript state tracking during polling"
  - "Fire-and-forget PATCH call on conversation view (no await, no UI feedback needed)"
  - "Check both updated_at and is_read changes to trigger card updates"

patterns-established:
  - "Conditional Jinja class with matching data attribute for JS sync"
  - "Fire-and-forget API calls for non-critical background updates"

requirements-completed: [FILT-03, POLL-05]

# Metrics
duration: 1min
completed: 2026-02-18
---

# Phase 03 Plan 02: Unread Visual Indicators Summary

**Unread conversations display blue dot indicator in inbox, auto-marked as read when opened**

## Performance

- **Duration:** 1 min 24 sec
- **Started:** 2026-02-18T12:33:11Z
- **Completed:** 2026-02-18T12:34:35Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments
- Server-rendered inbox cards show unread styling when is_read is False
- JavaScript creates and updates cards with correct unread class based on is_read property
- Opening a conversation marks it as read via fire-and-forget PATCH call
- Polling updates correctly toggle unread state when is_read changes

## Task Commits

Each task was committed atomically:

1. **Task 1: Add unread class to Jinja template conversation cards** - `5d0a69a` (feat)
2. **Task 2: Update JavaScript card functions to handle unread state** - `345cba4` (feat)
3. **Task 3: Mark conversation as read on view** - `0362af6` (feat)

## Files Created/Modified
- `templates/chatbot/inbox.html` - Added Jinja conditional unread class, data-is-read attribute, sr-only span; updated createConversationCard() and updateConversationCard() for unread state
- `templates/chatbot/conversation.html` - Added fire-and-forget PATCH call on DOMContentLoaded to mark conversation as read

## Decisions Made
- Added data-is-read attribute to enable JavaScript to detect read state changes during polling (needed for toggles when user opens conversation in another tab)
- Used fire-and-forget pattern for mark-as-read call because user is already viewing the conversation and no UI feedback is needed
- Extended card update condition to check is_read change in addition to updated_at to ensure visual updates when read state changes independently of new messages

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Unread tracking feature complete - all requirements (FILT-03, POLL-05) satisfied
- Phase 03 complete - ready for Phase 04
- End-to-end flow verified: unread indicator appears on guest message, disappears when conversation opened

---
*Phase: 03-unread-tracking*
*Completed: 2026-02-18*

## Self-Check: PASSED

- FOUND: templates/chatbot/inbox.html
- FOUND: templates/chatbot/conversation.html
- FOUND: 5d0a69a
- FOUND: 345cba4
- FOUND: 0362af6
