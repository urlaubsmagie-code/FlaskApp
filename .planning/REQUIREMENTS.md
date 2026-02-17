# Requirements: ChatBotAI Dashboard UI

**Defined:** 2026-02-17
**Core Value:** Unified inbox with persistent guest memory that remembers everyone

## v1 Requirements

Requirements for Dashboard UI completion milestone. Each maps to roadmap phases.

### Infrastructure

- [ ] **INFRA-01**: System adds `is_read` field to Conversation model for unread tracking
- [ ] **INFRA-02**: System configures SQLite WAL mode for concurrent polling access
- [ ] **INFRA-03**: System implements full-text search index on Message.content

### Filtering

- [ ] **FILT-01**: User can filter inbox by platform (Email, WhatsApp, Airbnb, Booking)
- [ ] **FILT-02**: User can filter inbox by status (Active, Pending, Closed)
- [ ] **FILT-03**: User can see unread indicator (blue dot) on unread conversations
- [ ] **FILT-04**: User can filter inbox by specific guest via dropdown
- [ ] **FILT-05**: User can see active filter indicators showing current filters
- [ ] **FILT-06**: User can clear all filters with single click
- [ ] **FILT-07**: User's filter selections persist in URL (bookmarkable, back-button works)

### Search

- [ ] **SRCH-01**: User can search conversations by guest name
- [ ] **SRCH-02**: User can search across message content with full-text search
- [ ] **SRCH-03**: User can combine filters with search (search within filtered results)
- [ ] **SRCH-04**: User sees search results with highlighted match context
- [ ] **SRCH-05**: User sees helpful empty state when search returns no results

### Profile Editing

- [ ] **PROF-01**: User can edit guest basic info (name, email, phone) via modal form
- [ ] **PROF-02**: User can add new memory items to guest profile
- [ ] **PROF-03**: User can delete memory items from guest profile
- [ ] **PROF-04**: User can edit existing memory items inline (click to edit)

### Real-time Updates

- [ ] **POLL-01**: Inbox auto-refreshes via polling every 10-30 seconds
- [ ] **POLL-02**: Conversation view auto-refreshes for new messages
- [ ] **POLL-03**: Polling pauses when browser tab is hidden (Visibility API)
- [ ] **POLL-04**: Polling resumes and forces refresh when tab becomes visible
- [ ] **POLL-05**: User sees visual indicator when new messages arrive

## v2 Requirements

Deferred to future milestone. Tracked but not in current roadmap.

### Filtering Enhancements

- **FILT-08**: User can save filter presets for quick access
- **FILT-09**: User can manage (rename, delete) saved filter presets

### Search Enhancements

- **SRCH-06**: User can search within a single conversation thread
- **SRCH-07**: User can use advanced search operators (date range, platform)

### Profile Enhancements

- **PROF-05**: User sees confidence indicator on AI-extracted memories
- **PROF-06**: User can merge duplicate guest profiles

### Bulk Operations

- **BULK-01**: User can select multiple conversations
- **BULK-02**: User can mark selected conversations as read/unread
- **BULK-03**: User can archive selected conversations

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Notifications (audio/visual) | Defer to future milestone - polling with refresh is sufficient for v1 |
| Mobile-responsive optimization | Defer to future milestone - desktop-first for host workflow |
| WhatsApp API integration | Gmail only for v1 - other platforms deferred |
| Airbnb API integration | Gmail only for v1 - other platforms deferred |
| Booking.com API integration | Gmail only for v1 - other platforms deferred |
| WebSocket real-time updates | Polling is simpler and sufficient for 10-50 conversations |
| User authentication | Single-user system for now |
| Complex boolean search | Simple search covers 95% of use cases |
| Automatic guest deduplication | High risk of data loss - defer until explicit user request |
| Infinite scroll | Traditional pagination clearer for small datasets |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 1 | Pending |
| INFRA-02 | Phase 1 | Pending |
| INFRA-03 | Phase 1 | Pending |
| FILT-01 | Phase 4 | Pending |
| FILT-02 | Phase 5 | Pending |
| FILT-03 | Phase 3 | Pending |
| FILT-04 | Phase 6 | Pending |
| FILT-05 | Phase 4 | Pending |
| FILT-06 | Phase 4 | Pending |
| FILT-07 | Phase 4 | Pending |
| SRCH-01 | Phase 7 | Pending |
| SRCH-02 | Phase 7 | Pending |
| SRCH-03 | Phase 7 | Pending |
| SRCH-04 | Phase 7 | Pending |
| SRCH-05 | Phase 7 | Pending |
| PROF-01 | Phase 8 | Pending |
| PROF-02 | Phase 8 | Pending |
| PROF-03 | Phase 8 | Pending |
| PROF-04 | Phase 8 | Pending |
| POLL-01 | Phase 2 | Pending |
| POLL-02 | Phase 2 | Pending |
| POLL-03 | Phase 2 | Pending |
| POLL-04 | Phase 2 | Pending |
| POLL-05 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 24 total
- Mapped to phases: 24
- Unmapped: 0

---
*Requirements defined: 2026-02-17*
*Last updated: 2026-02-17 after roadmap creation*
