# Pitfalls Research

**Domain:** Dashboard UI Enhancements (Polling, Filtering, Search, CRUD) for Flask Messaging App
**Researched:** 2026-02-17
**Confidence:** HIGH (verified across multiple authoritative sources)

## Critical Pitfalls

### Pitfall 1: Polling Memory Leaks and Timer Accumulation

**What goes wrong:**
JavaScript `setInterval` timers accumulate when users navigate between pages without proper cleanup. Each page visit creates a new polling interval while old ones continue running. Over time, this causes exponential API calls, memory consumption, and eventually browser crashes.

**Why it happens:**
In multi-page Flask apps with Jinja templates, JavaScript is typically inline or page-specific. When users navigate via traditional links (not SPA routing), old page scripts should be garbage collected, but timer references can persist if not explicitly cleared. The existing ChatBotAI codebase uses inline `<script>` tags without centralized timer management.

**How to avoid:**
1. Store interval IDs in a single global object (`window.chatbotTimers = {}`)
2. Clear ALL timers on `beforeunload` event
3. Use `setTimeout` chains instead of `setInterval` for polling (self-correcting)
4. Add visibility API check - pause polling when tab is hidden

```javascript
// Pattern: Self-clearing timeout chain
function pollConversations() {
    if (document.hidden) {
        window.pollTimeoutId = setTimeout(pollConversations, 30000);
        return;
    }

    fetch('/chatbot/api/conversations')
        .then(response => response.json())
        .then(data => {
            updateUI(data);
            window.pollTimeoutId = setTimeout(pollConversations, 10000);
        })
        .catch(err => {
            console.error('Poll failed:', err);
            // Exponential backoff on error
            window.pollTimeoutId = setTimeout(pollConversations, 30000);
        });
}

// Clean up on page leave
window.addEventListener('beforeunload', () => {
    clearTimeout(window.pollTimeoutId);
});
```

**Warning signs:**
- Network tab shows increasing request frequency over time
- Memory usage climbs steadily in DevTools Performance monitor
- "Maximum call stack exceeded" errors in console
- Browser tab becomes sluggish after extended use

**Phase to address:**
Phase 1 (Polling Infrastructure) - Build the timer management system before any polling features.

---

### Pitfall 2: Background Tab Throttling Breaking Polling

**What goes wrong:**
Chrome throttles `setInterval` to once per minute when tabs are inactive. Firefox and Safari have similar behaviors. Users expect real-time updates but see stale data when they return to the tab. Badge counts become incorrect.

**Why it happens:**
Modern browsers aggressively throttle background tabs to save battery and CPU. This is intentional browser behavior, not a bug. The existing ChatBotAI refresh button (`refreshConversations()`) uses `location.reload()` which works but provides poor UX.

**How to avoid:**
1. Use Page Visibility API to detect tab state changes
2. Force full refresh when tab becomes visible after being hidden
3. Store "last poll timestamp" and check staleness on visibility change
4. Consider a Service Worker for critical notifications (advanced)

```javascript
let lastPollTime = Date.now();
const STALE_THRESHOLD = 60000; // 1 minute

document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
        const timeSinceLastPoll = Date.now() - lastPollTime;
        if (timeSinceLastPoll > STALE_THRESHOLD) {
            // Data is stale, force immediate refresh
            pollConversationsNow();
        }
    }
});
```

**Warning signs:**
- Users report "messages don't show up until I refresh"
- Badge counts are wrong after switching tabs
- QA tests pass when tab is focused, fail when tab is backgrounded

**Phase to address:**
Phase 1 (Polling Infrastructure) - This is fundamental to polling reliability.

---

### Pitfall 3: N+1 Queries in Paginated Conversation Lists

**What goes wrong:**
Loading a page of 20 conversations triggers 21 database queries: 1 for conversations + 20 individual queries for `guest.name` or `last_message.content`. Page load becomes unbearably slow as conversation count grows.

**Why it happens:**
SQLAlchemy lazy loading. The existing code in `routes.py` does `Conversation.query.order_by(...)` but accessing `conv.guest.name` or `conv.last_message` in templates triggers additional queries. The template `inbox.html` accesses `conv.guest.name`, `conv.guest.email`, `conv.last_message.content`, and `conv.status`.

**How to avoid:**
1. Use `joinedload()` or `selectinload()` for relationships accessed in lists
2. Add a `last_message` relationship with `uselist=False` and eager loading
3. Profile queries with Flask-DebugToolbar or SQLAlchemy echo

```python
# Bad - current pattern (N+1)
conversations = Conversation.query.order_by(Conversation.updated_at.desc()).all()

# Good - eager load relationships
from sqlalchemy.orm import joinedload, selectinload

conversations = Conversation.query.options(
    joinedload(Conversation.guest),
    selectinload(Conversation.messages.limit(1))  # For last message
).order_by(Conversation.updated_at.desc()).all()
```

**Warning signs:**
- SQLAlchemy query count in debug toolbar shows 20+ queries per page
- Page load time increases linearly with conversation count
- Database CPU spikes during inbox loads

**Phase to address:**
Phase 2 (Filtering/Search) - When building the API endpoints that return conversation lists.

---

### Pitfall 4: COUNT(*) Pagination Performance Cliff

**What goes wrong:**
Flask-SQLAlchemy's `paginate()` method internally calls `query.count()`, which becomes catastrophically slow on large tables. With 100k+ messages, the count alone can take 3+ minutes on SQLite.

**Why it happens:**
SQLite (and PostgreSQL without proper indexes) must scan the entire table to count rows. The existing codebase uses SQLite (`instance/chatbot.db`). Every page navigation triggers a full table scan just to show "Page 1 of 5000".

**How to avoid:**
1. For MVP: Remove total page count display, use "Load More" pattern instead
2. Cache counts with short TTL (30-60 seconds)
3. Use approximate counts for display, exact counts only when necessary
4. Add composite indexes on filter columns

```python
# Bad - counts entire table every request
pagination = query.paginate(page=page, per_page=20)

# Better - avoid count for large tables
results = query.limit(per_page + 1).offset((page - 1) * per_page).all()
has_more = len(results) > per_page
items = results[:per_page]

# Return "has_more" flag instead of total count
return jsonify({
    'conversations': [c.to_dict() for c in items],
    'has_more': has_more,
    'page': page
})
```

**Warning signs:**
- Page load times are fine for page 1, but page 1000+ takes minutes
- Database locks during pagination (SQLite)
- `EXPLAIN` shows table scans on pagination queries

**Phase to address:**
Phase 2 (Filtering/Search) - Design pagination strategy before implementing filtering.

---

### Pitfall 5: Search Input Without Debouncing Overloading Server

**What goes wrong:**
Every keystroke triggers an API call. Typing "hello" sends 5 requests in rapid succession. With multiple users, this creates API avalanche, slows responses for everyone, and may trigger rate limiting.

**Why it happens:**
The existing `inbox.html` has a search input with direct `input` event handler that filters client-side. When migrating to server-side search (for larger datasets), developers often forget to add debouncing.

**How to avoid:**
1. Debounce search input with 300-500ms delay
2. Cancel pending requests when new search starts (AbortController)
3. Show loading indicator during search
4. Minimum character threshold (e.g., 3 chars) before searching

```javascript
let searchTimeout = null;
let searchAbortController = null;

document.getElementById('searchInput').addEventListener('input', function() {
    const query = this.value.trim();

    // Clear pending timeout
    clearTimeout(searchTimeout);

    // Abort pending request
    if (searchAbortController) {
        searchAbortController.abort();
    }

    // Minimum 3 characters
    if (query.length < 3 && query.length > 0) {
        return;
    }

    searchTimeout = setTimeout(() => {
        searchAbortController = new AbortController();

        fetch(`/chatbot/api/conversations?search=${encodeURIComponent(query)}`, {
            signal: searchAbortController.signal
        })
        .then(response => response.json())
        .then(data => updateConversationList(data))
        .catch(err => {
            if (err.name !== 'AbortError') {
                console.error('Search failed:', err);
            }
        });
    }, 300);
});
```

**Warning signs:**
- Network tab shows rapid consecutive requests while typing
- Server logs show high request volume from single users
- Search results "flicker" as multiple responses arrive out of order

**Phase to address:**
Phase 2 (Filtering/Search) - Build into search feature from the start.

---

### Pitfall 6: SQLite Locking Under Polling Load

**What goes wrong:**
Multiple concurrent polling requests cause "database is locked" errors. The Flask app hangs or returns 500 errors. Users see "Failed to load conversations" notifications.

**Why it happens:**
SQLite uses database-level locking, not row-level. The existing ChatBotAI uses SQLite (`instance/chatbot.db`). When polling creates read requests while background tasks (memory extraction, AI responses) create writes, lock contention occurs.

**How to avoid:**
1. Enable WAL mode for SQLite: `PRAGMA journal_mode=WAL;`
2. Set busy_timeout: `PRAGMA busy_timeout=5000;`
3. Keep transactions short - commit frequently
4. For production: Migrate to PostgreSQL

```python
# In config.py or create_app()
from sqlalchemy import event

def configure_sqlite(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA busy_timeout=5000;")
    cursor.close()

# In create_app():
if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
    event.listen(db.engine, 'connect', configure_sqlite)
```

**Warning signs:**
- Intermittent "database is locked" errors in logs
- Errors correlate with periods of high activity
- Flask workers hang under load

**Phase to address:**
Phase 1 (Polling Infrastructure) - Configure SQLite before adding polling load.

---

### Pitfall 7: Filter State Not in URL (Lost on Refresh/Share)

**What goes wrong:**
User applies filters (status=pending, platform=email), then refreshes page - all filters reset to defaults. User cannot share filtered view with teammate. Back button doesn't restore previous filter state.

**Why it happens:**
The existing `inbox.html` stores filter state only in JavaScript (active class on buttons). No URL parameter synchronization exists. This is typical for prototype UIs but becomes a major pain point for real usage.

**How to avoid:**
1. Sync ALL filter state to URL query parameters
2. Use `history.replaceState()` for filter changes (not pushState to avoid cluttered history)
3. Read initial state from URL parameters on page load
4. Consider using a small library like `qs` for complex filter serialization

```javascript
// Read filters from URL on page load
function getFiltersFromURL() {
    const params = new URLSearchParams(window.location.search);
    return {
        status: params.get('status') || 'all',
        platform: params.get('platform') || 'all',
        search: params.get('search') || ''
    };
}

// Update URL when filters change (without adding history entry)
function updateURLWithFilters(filters) {
    const params = new URLSearchParams();
    if (filters.status !== 'all') params.set('status', filters.status);
    if (filters.platform !== 'all') params.set('platform', filters.platform);
    if (filters.search) params.set('search', filters.search);

    const newURL = `${window.location.pathname}${params.toString() ? '?' + params.toString() : ''}`;
    history.replaceState(null, '', newURL);
}
```

**Warning signs:**
- QA reports "filters reset on refresh"
- Users manually share filter states via chat ("look at pending emails")
- Back button behaves unexpectedly after filtering

**Phase to address:**
Phase 2 (Filtering/Search) - Build URL sync into filtering from day 1.

---

### Pitfall 8: CRUD Edits Without Unsaved Changes Warning

**What goes wrong:**
User edits guest profile details, then accidentally clicks back button or closes tab - all changes lost with no warning. User re-enters data repeatedly. Trust in the application erodes.

**Why it happens:**
Browser's `beforeunload` event exists but isn't implemented. SPA-style navigation (if any) doesn't trigger it. Developers focus on the "happy path" of saving, not the accidental navigation case.

**How to avoid:**
1. Track "dirty" state - whether form has unsaved changes
2. Implement `beforeunload` handler when dirty
3. Style unsaved forms differently (e.g., subtle border color change)
4. Auto-save drafts to localStorage as fallback

```javascript
let formIsDirty = false;

// Track changes
document.querySelectorAll('#guestForm input, #guestForm textarea').forEach(el => {
    el.addEventListener('input', () => {
        formIsDirty = true;
        document.getElementById('guestForm').classList.add('has-changes');
    });
});

// Warn on navigation
window.addEventListener('beforeunload', (e) => {
    if (formIsDirty) {
        e.preventDefault();
        e.returnValue = ''; // Required for Chrome
    }
});

// Clear dirty state on successful save
function onSaveSuccess() {
    formIsDirty = false;
    document.getElementById('guestForm').classList.remove('has-changes');
}
```

**Warning signs:**
- Support tickets about "lost data"
- Users report entering same information multiple times
- Low completion rate on edit forms

**Phase to address:**
Phase 3 (CRUD Editing) - Implement before any edit forms go live.

---

### Pitfall 9: XSS via User Content in JavaScript Context

**What goes wrong:**
Guest name or message content contains JavaScript that executes in the host's browser. Attacker injects `<script>` tags or event handlers that steal session cookies or modify conversation data.

**Why it happens:**
Jinja2 auto-escapes HTML context but the existing templates embed data directly in JavaScript. Example from `conversation.html`: `const conversationId = {{ conversation.id }};` is safe (integer), but string interpolation like `const guestName = '{{ guest.name }}';` is vulnerable.

**How to avoid:**
1. Use `|tojson` filter for ALL data passed to JavaScript
2. Never use `|safe` on user-generated content
3. Set Content-Security-Policy header to block inline scripts (defense in depth)
4. Use `textContent` instead of `innerHTML` when updating DOM with user data

```html
<!-- Bad - XSS vulnerable -->
<script>
    const guestName = '{{ guest.name }}';  // If name is "'; alert('xss');//"
</script>

<!-- Good - properly escaped -->
<script>
    const guestName = {{ guest.name|tojson }};  // Produces escaped string
    const conversationData = {{ conversation.to_dict()|tojson }};
</script>

<!-- Also good - use data attributes -->
<div id="conversation-container"
     data-guest-name="{{ guest.name }}"
     data-conversation-id="{{ conversation.id }}">
</div>
<script>
    const container = document.getElementById('conversation-container');
    const guestName = container.dataset.guestName;  // Automatically decoded
</script>
```

**Warning signs:**
- Security scanner flags XSS vulnerabilities
- Weird characters appear broken in UI (over-escaping)
- User names render literally as `&lt;script&gt;`

**Phase to address:**
Phase 3 (CRUD Editing) - Audit ALL JavaScript string interpolation before guest editing.

---

### Pitfall 10: Optimistic UI Without Rollback Strategy

**What goes wrong:**
UI shows "message sent" immediately (optimistic update), but server request fails. Message appears sent to user but was never delivered. User doesn't realize the failure, guest never receives message.

**Why it happens:**
Optimistic UI provides better perceived performance but requires careful rollback handling. The existing `addMessageToUI()` function in `conversation.html` adds the message immediately but the error handler only shows an alert - it doesn't remove the optimistic message.

**How to avoid:**
1. Mark optimistic items visually (subtle "sending..." indicator)
2. Store reference to optimistic DOM elements for removal on failure
3. Implement retry mechanism for failed sends
4. Show persistent error state, not just alert

```javascript
async function sendMessage(e) {
    e.preventDefault();
    const content = messageInput.value.trim();
    if (!content) return;

    // Create optimistic message with pending state
    const tempId = 'temp-' + Date.now();
    const optimisticMessage = addMessageToUI({
        id: tempId,
        content: content,
        sender_type: 'owner',
        pending: true  // Mark as pending
    });
    optimisticMessage.classList.add('message-pending');

    messageInput.value = '';

    try {
        const response = await fetch(`/chatbot/api/conversations/${conversationId}/messages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content })
        });

        if (!response.ok) throw new Error('Send failed');

        const data = await response.json();
        // Replace optimistic message with real one
        optimisticMessage.classList.remove('message-pending');
        optimisticMessage.dataset.messageId = data.id;

    } catch (err) {
        // Remove optimistic message and restore input
        optimisticMessage.remove();
        messageInput.value = content;
        showNotification('Failed to send message. Please try again.', 'error');
    }
}
```

**Warning signs:**
- Users report "sent messages that guests never received"
- Messages appear duplicated (failed optimistic + successful retry)
- QA finds messages in UI that aren't in database

**Phase to address:**
Phase 3 (CRUD Editing) - Design error handling before implementing optimistic UI.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Client-side only filtering | Fast to implement, no API changes | Can't scale past ~100 items, inconsistent with server state | MVP with <50 conversations |
| Polling with fixed interval | Simple implementation | Wastes bandwidth when nothing changes, overloads server with many users | Development/testing only |
| `innerHTML` for dynamic content | Quick DOM updates | XSS vulnerability, breaks event handlers | Never with user content |
| Skip debouncing on search | Simpler code | API overload, poor UX with flickering results | Never in production |
| No URL state for filters | Faster initial development | Users can't share/bookmark, refresh loses state | Very early prototype only |
| SQLite in production | Zero setup, single file | Lock contention, no concurrent writes | Single-user or read-heavy only |

## Integration Gotchas

Common mistakes when connecting polling/filtering with existing ChatBotAI components.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Polling + Memory Service | Polling triggers memory extraction on every fetch | Only extract memory on NEW messages (check `processed` flag) |
| Filtering + AI Status | Filter by AI enabled but include AI-disabled conversations in count | Separate counts for filtered vs total, clear UI distinction |
| Search + GuestDetail | Search only conversation content, miss guest details | Include guest profile in search index or provide separate search |
| CRUD + Conversation Status | Edit guest while conversation is active, confuse AI context | Lock editing during active AI generation, or handle gracefully |
| Polling + Message Sending | Poll response overwrites optimistically added message | Merge poll results with local state, don't replace entirely |

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Load all conversations on page load | Slow initial load, high memory | Paginate from start, lazy load | >100 conversations |
| No index on `updated_at` | Slow ordering queries | Add index on sort columns | >10k messages |
| Eager load all relationships | Slow queries, high memory | Load only needed relationships | >50 guests with details |
| Poll all conversations for badge count | N requests for N conversations | Single count endpoint | >5 concurrent users |
| Store search index in memory | Fast search, but rebuilds on restart | Use database full-text or separate index | >1k messages |

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Guest can see other guests' data via API manipulation | Privacy violation, legal liability | Validate guest ownership in EVERY API endpoint |
| Message content rendered without escaping | XSS attack steals host's session | Use `|tojson` for JS, `textContent` for DOM |
| Filter parameters passed directly to SQL | SQL injection | Use SQLAlchemy ORM, never raw string interpolation |
| Polling endpoint returns full conversation history | Data exposure if endpoint guessed | Auth check on every poll endpoint |
| Edit API doesn't validate field types | Type confusion attacks | Schema validation (e.g., marshmallow) |

## UX Pitfalls

Common user experience mistakes in messaging dashboards.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No visual indicator of poll in progress | User thinks app is frozen | Subtle activity indicator (e.g., favicon change) |
| Filter resets on any navigation | User must re-apply filters constantly | Persist filters in URL and/or localStorage |
| Search requires pressing Enter | Users expect as-you-type results | Debounced live search |
| No confirmation before destructive actions | Accidental data loss | Confirm dialog for delete, warn for unsaved changes |
| Messages jump around when polling updates | Disorienting, hard to read | Maintain scroll position, only add to top/bottom |
| Badge count doesn't match visible messages | Confusing, looks buggy | Ensure count matches exactly what filters show |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Polling:** Often missing error handling and exponential backoff - verify with network disconnect test
- [ ] **Filtering:** Often missing URL sync - verify filters survive refresh and can be shared
- [ ] **Search:** Often missing debouncing - verify by watching network tab while typing
- [ ] **Editing:** Often missing unsaved changes warning - verify with back button mid-edit
- [ ] **Pagination:** Often missing loading states - verify skeleton/spinner shows during fetch
- [ ] **Badge Count:** Often stale when filters change - verify count updates with every filter
- [ ] **Error States:** Often only show toast, no recovery - verify can retry failed operations
- [ ] **Mobile:** Often untested - verify touch interactions, responsive layout

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Memory leak from timers | LOW | Clear all timers, refresh page, add cleanup code |
| N+1 query performance | MEDIUM | Add eager loading, may need to refactor model relationships |
| SQLite lock contention | HIGH | Enable WAL mode, or migrate to PostgreSQL |
| XSS vulnerability discovered | HIGH | Audit all templates, add CSP headers, rotate sessions |
| Lost user data from missing warning | HIGH | Apologize, add auto-save, implement unsaved changes detection |
| Polling overloading server | MEDIUM | Add rate limiting, implement conditional requests (ETag) |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Timer memory leaks | Phase 1 (Polling) | DevTools Memory tab shows stable usage after 10+ minutes |
| Background tab throttling | Phase 1 (Polling) | Switch tabs, wait 2 min, return - data is fresh |
| N+1 queries | Phase 2 (Filtering) | Debug toolbar shows <5 queries per page load |
| COUNT performance | Phase 2 (Filtering) | Last page loads in <500ms with 100k records |
| Search without debounce | Phase 2 (Filtering) | Network tab shows max 1 request per 300ms while typing |
| SQLite locking | Phase 1 (Polling) | No lock errors under 10 concurrent polling sessions |
| Filter state not in URL | Phase 2 (Filtering) | Copy URL, open in new tab - same filters applied |
| No unsaved changes warning | Phase 3 (CRUD) | Edit form, click back - browser warns |
| XSS in JavaScript context | Phase 3 (CRUD) | Guest name with `<script>` renders as text, not code |
| Optimistic UI without rollback | Phase 3 (CRUD) | Disconnect network mid-send - message removed, input restored |

## Sources

### Polling and Real-time Updates
- [The Flask Mega-Tutorial: User Notifications](https://blog.miguelgrinberg.com/post/the-flask-mega-tutorial-part-xxi-user-notifications) - MEDIUM confidence
- [Long Polling JavaScript patterns](https://javascript.info/long-polling) - HIGH confidence
- [Modern JavaScript Polling: Adaptive Strategies](https://medium.com/tech-pulse-by-collatzinc/modern-javascript-polling-adaptive-strategies-that-actually-work-part-1-9909f5946730) - MEDIUM confidence
- [Efficient Polling in React](https://medium.com/@atulbanwar/efficient-polling-in-react-5f8c51c8fb1a) - MEDIUM confidence

### SQLAlchemy and Database Performance
- [Flask-SQLAlchemy Pagination](https://flask-sqlalchemy.palletsprojects.com/en/stable/pagination/) - HIGH confidence
- [Poor pagination performance issue #272](https://github.com/pallets-eco/flask-sqlalchemy/issues/272) - HIGH confidence
- [SQLite concurrent writes and locking](https://tenthousandmeters.com/blog/sqlite-concurrent-writes-and-database-is-locked-errors/) - HIGH confidence
- [Flask-SQLAlchemy pagination slow #518](https://github.com/pallets-eco/flask-sqlalchemy/issues/518) - HIGH confidence

### JavaScript Memory and Timer Issues
- [JavaScript Memory Leaks - Forgotten timers](https://www.tutorialspoint.com/how-can-forgotten-timers-or-callbacks-cause-memory-leaks-in-javascript) - MEDIUM confidence
- [setInterval throttling in background tabs](https://pontistechnology.com/learn-why-setinterval-javascript-breaks-when-throttled/) - HIGH confidence

### Search and Debouncing
- [Optimize Search with Debouncing](https://www.freecodecamp.org/news/optimize-search-in-javascript-with-debouncing/) - HIGH confidence
- [Debouncing in React](https://www.developerway.com/posts/debouncing-in-react) - HIGH confidence

### Form Handling and UX
- [Display Warning for Unsaved Form Data](https://claritydev.net/blog/display-warning-for-unsaved-form-data-on-page-exit) - HIGH confidence
- [Unsaved Changes Pattern - Cloudscape](https://cloudscape.design/patterns/general/unsaved-changes/) - HIGH confidence

### URL State Management
- [URL state with useSearchParams](https://blog.logrocket.com/url-state-usesearchparams/) - HIGH confidence
- [replaceUrl for filter state](https://www.bennadel.com/blog/3614-using-replaceurl-to-persist-search-filters-in-the-url-without-messing-up-the-browser-history-in-angular-7-2-14.htm) - MEDIUM confidence

### Security
- [Flask XSS Cheat Sheet - Semgrep](https://semgrep.dev/docs/cheat-sheets/flask-xss) - HIGH confidence
- [Flask Security Considerations](https://flask.palletsprojects.com/en/stable/web-security/) - HIGH confidence

### Optimistic UI
- [Optimistic UI Guidelines](https://www.jacobparis.com/content/remix-crud-ui) - MEDIUM confidence
- [Optimistic UI Pattern](https://xiaoyunyang.github.io/post/web-developer-playbook-optimistic-ui/) - MEDIUM confidence

### Testing
- [Introduction to Testing in Flask](https://blog.appsignal.com/2025/04/02/an-introduction-to-testing-in-python-flask.html) - HIGH confidence
- [Flask Testing Documentation](https://flask.palletsprojects.com/en/stable/testing/) - HIGH confidence

---
*Pitfalls research for: ChatBotAI Dashboard UI Enhancements*
*Researched: 2026-02-17*
