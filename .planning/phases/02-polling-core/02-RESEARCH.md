# Phase 2: Polling Core - Research

**Researched:** 2026-02-18
**Domain:** JavaScript polling, Page Visibility API, Flask JSON APIs
**Confidence:** HIGH

## Summary

Phase 2 implements automatic inbox and conversation updates via polling. The existing codebase already has JSON API endpoints (`/api/conversations` and `/api/conversations/<id>/messages`) that return the data needed for polling. The challenge is creating a reusable PollingManager JavaScript module that handles polling intervals, visibility-aware pause/resume, and efficient DOM updates.

The research confirms that:
1. **Page Visibility API** is universally supported (since July 2015) and is the standard way to detect tab hidden/visible state
2. **Recursive setTimeout is preferred over setInterval** for polling async operations to prevent call stacking
3. **AbortController** should be used to cancel in-flight fetch requests when stopping polls or navigating away
4. The existing Flask API endpoints already support the data format needed; minimal backend changes required

**Primary recommendation:** Create a self-contained `PollingManager` ES6 class that encapsulates polling logic with Page Visibility API integration, making it reusable across inbox and conversation views.

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| POLL-01 | Inbox auto-refreshes via polling every 10-30 seconds | PollingManager class with configurable interval; existing `/api/conversations` endpoint returns conversation list with `updated_at` timestamps |
| POLL-02 | Conversation view auto-refreshes for new messages | Same PollingManager with different endpoint; existing `/api/conversations/<id>/messages` endpoint returns all messages; can filter new messages by comparing IDs |
| POLL-03 | Polling pauses when browser tab is hidden (Visibility API) | Page Visibility API via `document.visibilityState` and `visibilitychange` event; HIGH confidence - universally supported |
| POLL-04 | Polling resumes and forces refresh when tab becomes visible | `visibilitychange` event listener triggers immediate poll + restart interval |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Vanilla JavaScript | ES6+ | Polling logic, DOM manipulation | No framework dependencies; existing codebase uses vanilla JS |
| Page Visibility API | Native | Tab visibility detection | W3C standard since 2015; universal browser support |
| Fetch API | Native | HTTP requests | Already used in existing `app.js`; no external dependencies |
| AbortController | Native | Cancel in-flight requests | Prevents memory leaks; allows clean polling stop |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| N/A | - | - | No additional libraries needed |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Polling | WebSocket (Socket.IO) | WebSocket is more efficient but adds complexity; polling sufficient for 10-50 conversations per prior decision |
| setInterval | setInterval | Simpler but can stack calls if API is slow; recursive setTimeout safer |
| Custom visibility detection | focus/blur events | focus/blur fires when switching windows, not just tabs; Visibility API is more accurate |

**Installation:**
```bash
# No installation required - all native APIs
```

## Architecture Patterns

### Recommended Project Structure
```
static/
├── js/
│   ├── app.js           # Existing utility functions (apiRequest, etc.)
│   ├── polling.js       # NEW: PollingManager class
│   └── inbox.js         # NEW: Inbox-specific polling integration
templates/
└── chatbot/
    ├── inbox.html       # Add polling initialization
    └── conversation.html # Add polling initialization
```

### Pattern 1: PollingManager Class
**What:** ES6 class encapsulating polling state and behavior
**When to use:** Any view that needs periodic data refresh
**Example:**
```javascript
// Source: Synthesized from MDN Page Visibility API + polling best practices
class PollingManager {
    constructor(options) {
        this.fetchFn = options.fetchFn;        // Async function that fetches data
        this.onUpdate = options.onUpdate;       // Callback when new data received
        this.interval = options.interval || 15000;  // Default 15s
        this.timeoutId = null;
        this.abortController = null;
        this.isPolling = false;

        // Bind visibility handler
        this._onVisibilityChange = this._onVisibilityChange.bind(this);
    }

    start() {
        if (this.isPolling) return;
        this.isPolling = true;
        document.addEventListener('visibilitychange', this._onVisibilityChange);
        this._poll(); // Immediate first poll
    }

    stop() {
        this.isPolling = false;
        document.removeEventListener('visibilitychange', this._onVisibilityChange);
        this._cancelPending();
    }

    _poll() {
        if (!this.isPolling || document.visibilityState === 'hidden') return;

        // Cancel any in-flight request
        if (this.abortController) {
            this.abortController.abort();
        }
        this.abortController = new AbortController();

        this.fetchFn(this.abortController.signal)
            .then(data => {
                if (this.isPolling) {
                    this.onUpdate(data);
                    this._scheduleNext();
                }
            })
            .catch(err => {
                if (err.name !== 'AbortError' && this.isPolling) {
                    console.error('Polling error:', err);
                    this._scheduleNext();
                }
            });
    }

    _scheduleNext() {
        this._cancelPending();
        this.timeoutId = setTimeout(() => this._poll(), this.interval);
    }

    _cancelPending() {
        if (this.timeoutId) {
            clearTimeout(this.timeoutId);
            this.timeoutId = null;
        }
        if (this.abortController) {
            this.abortController.abort();
            this.abortController = null;
        }
    }

    _onVisibilityChange() {
        if (document.visibilityState === 'visible') {
            this._poll(); // Immediate poll on return
        } else {
            this._cancelPending(); // Stop polling when hidden
        }
    }
}
```

### Pattern 2: Incremental DOM Updates
**What:** Update only changed elements instead of full page refresh
**When to use:** When polling returns data that may be unchanged
**Example:**
```javascript
// Source: Best practice for polling DOM updates
function updateInboxList(conversations, container) {
    const existingIds = new Set(
        [...container.querySelectorAll('[data-conversation-id]')]
            .map(el => el.dataset.conversationId)
    );

    conversations.forEach(conv => {
        const existing = container.querySelector(`[data-conversation-id="${conv.id}"]`);
        if (existing) {
            // Update existing card (preview, time, status)
            updateConversationCard(existing, conv);
        } else {
            // Insert new card at top (newest first)
            const newCard = createConversationCard(conv);
            container.prepend(newCard);
        }
    });

    // Optionally remove cards no longer in response
    // (careful with pagination - may not want this)
}
```

### Pattern 3: Fetch with AbortController
**What:** Pass AbortController signal to fetch for cancellation
**When to use:** All polling fetch calls
**Example:**
```javascript
// Source: MDN AbortController documentation
async function fetchConversations(signal) {
    const response = await fetch('/chatbot/api/conversations', { signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
}

// Usage in PollingManager
const poller = new PollingManager({
    fetchFn: fetchConversations,
    onUpdate: updateInbox,
    interval: 15000
});
```

### Anti-Patterns to Avoid
- **setInterval for async polling:** Can stack calls if API response is slow; use recursive setTimeout instead
- **Polling without visibility check:** Wastes bandwidth and server resources when tab is hidden
- **Full DOM replacement on every poll:** Causes flicker and loses scroll position; use incremental updates
- **No AbortController:** Memory leaks from abandoned fetch requests; always cancel on stop/visibility change
- **Hardcoded intervals:** Should be configurable for different views (inbox vs conversation may have different needs)

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Tab visibility detection | Custom focus/blur logic | Page Visibility API (`document.visibilityState`) | focus/blur fires incorrectly; Visibility API is the standard |
| Request cancellation | Custom timeout logic | AbortController | Native API, works with fetch, prevents memory leaks |
| Time formatting | Custom date formatting | `toLocaleString()` or existing `formatRelativeTime()` | Already exists in app.js |
| API requests | Raw XMLHttpRequest | Existing `apiRequest()` from app.js | Already handles JSON, error handling |

**Key insight:** The existing codebase already has utility functions (`apiRequest`, `formatRelativeTime`, `showNotification`). Build on these rather than creating parallel implementations.

## Common Pitfalls

### Pitfall 1: setInterval Call Stacking
**What goes wrong:** If the API takes 2 seconds to respond but interval is 1 second, calls queue up
**Why it happens:** setInterval schedules the next call regardless of whether the previous completed
**How to avoid:** Use recursive setTimeout that only schedules next call after current completes
**Warning signs:** Multiple simultaneous requests visible in network tab; increasing memory usage

### Pitfall 2: Polling in Hidden Tabs
**What goes wrong:** Unnecessary network requests when user isn't looking; wasted server resources
**Why it happens:** Forgetting to check visibility state before polling
**How to avoid:** Check `document.visibilityState !== 'hidden'` before each poll; stop on visibilitychange
**Warning signs:** Network requests continue when tab is in background (check DevTools)

### Pitfall 3: Memory Leaks from Abandoned Requests
**What goes wrong:** Fetch promises keep references to callbacks even after component unmounts
**Why it happens:** Not aborting in-flight requests when stopping polling or navigating away
**How to avoid:** Use AbortController; call `abort()` in stop() and before new requests
**Warning signs:** Growing memory usage over time; "Can't perform state update on unmounted component" errors

### Pitfall 4: DOM Flicker on Full Replacement
**What goes wrong:** Scroll position lost; visual flicker; poor user experience
**Why it happens:** Replacing entire container innerHTML instead of updating individual elements
**How to avoid:** Diff current DOM with new data; update only changed elements
**Warning signs:** Page jumps to top on poll; visible blink when data refreshes

### Pitfall 5: Not Resuming After Tab Return
**What goes wrong:** User returns to tab but data is stale; requires manual refresh
**Why it happens:** Only stopping polling on hide, not restarting on visible
**How to avoid:** Both pause on hidden AND immediate poll + restart on visible
**Warning signs:** Data doesn't update after switching back to tab

### Pitfall 6: AbortController Reuse
**What goes wrong:** Request cancellation stops working after first abort
**Why it happens:** AbortController can only abort once; stays in aborted state permanently
**How to avoid:** Create new AbortController for each request
**Warning signs:** Requests not canceling; memory leaks

## Code Examples

Verified patterns from official sources:

### Page Visibility API Detection
```javascript
// Source: MDN Page Visibility API
// https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API

document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
        console.log('Tab is now visible - resume polling');
        poller.start();
    } else {
        console.log('Tab is now hidden - pause polling');
        poller.stop();
    }
});
```

### Recursive setTimeout Polling
```javascript
// Source: JavaScript polling best practices
// https://davidwalsh.name/javascript-polling

function pollWithTimeout(fn, interval) {
    let timeoutId = null;
    let isActive = true;

    async function poll() {
        if (!isActive) return;

        try {
            await fn();
        } catch (err) {
            console.error('Poll error:', err);
        }

        if (isActive) {
            timeoutId = setTimeout(poll, interval);
        }
    }

    poll(); // Start immediately

    return {
        stop() {
            isActive = false;
            if (timeoutId) clearTimeout(timeoutId);
        }
    };
}
```

### Fetch with AbortController
```javascript
// Source: MDN Fetch API / AbortController
// https://developer.mozilla.org/en-US/docs/Web/API/AbortController

async function fetchWithCancel(url, signal) {
    try {
        const response = await fetch(url, { signal });
        if (!response.ok) {
            throw new Error(`HTTP error: ${response.status}`);
        }
        return await response.json();
    } catch (err) {
        if (err.name === 'AbortError') {
            console.log('Fetch was cancelled');
            return null; // Don't treat as error
        }
        throw err; // Re-throw actual errors
    }
}
```

### Efficient Inbox Update (New Messages Only)
```javascript
// Source: Best practice for chat/inbox polling

function updateInboxWithNewData(newConversations) {
    const container = document.getElementById('conversationList');
    const existingMap = new Map();

    container.querySelectorAll('[data-conversation-id]').forEach(el => {
        existingMap.set(el.dataset.conversationId, el);
    });

    newConversations.forEach((conv, index) => {
        const id = String(conv.id);
        const existing = existingMap.get(id);

        if (existing) {
            // Update if changed (compare updated_at)
            if (existing.dataset.updatedAt !== conv.updated_at) {
                updateCardContent(existing, conv);
                existing.dataset.updatedAt = conv.updated_at;
            }
            // Move to correct position if needed
            if (container.children[index] !== existing) {
                container.insertBefore(existing, container.children[index]);
            }
        } else {
            // New conversation - insert at correct position
            const newCard = createConversationCard(conv);
            container.insertBefore(newCard, container.children[index]);
        }
    });
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| jQuery AJAX | Native fetch API | ES6 (2015) | No jQuery dependency needed |
| `document.hidden` (boolean) | `document.visibilityState` (string) | Still both valid | visibilityState provides more information |
| Vendor-prefixed visibility | Unprefixed standard | 2015+ | No need for webkit/moz prefixes anymore |
| XMLHttpRequest | Fetch + AbortController | 2017+ | Cleaner API, native cancellation |

**Deprecated/outdated:**
- `webkitHidden`, `mozHidden`: Vendor prefixes no longer needed; use standard API
- `$.ajax()`: Flask docs mark jQuery AJAX as obsolete; use native fetch
- `document.webkitVisibilityState`: Use standard `document.visibilityState`

## Open Questions

1. **Message ID tracking for conversation polling**
   - What we know: Current `/api/conversations/<id>/messages` returns all messages
   - What's unclear: Should we track last seen message ID and only fetch new ones?
   - Recommendation: For v1, fetch all messages and compare client-side (simpler); optimize with `?since_id=` parameter in Phase 3 if needed

2. **Error retry strategy**
   - What we know: Network errors will happen; exponential backoff is standard
   - What's unclear: How aggressive should retry be? Should we show user notification?
   - Recommendation: Simple retry with same interval (10-30s is already conservative); show subtle indicator if 3+ consecutive failures

3. **Multiple pollers on same page**
   - What we know: Conversation page could poll both messages and guest profile updates
   - What's unclear: Should there be a single coordinator or independent pollers?
   - Recommendation: Independent pollers are simpler; both pause/resume on visibility change naturally

## Sources

### Primary (HIGH confidence)
- [MDN Page Visibility API](https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API) - Visibility detection, events, states
- [MDN document.visibilityState](https://developer.mozilla.org/en-US/docs/Web/API/Document/visibilityState) - Property details and values
- [MDN AbortController](https://developer.mozilla.org/en-US/docs/Web/API/AbortController/abort) - Request cancellation

### Secondary (MEDIUM confidence)
- [David Walsh - JavaScript Polling](https://davidwalsh.name/javascript-polling) - Promise-based polling patterns (verified against MDN)
- [OpenReplay - Three Ways of Polling](https://blog.openreplay.com/forever-functional-three-ways-of-polling/) - Comparison of polling approaches
- [Ben Nadel - Canceling Fetch with AbortController](https://www.bennadel.com/blog/4180-canceling-api-requests-using-fetch-and-abortcontroller-in-javascript.htm) - AbortController patterns

### Tertiary (LOW confidence)
- [Medium - setInterval vs setTimeout](https://fadamakis.com/polling-with-setinterval-vs-settimeout-in-javascript-c20caadee1cb) - Comparison article (inaccessible but claims verified via other sources)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All native browser APIs, universally supported since 2015+
- Architecture: HIGH - PollingManager pattern is well-established; existing codebase provides foundation
- Pitfalls: HIGH - Memory leaks and call stacking are well-documented; MDN provides clear guidance
- DOM updates: MEDIUM - Incremental update pattern is best practice but implementation details vary by use case

**Research date:** 2026-02-18
**Valid until:** 2026-03-18 (30 days - stable APIs, unlikely to change)

## Implementation Notes for Planner

1. **API endpoints already exist** - No backend changes needed for basic polling:
   - `GET /chatbot/api/conversations` - Returns paginated conversation list with `to_dict()` format
   - `GET /chatbot/api/conversations/<id>/messages` - Returns all messages for a conversation

2. **Existing infrastructure to leverage:**
   - `static/js/app.js` has `apiRequest()`, `showNotification()`, `formatRelativeTime()`
   - Templates already have `{% block extra_js %}` for page-specific scripts
   - Conversation list items use `conversation.updated_at` which can be compared

3. **File structure recommendation:**
   - Create `static/js/polling.js` for reusable PollingManager class
   - Inline polling initialization in template `{% block extra_js %}` for page-specific config
   - This avoids creating multiple small files while keeping PollingManager reusable

4. **Data attributes for DOM updates:**
   - Add `data-conversation-id` and `data-updated-at` to conversation cards
   - Add `data-message-id` to message elements
   - These enable efficient incremental updates without full DOM replacement
