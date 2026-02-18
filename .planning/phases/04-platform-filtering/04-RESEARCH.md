# Phase 4: Platform Filtering - Research

**Researched:** 2026-02-18
**Domain:** URL state management, filter UI patterns, JavaScript modules, Flask API integration
**Confidence:** HIGH

## Summary

Phase 4 implements platform filtering for the inbox with URL synchronization. Users will be able to filter conversations by platform (Email, WhatsApp, Airbnb, Booking), see active filter indicators, clear all filters with one click, and have filter state persist in the URL for sharing and browser navigation.

The implementation is straightforward because:
1. **Existing filter infrastructure** - The inbox already has a status filter bar with button styling (`filter-btn`, `filter-btn.active`)
2. **Existing data attributes** - Conversation cards already have `data-status` attribute used for client-side filtering; adding `data-platform` follows the same pattern
3. **API already supports filtering** - The `/api/conversations` endpoint already accepts query parameters and can be extended for platform filtering
4. **URL APIs are native** - `URLSearchParams` and `history.pushState/replaceState` are universally supported browser APIs

The key design decision is whether to filter client-side (fast, works with existing polling) or server-side (scales better). Given the target of 10-50 conversations and existing client-side status filtering, **client-side filtering with URL sync** is recommended. This matches the existing architecture and avoids API changes for v1.

**Primary recommendation:** Create a `FilterState` JavaScript module that manages filter state, syncs to/from URL, and applies DOM visibility. Platform filter UI mirrors existing status filter pattern.

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| FILT-01 | User can filter inbox by platform (Email, WhatsApp, Airbnb, Booking) | Platform filter button group mirroring existing status filter; client-side filtering via `data-platform` attribute; `filterConversations()` updated to check both status and platform |
| FILT-05 | User can see active filter indicators showing current filters | Active filter badges below filter bar showing current selections; CSS styling consistent with existing `.platform-badge` styles |
| FILT-06 | User can clear all filters with single click | "Clear All" button that resets all filter buttons to default state and updates URL; `FilterState.reset()` method |
| FILT-07 | User's filter selections persist in URL (bookmarkable, back-button works) | `URLSearchParams` for reading/writing `?platform=email&status=active`; `history.replaceState()` for non-navigational updates; `popstate` event handler for back/forward navigation |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Vanilla JavaScript | ES6+ | Filter logic, DOM manipulation, URL sync | Consistent with existing codebase; no framework needed |
| URLSearchParams | Native | Query string parsing and building | W3C standard; universal browser support |
| History API | Native | URL state management without reload | W3C standard; `pushState`/`replaceState`/`popstate` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| N/A | - | - | No additional libraries needed |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Client-side filtering | Server-side API filtering | Server-side scales better but adds API complexity; client-side works for 10-50 conversations |
| history.replaceState | history.pushState | pushState adds history entries for each filter change (clutter); replaceState better for filter state |
| Data attributes for filtering | CSS classes | Data attributes more explicit and queryable; classes can conflict with styling |
| URLSearchParams | Manual query string parsing | URLSearchParams is cleaner, handles encoding, and is native |

**Installation:**
```bash
# No installation required - all native APIs
```

## Architecture Patterns

### Recommended Project Structure
```
static/
├── js/
│   ├── app.js            # Existing utility functions
│   ├── polling.js        # Existing PollingManager class
│   └── filter-state.js   # NEW: FilterState module for URL sync and state management
templates/
└── chatbot/
    └── inbox.html        # Update: add platform filter UI, data-platform attributes
```

### Pattern 1: FilterState Module (Singleton)
**What:** ES6 module that encapsulates filter state, URL sync, and DOM operations
**When to use:** Any page requiring URL-synchronized filtering
**Example:**
```javascript
// Source: Best practices for URL-synced filter state
class FilterState {
    constructor() {
        this.state = {
            platform: null,  // null = all, or 'email'|'whatsapp'|'airbnb'|'booking'
            status: null     // null = all, or 'active'|'pending_owner'|'closed'
        };

        // Initialize from URL on construction
        this.loadFromURL();

        // Handle browser back/forward
        window.addEventListener('popstate', () => {
            this.loadFromURL();
            this.applyFilters();
            this.updateUI();
        });
    }

    loadFromURL() {
        const params = new URLSearchParams(window.location.search);
        this.state.platform = params.get('platform');
        this.state.status = params.get('status');
    }

    saveToURL() {
        const url = new URL(window.location.href);
        const params = url.searchParams;

        // Set or delete based on state
        if (this.state.platform) {
            params.set('platform', this.state.platform);
        } else {
            params.delete('platform');
        }

        if (this.state.status) {
            params.set('status', this.state.status);
        } else {
            params.delete('status');
        }

        // Use replaceState (no history entry for filter changes)
        history.replaceState({}, '', url.toString());
    }

    setPlatform(platform) {
        this.state.platform = platform || null;
        this.saveToURL();
        this.applyFilters();
        this.updateUI();
    }

    setStatus(status) {
        this.state.status = status || null;
        this.saveToURL();
        this.applyFilters();
        this.updateUI();
    }

    reset() {
        this.state = { platform: null, status: null };
        this.saveToURL();
        this.applyFilters();
        this.updateUI();
    }

    applyFilters() {
        const cards = document.querySelectorAll('.conversation-card');
        cards.forEach(card => {
            const matchesPlatform = !this.state.platform || card.dataset.platform === this.state.platform;
            const matchesStatus = !this.state.status || card.dataset.status === this.state.status;
            card.style.display = (matchesPlatform && matchesStatus) ? 'flex' : 'none';
        });
    }

    updateUI() {
        // Update platform filter buttons
        document.querySelectorAll('[data-filter-platform]').forEach(btn => {
            const btnPlatform = btn.dataset.filterPlatform || null;
            btn.classList.toggle('active', btnPlatform === (this.state.platform || null));
        });

        // Update status filter buttons
        document.querySelectorAll('[data-filter-status]').forEach(btn => {
            const btnStatus = btn.dataset.filterStatus || null;
            btn.classList.toggle('active', btnStatus === (this.state.status || null));
        });

        // Update active filter indicators
        this.updateFilterIndicators();
    }

    updateFilterIndicators() {
        const container = document.getElementById('activeFilters');
        if (!container) return;

        container.innerHTML = '';

        if (this.state.platform) {
            const badge = this.createFilterBadge('platform', this.state.platform);
            container.appendChild(badge);
        }

        if (this.state.status) {
            const badge = this.createFilterBadge('status', this.state.status);
            container.appendChild(badge);
        }

        // Show/hide "Clear All" button
        const clearBtn = document.getElementById('clearFiltersBtn');
        if (clearBtn) {
            clearBtn.style.display = (this.state.platform || this.state.status) ? 'inline-flex' : 'none';
        }
    }

    createFilterBadge(type, value) {
        const badge = document.createElement('span');
        badge.className = `active-filter-badge ${type}-${value}`;
        badge.innerHTML = `
            ${this.formatFilterValue(type, value)}
            <button onclick="filterState.clear${type.charAt(0).toUpperCase() + type.slice(1)}()" aria-label="Remove ${type} filter">
                <i class="fas fa-times"></i>
            </button>
        `;
        return badge;
    }

    formatFilterValue(type, value) {
        if (type === 'platform') {
            return value.charAt(0).toUpperCase() + value.slice(1);
        }
        if (type === 'status') {
            return value.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
        }
        return value;
    }

    clearPlatform() { this.setPlatform(null); }
    clearStatus() { this.setStatus(null); }
}

// Export singleton instance
const filterState = new FilterState();
```

### Pattern 2: Data Attribute for Platform
**What:** Store platform on conversation card for fast client-side filtering
**When to use:** Conversation cards in inbox
**Example:**
```html
<!-- Source: Mirrors existing data-status pattern from Phase 2 -->
<a href="..." class="conversation-card"
   data-conversation-id="{{ conv.id }}"
   data-updated-at="{{ conv.updated_at.isoformat() }}"
   data-platform="{{ conv.platform }}"
   data-status="{{ conv.status }}"
   data-is-read="{{ 'true' if conv.is_read else 'false' }}">
```

### Pattern 3: Platform Filter Button Group
**What:** Button group for selecting platform filter
**When to use:** Filter bar in inbox
**Example:**
```html
<!-- Source: Mirrors existing status filter pattern -->
<div class="filter-bar">
    <!-- Platform Filter Group -->
    <div class="filter-group" role="group" aria-label="Filter by platform">
        <button class="filter-btn active" data-filter-platform="">All Platforms</button>
        <button class="filter-btn" data-filter-platform="email">
            <i class="fas fa-envelope"></i> Email
        </button>
        <button class="filter-btn" data-filter-platform="whatsapp">
            <i class="fab fa-whatsapp"></i> WhatsApp
        </button>
        <button class="filter-btn" data-filter-platform="airbnb">
            <i class="fab fa-airbnb"></i> Airbnb
        </button>
        <button class="filter-btn" data-filter-platform="booking">
            <i class="fas fa-bed"></i> Booking
        </button>
    </div>

    <!-- Status Filter Group (existing) -->
    <div class="filter-group" role="group" aria-label="Filter by status">
        <button class="filter-btn active" data-filter-status="">All</button>
        <button class="filter-btn" data-filter-status="active">Active</button>
        <button class="filter-btn" data-filter-status="pending_owner">Pending</button>
        <button class="filter-btn" data-filter-status="closed">Closed</button>
    </div>

    <div class="search-box">...</div>
</div>

<!-- Active Filter Indicators -->
<div id="activeFilters" class="active-filters"></div>

<!-- Clear All Button -->
<button id="clearFiltersBtn" class="btn btn-secondary btn-sm" style="display: none;" onclick="filterState.reset()">
    <i class="fas fa-times"></i> Clear All Filters
</button>
```

### Pattern 4: URL Sync with replaceState
**What:** Update URL query parameters without creating history entries
**When to use:** Filter changes that shouldn't clutter browser history
**Example:**
```javascript
// Source: MDN History API documentation
// https://developer.mozilla.org/en-US/docs/Web/API/History/replaceState

function updateURL(filters) {
    const url = new URL(window.location.href);

    // Set or delete platform parameter
    if (filters.platform) {
        url.searchParams.set('platform', filters.platform);
    } else {
        url.searchParams.delete('platform');
    }

    // Replace without creating history entry
    history.replaceState({}, '', url.toString());
}
```

### Pattern 5: popstate Handler for Back/Forward
**What:** Listen for browser navigation and restore filter state
**When to use:** Always, to support back/forward buttons
**Example:**
```javascript
// Source: MDN popstate event documentation
// https://developer.mozilla.org/en-US/docs/Web/API/Window/popstate_event

window.addEventListener('popstate', (event) => {
    // Re-read filters from URL
    const params = new URLSearchParams(window.location.search);
    const platform = params.get('platform');
    const status = params.get('status');

    // Update state and UI
    filterState.state = { platform, status };
    filterState.applyFilters();
    filterState.updateUI();
});
```

### Anti-Patterns to Avoid
- **history.pushState for filter changes:** Creates excessive history entries; user has to click back many times. Use replaceState instead.
- **Encoding filters in hash (#platform=email):** Non-standard for filtering; query parameters are conventional. Hash is for in-page anchors.
- **Server-side filtering without client-side fallback:** Slower UX; requires API round-trip. Keep client-side for small datasets.
- **Not handling popstate:** Back button won't work correctly; frustrating for users expecting normal browser behavior.
- **Hardcoded filter values in JavaScript:** Use data attributes from HTML so adding platforms doesn't require JS changes.
- **Forgetting to re-apply filters after polling:** Polling updates may reset visibility; always call `filterState.applyFilters()` in `updateInboxList()`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Query string parsing | Regex or manual split | `URLSearchParams` | Native, handles encoding, full API |
| URL updates without reload | Setting `window.location` | `history.replaceState()` | Avoids page reload, doesn't add history |
| Back button handling | Manual history tracking | `popstate` event | Native browser integration |
| Filter button toggle | Custom state tracking | CSS class `.active` + data attributes | Simpler, visible in DOM, matches existing |

**Key insight:** The existing status filter in inbox.html already uses the pattern of `filter-btn.active` + `data-filter` attributes. Platform filtering should follow the exact same pattern for consistency.

## Common Pitfalls

### Pitfall 1: Filters Reset After Polling
**What goes wrong:** New conversations from polling appear unfiltered; existing filter visibility lost
**Why it happens:** `updateInboxList()` doesn't call filter after DOM update
**How to avoid:** Call `filterState.applyFilters()` at the end of `updateInboxList()`
**Warning signs:** All conversations briefly visible after poll interval

### Pitfall 2: URL Not Updated on Filter Click
**What goes wrong:** User filters, copies URL, URL doesn't include filter state
**Why it happens:** Forgetting to call `saveToURL()` after filter change
**How to avoid:** Every filter mutation must trigger URL sync
**Warning signs:** Shared URLs don't reproduce filter state

### Pitfall 3: Back Button Doesn't Restore Filters
**What goes wrong:** User navigates away, clicks back, filters not applied
**Why it happens:** No `popstate` event handler
**How to avoid:** Initialize FilterState with popstate listener that calls loadFromURL + applyFilters + updateUI
**Warning signs:** Back button shows wrong filter state

### Pitfall 4: Initial Page Load Ignores URL Parameters
**What goes wrong:** User visits `/chatbot/?platform=email` but all conversations shown
**Why it happens:** Not calling `loadFromURL()` on FilterState construction
**How to avoid:** Constructor should read URL and apply filters before page renders
**Warning signs:** Refresh doesn't preserve filter state

### Pitfall 5: Race Condition Between Filter and Polling Init
**What goes wrong:** Polling fetch completes before filters initialized; wrong visibility
**Why it happens:** Polling starts on DOMContentLoaded but FilterState initialized later
**How to avoid:** Initialize FilterState BEFORE starting polling; apply filters after each poll
**Warning signs:** Brief flash of unfiltered content on page load

### Pitfall 6: Missing data-platform Attribute
**What goes wrong:** Filter doesn't work; all cards hidden or shown
**Why it happens:** `createConversationCard()` not adding data-platform attribute
**How to avoid:** Update both Jinja template AND JavaScript card creation to include `data-platform`
**Warning signs:** Dynamically created cards don't filter correctly

### Pitfall 7: Search and Filter Conflict
**What goes wrong:** Search hides cards, filter shows them (or vice versa)
**Why it happens:** Search and filter both manipulate `style.display` independently
**How to avoid:** Unified filtering: card visible only if (matchesFilter AND matchesSearch)
**Warning signs:** Strange behavior when using both search and filter

## Code Examples

Verified patterns from official sources:

### URL Parameter Management
```javascript
// Source: MDN URLSearchParams
// https://developer.mozilla.org/en-US/docs/Web/API/URLSearchParams

// Read from current URL
const url = new URL(window.location.href);
const platform = url.searchParams.get('platform'); // 'email' or null

// Set parameter
url.searchParams.set('platform', 'whatsapp');

// Delete parameter
url.searchParams.delete('platform');

// Build query string
url.searchParams.toString(); // 'platform=whatsapp&status=active'
```

### History API Usage
```javascript
// Source: MDN History API
// https://developer.mozilla.org/en-US/docs/Web/API/History_API

// Update URL without navigation (filter changes)
const url = new URL(window.location.href);
url.searchParams.set('platform', 'email');
history.replaceState({}, '', url.toString());

// Listen for back/forward navigation
window.addEventListener('popstate', (event) => {
    const params = new URLSearchParams(window.location.search);
    applyFiltersFromParams(params);
});
```

### Combined Filter Function
```javascript
// Source: Pattern from existing status filtering in inbox.html
function applyAllFilters() {
    const cards = document.querySelectorAll('.conversation-card');
    const searchQuery = document.getElementById('searchInput')?.value.toLowerCase() || '';

    cards.forEach(card => {
        // Check platform filter
        const platform = filterState.state.platform;
        const matchesPlatform = !platform || card.dataset.platform === platform;

        // Check status filter
        const status = filterState.state.status;
        const matchesStatus = !status || card.dataset.status === status;

        // Check search
        const text = card.textContent.toLowerCase();
        const matchesSearch = !searchQuery || text.includes(searchQuery);

        // Card visible only if ALL conditions pass
        card.style.display = (matchesPlatform && matchesStatus && matchesSearch) ? 'flex' : 'none';
    });
}
```

### Active Filter Badge CSS
```css
/* Source: Consistent with existing badge styling */
.active-filters {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-bottom: 12px;
}

.active-filter-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 500;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
}

.active-filter-badge button {
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
    color: var(--text-light);
    display: flex;
    align-items: center;
}

.active-filter-badge button:hover {
    color: var(--danger-color);
}

/* Platform-specific badge colors */
.active-filter-badge.platform-email { background: #fce8e6; color: var(--email-color); border-color: #fcd5d2; }
.active-filter-badge.platform-whatsapp { background: #e6f7ed; color: var(--whatsapp-color); border-color: #c3e8d0; }
.active-filter-badge.platform-airbnb { background: #ffe6e6; color: var(--airbnb-color); border-color: #fcd0d0; }
.active-filter-badge.platform-booking { background: #e6eef7; color: var(--booking-color); border-color: #c5d9ed; }
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hash-based routing (#filter=email) | Query parameters (?platform=email) | Modern SPA era | Query params are standard; hash for anchors only |
| Manual query string parsing | URLSearchParams | ES6 (2015) | Native API, handles encoding |
| window.location for state | History API | HTML5 (2014) | No page reload, proper navigation |
| Reload-based filtering | Client-side DOM visibility | SPA patterns | Faster UX, works with polling |

**Deprecated/outdated:**
- Using location.hash for filter state: Conflicts with potential anchor navigation
- Manual query string building with string concatenation: URLSearchParams handles edge cases

## Open Questions

1. **Should platform filter use pushState or replaceState?**
   - What we know: replaceState doesn't create history entries; pushState does
   - What's unclear: Does user expect back button to undo filter changes?
   - Recommendation: Use `replaceState` for filter changes (less clutter); `pushState` would require clicking back many times to leave page

2. **Should "All Platforms" button exist or use no-selection for all?**
   - What we know: Current status filter has explicit "All" button
   - What's unclear: Is explicit "All" clearer than no selection?
   - Recommendation: Follow existing pattern - explicit "All Platforms" button for consistency

3. **Should filter indicator badges be clickable?**
   - What we know: Design shows badges with "x" to remove individual filters
   - What's unclear: Should clicking the badge itself do anything?
   - Recommendation: Badge shows current filter; "x" removes that filter. Badge click could toggle off (same as clicking "All") but may be confusing - keep simple.

## Sources

### Primary (HIGH confidence)
- [MDN URLSearchParams](https://developer.mozilla.org/en-US/docs/Web/API/URLSearchParams) - Query string API
- [MDN History.replaceState()](https://developer.mozilla.org/en-US/docs/Web/API/History/replaceState) - URL updates without reload
- [MDN popstate event](https://developer.mozilla.org/en-US/docs/Web/API/Window/popstate_event) - Back/forward handling
- Existing codebase analysis: `inbox.html` (status filter pattern), `polling.js` (integration point)

### Secondary (MEDIUM confidence)
- [MDN URL interface](https://developer.mozilla.org/en-US/docs/Web/API/URL) - URL construction and manipulation
- Existing `style.css` - Badge styling patterns for consistency

### Tertiary (LOW confidence)
- N/A - All patterns verified against official sources or existing codebase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All native browser APIs; no external dependencies
- Architecture: HIGH - Extends existing filter pattern; minimal new patterns
- Pitfalls: HIGH - URL state sync is well-understood domain; issues are predictable
- Integration: HIGH - Existing polling infrastructure already reapplies filters after update

**Research date:** 2026-02-18
**Valid until:** 2026-03-18 (30 days - stable APIs, unlikely to change)

## Implementation Notes for Planner

1. **Existing infrastructure to leverage:**
   - `static/js/polling.js` - PollingManager class (no changes needed)
   - `templates/chatbot/inbox.html` - Status filter pattern to mirror
   - `static/css/style.css` - Platform badge colors already defined

2. **Required changes:**
   - Create `static/js/filter-state.js` - FilterState module
   - Update `templates/chatbot/inbox.html`:
     - Add `data-platform` attribute to Jinja conversation cards
     - Add platform filter button group
     - Add active filter indicators container
     - Add "Clear All" button
     - Update `createConversationCard()` to include `data-platform`
     - Update `updateInboxList()` to call `filterState.applyFilters()`
     - Replace inline `filterConversations()` with FilterState methods
     - Initialize FilterState before polling starts
   - Update `static/css/style.css`:
     - Add active filter badge styles

3. **No backend changes required:**
   - Client-side filtering sufficient for 10-50 conversations
   - Conversation `to_dict()` already includes `platform` field
   - Polling API already returns platform data

4. **Integration with existing filter behavior:**
   - Replace current inline `filterConversations()` with FilterState
   - Unify status filter and platform filter in single state manager
   - Search filter also integrated into combined filter logic

5. **Prior decisions from earlier phases (MUST honor):**
   - [02-01]: Recursive setTimeout over setInterval - PollingManager unchanged
   - [02-02]: Added `data-status` attribute - now adding `data-platform` using same pattern
   - [02-02]: XSS prevention with `escapeHtml()` - continue using
   - [02-02]: Filter and search reapplied after each polling update - FilterState.applyFilters() called in updateInboxList()
