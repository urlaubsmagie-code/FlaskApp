# Roadmap: ChatBotAI Dashboard UI

## Overview

This roadmap delivers the Dashboard UI completion milestone (Step 7) for ChatBotAI. Starting from infrastructure foundations (database schema and search index), we build polling-based real-time updates, then layer filtering and search capabilities on top, and finish with guest profile editing. Each phase delivers a coherent, testable capability that builds toward the complete dashboard experience.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Infrastructure Foundation** - Database schema changes and search index setup
- [ ] **Phase 2: Polling Core** - Real-time inbox and conversation updates via polling
- [ ] **Phase 3: Unread Tracking** - Visual indicators for unread conversations
- [ ] **Phase 4: Platform Filtering** - Filter inbox by communication platform
- [ ] **Phase 5: Status Filtering** - Filter inbox by conversation status
- [ ] **Phase 6: Guest Filtering** - Filter inbox by specific guest
- [ ] **Phase 7: Search** - Search conversations by name and message content
- [ ] **Phase 8: Profile Editing** - Edit guest info and manage memory items

## Phase Details

### Phase 1: Infrastructure Foundation
**Goal**: Database is prepared for filtering, search, and concurrent access
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-02, INFRA-03
**Success Criteria** (what must be TRUE):
  1. Conversation model has is_read field that persists across server restarts
  2. Database operates in WAL mode (verified via PRAGMA query)
  3. Full-text search on messages returns results in under 500ms for 1000+ messages
**Plans**: 2 plans in 2 waves

Plans:
- [ ] 01-01-PLAN.md — Schema migration, is_read field, and WAL mode setup (Wave 1)
- [ ] 01-02-PLAN.md — FTS5 full-text search index with triggers (Wave 2)

### Phase 2: Polling Core
**Goal**: Inbox and conversations update automatically without page refresh
**Depends on**: Phase 1
**Requirements**: POLL-01, POLL-02, POLL-03, POLL-04
**Success Criteria** (what must be TRUE):
  1. Inbox list refreshes automatically every 10-30 seconds showing new conversations
  2. Conversation view shows new messages without page refresh
  3. Polling pauses when browser tab is hidden (no network requests in background)
  4. Polling resumes and fetches latest data when tab becomes visible
**Plans**: 3 plans in 2 waves

Plans:
- [ ] 02-01-PLAN.md — PollingManager class with visibility API (Wave 1)
- [ ] 02-02-PLAN.md — Inbox polling with incremental DOM updates (Wave 2)
- [ ] 02-03-PLAN.md — Conversation message polling (Wave 2)

### Phase 3: Unread Tracking
**Goal**: Users can see at a glance which conversations have unread messages
**Depends on**: Phase 1, Phase 2
**Requirements**: FILT-03, POLL-05
**Success Criteria** (what must be TRUE):
  1. Unread conversations display blue dot indicator in inbox list
  2. Opening a conversation marks it as read (blue dot disappears)
  3. New message arrival (via polling) shows visual indicator on inbox
**Plans**: 2 plans in 2 waves

Plans:
- [ ] 03-01-PLAN.md — Mark-as-read API endpoint and CSS styling (Wave 1)
- [ ] 03-02-PLAN.md — Unread class in templates and auto-mark-read on view (Wave 2)

### Phase 4: Platform Filtering
**Goal**: Users can filter inbox to show only conversations from a specific platform
**Depends on**: Phase 2
**Requirements**: FILT-01, FILT-05, FILT-06, FILT-07
**Success Criteria** (what must be TRUE):
  1. User can select platform (Email, WhatsApp, Airbnb, Booking) to filter inbox
  2. Active filter is visible as a badge/indicator showing current selection
  3. User can clear all filters with single click returning to full inbox
  4. Filter selection persists in URL (back button restores previous filter, URL is shareable)
**Plans**: TBD

Plans:
- [ ] 04-01: FilterState module and URL sync
- [ ] 04-02: Platform filter API and UI

### Phase 5: Status Filtering
**Goal**: Users can filter inbox by conversation status
**Depends on**: Phase 4
**Requirements**: FILT-02
**Success Criteria** (what must be TRUE):
  1. User can filter inbox by status (Active, Pending, Closed)
  2. Status filter combines with platform filter (both active simultaneously)
  3. Status filter selection persists in URL alongside platform filter
**Plans**: TBD

Plans:
- [ ] 05-01: Status filter implementation

### Phase 6: Guest Filtering
**Goal**: Users can filter inbox to show only conversations with a specific guest
**Depends on**: Phase 4
**Requirements**: FILT-04
**Success Criteria** (what must be TRUE):
  1. User can select a specific guest from dropdown to filter inbox
  2. Guest filter works alongside platform and status filters
  3. Dropdown shows guest names with conversation count
**Plans**: TBD

Plans:
- [ ] 06-01: Guest filter dropdown and API

### Phase 7: Search
**Goal**: Users can find conversations by searching guest names and message content
**Depends on**: Phase 1, Phase 4
**Requirements**: SRCH-01, SRCH-02, SRCH-03, SRCH-04, SRCH-05
**Success Criteria** (what must be TRUE):
  1. User can search conversations by typing guest name
  2. User can search across all message content with results showing match context
  3. Search works with active filters (search within filtered results)
  4. Search results highlight matching text in context preview
  5. Empty search results show helpful message with suggestions
**Plans**: TBD

Plans:
- [ ] 07-01: SearchManager module and API
- [ ] 07-02: Search UI with highlights and empty states

### Phase 8: Profile Editing
**Goal**: Users can manually add, edit, and delete guest information and memories
**Depends on**: Nothing (independent of filtering/search)
**Requirements**: PROF-01, PROF-02, PROF-03, PROF-04
**Success Criteria** (what must be TRUE):
  1. User can edit guest basic info (name, email, phone) via modal form
  2. User can add new memory items to any guest profile
  3. User can delete existing memory items from guest profile
  4. User can edit memory items inline (click to edit, save on blur/enter)
**Plans**: TBD

Plans:
- [ ] 08-01: Guest basic info editing
- [ ] 08-02: Memory item CRUD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Infrastructure Foundation | 0/2 | Not started | - |
| 2. Polling Core | 0/3 | Not started | - |
| 3. Unread Tracking | 0/2 | Not started | - |
| 4. Platform Filtering | 0/2 | Not started | - |
| 5. Status Filtering | 0/1 | Not started | - |
| 6. Guest Filtering | 0/1 | Not started | - |
| 7. Search | 0/2 | Not started | - |
| 8. Profile Editing | 0/2 | Not started | - |
