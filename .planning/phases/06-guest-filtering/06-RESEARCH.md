# Phase 6: Guest Filtering - Research

**Researched:** 2026-02-19
**Domain:** Guest dropdown filter, FilterState extension, API enhancement
**Confidence:** HIGH

## Summary

Phase 6 adds guest-specific filtering to the inbox, allowing users to filter conversations to show only those from a specific guest. This builds directly on the FilterState infrastructure created in Phase 4 for platform and status filtering.

The implementation is straightforward because:
1. **FilterState module already exists** - The singleton `filterState` manages URL sync, combined filters, and UI updates
2. **Guest data already in DOM** - Conversation cards have `data-platform` and `data-status`; adding `data-guest-id` follows the same pattern
3. **API endpoint exists** - `/api/guests` returns all guests (though lacks conversation counts)
4. **Dropdown pattern is simple** - HTML `<select>` with JavaScript change handler calling `filterState.setGuest()`

The key design decisions are:
- **Extend FilterState** to support a `guest` filter alongside platform and status
- **Add `data-guest-id` attribute** to conversation cards for client-side filtering
- **Fetch guests with conversation counts** for dropdown display
- **Ensure dropdown shows guest names** with count suffix like "Maria Schmidt (3)"

**Primary recommendation:** Extend `FilterState` class with `setGuest()` method and guest URL parameter. Add guest dropdown to filter bar. Include conversation count in API response or compute client-side.

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| FILT-04 | User can filter inbox by specific guest via dropdown | Guest dropdown in filter bar populated from `/api/guests`; FilterState extended with `guest` state and `setGuest()` method; `data-guest-id` attribute on conversation cards; combined filtering with platform, status, and search |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Vanilla JavaScript | ES6+ | Dropdown population, FilterState extension | Consistent with existing codebase |
| HTML5 `<select>` | Native | Guest dropdown UI | Simple, accessible, native form control |
| FilterState singleton | Existing | State management, URL sync | Already handles platform/status/URL sync |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Flask API | Existing | Guest list endpoint | Already exists at `/api/guests` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `<select>` dropdown | Autocomplete search input | Autocomplete more complex; dropdown sufficient for <100 guests |
| Fetch on page load | Cache guests in session | Caching adds complexity; single fetch per page load acceptable |
| Server-side guest count | Client-side count from DOM | Server-side more accurate but requires API change; client-side works if all conversations loaded |

**Installation:**
```bash
# No installation required - all native APIs and existing infrastructure
```

## Architecture Patterns

### Recommended Project Structure
```
static/
├── js/
│   ├── app.js            # Existing utility functions
│   ├── polling.js        # Existing PollingManager class
│   └── filter-state.js   # UPDATE: add guest filter state
templates/
└── chatbot/
    └── inbox.html        # UPDATE: add guest dropdown, data-guest-id attribute
routes.py                  # UPDATE: add conversation count to guests API (optional)
```

### Pattern 1: FilterState Extension for Guest Filter
**What:** Add `guest` property to FilterState state, `setGuest()` method, and URL sync
**When to use:** Guest filter implementation
**Example:**
```javascript
// Source: Extending existing FilterState pattern from Phase 4
class FilterState {
    constructor() {
        this.state = {
            platform: null,  // existing
            status: null,    // existing
            guest: null      // NEW: guest ID or null for all
        };
        // ... existing initialization
    }

    /**
     * Load filter state from URL query parameters
     */
    loadFromURL() {
        const params = new URLSearchParams(window.location.search);
        this.state.platform = params.get('platform') || null;
        this.state.status = params.get('status') || null;
        this.state.guest = params.get('guest') || null;  // NEW
    }

    /**
     * Save current filter state to URL
     */
    saveToURL() {
        const url = new URL(window.location.href);

        // Existing platform/status handling...

        // NEW: Set or delete guest param
        if (this.state.guest) {
            url.searchParams.set('guest', this.state.guest);
        } else {
            url.searchParams.delete('guest');
        }

        history.replaceState(null, '', url.toString());
    }

    /**
     * Set guest filter
     * @param {string|null} guestId - Guest ID to filter by, or null for all
     */
    setGuest(guestId) {
        this.state.guest = guestId || null;
        this.saveToURL();
        this.applyFilters();
        this.updateUI();
    }

    /**
     * Clear guest filter (shorthand)
     */
    clearGuest() {
        this.setGuest(null);
    }

    /**
     * Apply current filters to conversation cards - UPDATED
     */
    applyFilters() {
        const cards = document.querySelectorAll('.conversation-card');
        const searchInput = document.getElementById('searchInput');
        const searchTerm = searchInput ? searchInput.value.toLowerCase().trim() : '';

        cards.forEach(card => {
            const matchesPlatform = !this.state.platform || card.dataset.platform === this.state.platform;
            const matchesStatus = !this.state.status || card.dataset.status === this.state.status;
            const matchesGuest = !this.state.guest || card.dataset.guestId === this.state.guest;  // NEW
            const matchesSearch = !searchTerm || card.textContent.toLowerCase().includes(searchTerm);

            card.style.display = (matchesPlatform && matchesStatus && matchesGuest && matchesSearch) ? 'flex' : 'none';
        });
    }

    /**
     * Update filter indicators - UPDATED
     */
    updateFilterIndicators() {
        const container = document.getElementById('activeFilters');
        const clearBtn = document.getElementById('clearFiltersBtn');

        if (!container) return;

        container.innerHTML = '';

        if (this.state.platform) {
            container.appendChild(this.createFilterBadge('platform', this.state.platform));
        }

        if (this.state.status) {
            container.appendChild(this.createFilterBadge('status', this.state.status));
        }

        // NEW: Add guest badge if filtered
        if (this.state.guest) {
            container.appendChild(this.createFilterBadge('guest', this.state.guest));
        }

        const hasActiveFilters = this.state.platform || this.state.status || this.state.guest;
        if (clearBtn) {
            clearBtn.style.display = hasActiveFilters ? 'inline-flex' : 'none';
        }
    }

    /**
     * Check if any filters are active - UPDATED
     */
    hasActiveFilters() {
        return !!(this.state.platform || this.state.status || this.state.guest);
    }

    /**
     * Reset all filters - UPDATED
     */
    reset() {
        this.state.platform = null;
        this.state.status = null;
        this.state.guest = null;  // NEW
        this.saveToURL();
        this.applyFilters();
        this.updateUI();
    }
}
```

### Pattern 2: Guest Dropdown HTML
**What:** HTML select element for guest filter
**When to use:** Filter bar in inbox
**Example:**
```html
<!-- Source: Standard HTML select with dynamic population -->
<div class="filter-bar">
    <!-- Existing platform and status filter groups... -->

    <!-- Guest Filter Dropdown -->
    <div class="filter-group guest-filter">
        <select id="guestFilter" class="guest-dropdown" aria-label="Filter by guest">
            <option value="">All Guests</option>
            <!-- Options populated dynamically via JavaScript -->
        </select>
    </div>

    <div class="search-box">...</div>
</div>
```

### Pattern 3: Populate Guest Dropdown
**What:** Fetch guests and populate dropdown on page load
**When to use:** Inbox initialization
**Example:**
```javascript
// Source: Standard pattern for dropdown population
async function populateGuestDropdown() {
    const dropdown = document.getElementById('guestFilter');
    if (!dropdown) return;

    try {
        const response = await fetch('/chatbot/api/guests');
        if (!response.ok) throw new Error('Failed to fetch guests');
        const data = await response.json();

        // Get conversation counts from DOM
        const guestCounts = getGuestConversationCounts();

        // Clear existing options except "All Guests"
        dropdown.innerHTML = '<option value="">All Guests</option>';

        // Add guest options with conversation counts
        data.guests.forEach(guest => {
            const option = document.createElement('option');
            option.value = guest.id;
            const count = guestCounts[guest.id] || 0;
            const displayName = guest.name || guest.email || 'Unknown Guest';
            option.textContent = `${displayName} (${count})`;
            dropdown.appendChild(option);
        });

        // Restore selection from URL if present
        if (filterState.state.guest) {
            dropdown.value = filterState.state.guest;
        }
    } catch (error) {
        console.error('Failed to populate guest dropdown:', error);
    }
}

/**
 * Count conversations per guest from DOM
 */
function getGuestConversationCounts() {
    const counts = {};
    document.querySelectorAll('.conversation-card').forEach(card => {
        const guestId = card.dataset.guestId;
        if (guestId) {
            counts[guestId] = (counts[guestId] || 0) + 1;
        }
    });
    return counts;
}
```

### Pattern 4: Data Attribute for Guest ID
**What:** Store guest ID on conversation card for fast client-side filtering
**When to use:** Conversation cards in inbox
**Example:**
```html
<!-- Source: Mirrors existing data-platform/data-status pattern -->
<a href="..." class="conversation-card"
   data-conversation-id="{{ conv.id }}"
   data-updated-at="{{ conv.updated_at.isoformat() if conv.updated_at else '' }}"
   data-platform="{{ conv.platform }}"
   data-status="{{ conv.status }}"
   data-guest-id="{{ conv.guest_id }}"
   data-is-read="{{ 'true' if conv.is_read else 'false' }}">
```

### Pattern 5: Guest Filter Badge
**What:** Display guest name in active filter badge
**When to use:** Active filter indicators
**Example:**
```javascript
// Source: Extension of existing badge pattern
formatFilterValue(type, value) {
    if (type === 'platform') {
        return value.charAt(0).toUpperCase() + value.slice(1);
    } else if (type === 'status') {
        return value.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
    } else if (type === 'guest') {
        // Look up guest name from dropdown
        const dropdown = document.getElementById('guestFilter');
        if (dropdown) {
            const option = dropdown.querySelector(`option[value="${value}"]`);
            if (option) {
                // Return just the name part (remove count)
                return option.textContent.replace(/\s*\(\d+\)$/, '');
            }
        }
        return `Guest #${value}`;
    }
    return value;
}
```

### Anti-Patterns to Avoid
- **Fetching guests on every filter change:** Fetch once on page load; guests rarely change during session
- **Not updating dropdown after polling:** Guest conversation counts may change; repopulate after poll updates
- **Storing guest name in URL:** Use guest ID for URL (stable); look up name for display
- **Large dropdown with hundreds of guests:** Consider autocomplete if guest count exceeds 50-100; for v1 with small dataset, dropdown is fine
- **Not syncing dropdown selection with URL:** Always restore dropdown value from `filterState.state.guest` on page load

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| URL state sync | Custom URL parsing | Existing FilterState module | Already handles platform/status; extend for guest |
| Filter combination | Separate filter functions | FilterState.applyFilters() | Single source of truth for visibility |
| Dropdown styling | Custom dropdown component | Native `<select>` with CSS | Simple, accessible, works everywhere |

**Key insight:** Phase 6 is an incremental extension of Phase 4's FilterState. The pattern is established; we're adding one more filter dimension (guest) using the exact same approach as platform and status.

## Common Pitfalls

### Pitfall 1: Guest Filter Not Applied After Polling
**What goes wrong:** New conversations appear, guest filter seems to reset
**Why it happens:** `updateInboxList()` adds new cards but doesn't reapply filters
**How to avoid:** `filterState.applyFilters()` is already called at end of updateInboxList() - ensure it checks guest filter too
**Warning signs:** Cards for other guests briefly appear after poll

### Pitfall 2: Dropdown Shows Stale Conversation Counts
**What goes wrong:** Dropdown shows "Maria (2)" but 3 conversations visible
**Why it happens:** Counts computed from DOM at page load, not updated after polling
**How to avoid:** Repopulate dropdown after polling update, or accept slight staleness
**Warning signs:** Count mismatch after new conversation arrives

### Pitfall 3: URL Has guest=X but Dropdown Shows "All Guests"
**What goes wrong:** Page loads with URL filter but dropdown not synced
**Why it happens:** Dropdown populated before FilterState restores URL state
**How to avoid:** Populate dropdown, then set `dropdown.value = filterState.state.guest` if present
**Warning signs:** URL shows filter but dropdown doesn't reflect it

### Pitfall 4: Guest Badge Shows ID Instead of Name
**What goes wrong:** Active filter shows "Guest #5" instead of "Maria Schmidt"
**Why it happens:** `formatFilterValue()` doesn't look up guest name
**How to avoid:** Look up name from dropdown option text or cache guest names
**Warning signs:** Cryptic badge display

### Pitfall 5: Missing data-guest-id on Dynamic Cards
**What goes wrong:** New cards from polling don't filter by guest
**Why it happens:** `createConversationCard()` not adding data-guest-id
**How to avoid:** Update JS card creation to include `card.dataset.guestId = conv.guest_id`
**Warning signs:** Dynamically created cards always visible regardless of guest filter

### Pitfall 6: Guest Not Found in Dropdown After Filter Clear
**What goes wrong:** Clear filters, guest dropdown stuck on old selection visually
**Why it happens:** `updateUI()` doesn't reset dropdown selection
**How to avoid:** In `updateUI()`, set `dropdown.value = this.state.guest || ''`
**Warning signs:** Dropdown shows filtered guest but all conversations visible

## Code Examples

Verified patterns from existing codebase:

### Adding data-guest-id to Jinja Template
```html
<!-- Source: templates/chatbot/inbox.html - extend existing data attributes -->
<a href="{{ url_for('chatbot.conversation_view', conversation_id=conv.id) }}"
   class="conversation-card{% if not conv.is_read %} unread{% endif %}"
   data-conversation-id="{{ conv.id }}"
   data-updated-at="{{ conv.updated_at.isoformat() if conv.updated_at else '' }}"
   data-platform="{{ conv.platform }}"
   data-status="{{ conv.status }}"
   data-guest-id="{{ conv.guest_id }}"
   data-is-read="{{ 'true' if conv.is_read else 'false' }}">
```

### Adding data-guestId to JavaScript Card Creation
```javascript
// Source: templates/chatbot/inbox.html createConversationCard() function
function createConversationCard(conv) {
    const card = document.createElement('a');
    card.href = `/chatbot/conversation/${conv.id}`;
    card.className = 'conversation-card' + (!conv.is_read ? ' unread' : '');
    card.dataset.conversationId = conv.id;
    card.dataset.updatedAt = conv.updated_at || '';
    card.dataset.platform = conv.platform;
    card.dataset.status = conv.status;
    card.dataset.guestId = conv.guest_id;  // ADD THIS
    card.dataset.isRead = conv.is_read ? 'true' : 'false';
    // ... rest of card creation
}
```

### Guest Dropdown Change Handler
```javascript
// Source: Event handler pattern from Phase 4
document.getElementById('guestFilter').addEventListener('change', function() {
    filterState.setGuest(this.value || null);
});
```

### Update UI to Sync Dropdown Selection
```javascript
// Source: Add to FilterState.updateUI() method
updateUI() {
    // Existing platform and status button updates...

    // Sync guest dropdown selection
    const guestDropdown = document.getElementById('guestFilter');
    if (guestDropdown) {
        guestDropdown.value = this.state.guest || '';
    }

    // Update active filter indicators
    this.updateFilterIndicators();
}
```

### Guest Dropdown CSS
```css
/* Source: Consistent with existing filter-group styling */
.guest-dropdown {
    padding: 8px 12px;
    border: none;
    background: transparent;
    border-radius: 6px;
    font-size: 0.875rem;
    cursor: pointer;
    color: var(--text-secondary);
    min-width: 150px;
}

.guest-dropdown:hover {
    color: var(--text-primary);
}

.guest-dropdown:focus {
    outline: none;
    color: var(--text-primary);
}

/* When a guest is selected (not "All Guests") */
.guest-dropdown.active {
    background: var(--primary-color);
    color: white;
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Separate filter functions | Unified FilterState class | Phase 4 | Single source of truth |
| Custom dropdown libraries | Native HTML select | Always | Simpler, more accessible |
| Server-side filtering only | Client-side with URL sync | Phase 4 | Faster UX for small datasets |

**Deprecated/outdated:**
- None relevant to this phase

## Open Questions

1. **Should guest dropdown update after polling?**
   - What we know: Guest list unlikely to change during session; conversation counts may change
   - What's unclear: Is stale count (e.g., "Maria (2)" when actually 3) confusing?
   - Recommendation: For v1, accept slight staleness. Repopulating adds complexity. Users can refresh page.

2. **Should API return conversation counts per guest?**
   - What we know: Current `/api/guests` returns guest info but no conversation count
   - What's unclear: Compute client-side from DOM or server-side?
   - Recommendation: Compute client-side from DOM on page load. Keeps API simple. If pagination added later, revisit.

3. **What if guest has no conversations (filtered out by platform/status)?**
   - What we know: Guest may have conversations but all hidden by other filters
   - What's unclear: Should dropdown show guests with 0 visible conversations?
   - Recommendation: Show all guests who have ANY conversations (count from full DOM, not filtered). Selecting a guest with 0 filtered results shows empty state - that's expected behavior.

## Sources

### Primary (HIGH confidence)
- **Existing codebase analysis:**
  - `static/js/filter-state.js` - FilterState module to extend
  - `templates/chatbot/inbox.html` - Platform/status filter patterns
  - `routes.py` - `/api/guests` endpoint
  - `models.py` - Conversation model with `guest_id` field
- **Phase 4 research and implementation** - FilterState patterns

### Secondary (MEDIUM confidence)
- MDN HTML select element - Standard behavior
- Existing CSS styles - Badge and filter styling patterns

### Tertiary (LOW confidence)
- N/A - All patterns verified against existing codebase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All native APIs and existing patterns
- Architecture: HIGH - Direct extension of Phase 4 FilterState
- Pitfalls: HIGH - Similar to platform/status filter pitfalls; well-understood

**Research date:** 2026-02-19
**Valid until:** 2026-03-19 (30 days - stable patterns)

## Implementation Notes for Planner

1. **Files to modify:**
   - `static/js/filter-state.js`:
     - Add `guest: null` to state
     - Add `setGuest()`, `clearGuest()` methods
     - Update `loadFromURL()`, `saveToURL()` for guest param
     - Update `applyFilters()` to check guest
     - Update `updateFilterIndicators()` for guest badge
     - Update `updateUI()` to sync dropdown selection
     - Update `reset()` to clear guest
     - Update `hasActiveFilters()` to include guest
     - Update `formatFilterValue()` for guest name lookup
   - `templates/chatbot/inbox.html`:
     - Add `data-guest-id="{{ conv.guest_id }}"` to Jinja card
     - Add guest dropdown to filter bar HTML
     - Add `card.dataset.guestId = conv.guest_id;` to `createConversationCard()`
     - Add `populateGuestDropdown()` function
     - Add dropdown change handler
     - Call `populateGuestDropdown()` on DOMContentLoaded
   - `static/css/style.css`:
     - Add `.guest-dropdown` styles
     - Add `.active-filter-badge.guest-*` styles (if needed)

2. **No backend changes required for v1:**
   - `/api/guests` already returns guest list
   - Conversation count computed client-side from DOM
   - Guest ID already in `Conversation.to_dict()` response

3. **Prior decisions to honor:**
   - [04-01]: history.replaceState over pushState - continue pattern
   - [04-01]: Singleton pattern for FilterState - extend, don't replace
   - [04-01]: Combined filter logic - add guest to existing combination
   - [04-02]: Empty string for 'All' data-filter-* value - use empty string for "All Guests" option value
   - [04-02]: Filters applied before polling starts - continue pattern

4. **Integration points:**
   - `filterState.applyFilters()` already called after polling - will automatically apply guest filter once added to state
   - Dropdown population should happen after FilterState initialization so URL state can restore selection
