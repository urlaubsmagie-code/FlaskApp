# Stack Research: Real-Time Dashboard Enhancements

**Domain:** Flask/Jinja2 messaging dashboard with vanilla JS
**Researched:** 2026-02-17
**Confidence:** HIGH

## Recommended Stack

### Decision: htmx vs Enhanced Vanilla JS

**Recommendation: Enhanced Vanilla JavaScript with structured patterns**

Given the constraint of "no new frontend frameworks" and the existing ~400 lines of vanilla JS, introducing htmx would be a new dependency that changes the development paradigm. The existing codebase already has:
- A working `apiRequest()` fetch wrapper
- Debounce utility function
- Notification toast system
- Conversation/message loading patterns

**Rationale:** Enhance the existing vanilla JS patterns rather than introducing htmx. For a dashboard with 10-50 active conversations, the complexity of htmx's HTML-over-the-wire approach is unnecessary. The existing fetch-based architecture is appropriate and maintainable.

### Core Technologies (Existing - No Changes)

| Technology | Version | Purpose | Status |
|------------|---------|---------|--------|
| Flask | 2.x/3.x | Web framework | Keep |
| Jinja2 | 3.x | Server-side templates | Keep |
| SQLAlchemy | 2.x | ORM | Keep |
| Vanilla JavaScript | ES6+ | Client interactivity | Enhance |

### Real-Time Polling

| Approach | Recommendation | Rationale |
|----------|----------------|-----------|
| **Short Polling** | YES - Use `setInterval` | Simple, sufficient for 10-50 conversations, 5-10 second intervals |
| Long Polling | NO | Overengineered for this volume, adds server complexity |
| WebSockets | NO | Requires Flask-SocketIO, async workers, adds significant complexity |
| Server-Sent Events | NO | Requires Redis/pubsub backend, incompatible with Flask dev server |

**Confidence:** HIGH - Multiple sources confirm short polling is appropriate for low-volume dashboards.

**Implementation Pattern:**
```javascript
// Use setInterval (NOT requestAnimationFrame) for data polling
// requestAnimationFrame is for visual animations, setInterval for API polling
class InboxPoller {
    constructor(interval = 5000) {
        this.interval = interval;
        this.timer = null;
        this.lastUpdate = null;
    }

    start() {
        this.poll(); // Immediate first poll
        this.timer = setInterval(() => this.poll(), this.interval);
    }

    stop() {
        if (this.timer) clearInterval(this.timer);
    }

    async poll() {
        // Include last update timestamp for delta updates
        const since = this.lastUpdate ? `?since=${this.lastUpdate}` : '';
        const data = await apiRequest(`/chatbot/api/conversations${since}`);
        this.lastUpdate = new Date().toISOString();
        this.updateUI(data);
    }
}
```

**Source:** [MDN requestAnimationFrame](https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame), [CSS-Tricks setInterval replacement](https://css-tricks.com/snippets/javascript/replacements-setinterval-using-requestanimationframe/)

### Filtering and Search

| Pattern | Recommendation | Rationale |
|---------|----------------|-----------|
| **Client-side filtering** | YES for current view | Already have ~50 conversations in DOM |
| **Server-side search** | YES for full-text search | SQLAlchemy ilike for message content |
| **Debounced input** | YES - 300ms delay | Prevent excessive API calls |

**Confidence:** HIGH - Existing codebase already has debounce function.

**Implementation Pattern:**
```javascript
// Extend existing debounce for search
const searchInput = document.getElementById('searchInput');
const debouncedSearch = debounce(async (query) => {
    if (query.length < 2) {
        // Client-side filter for short queries
        filterConversationsLocal(query);
    } else {
        // Server-side search for longer queries
        const results = await apiRequest(`/chatbot/api/conversations/search?q=${encodeURIComponent(query)}`);
        renderConversations(results);
    }
}, 300);

searchInput.addEventListener('input', (e) => debouncedSearch(e.target.value));
```

**Flask Route Pattern:**
```python
@chatbot_bp.route('/api/conversations/search', methods=['GET'])
def api_search_conversations():
    query = request.args.get('q', '')
    platform = request.args.get('platform')  # Optional filter
    status = request.args.get('status')      # Optional filter

    filters = []
    if query:
        filters.append(or_(
            Guest.name.ilike(f'%{query}%'),
            Guest.email.ilike(f'%{query}%'),
            Conversation.subject.ilike(f'%{query}%')
        ))
    if platform:
        filters.append(Conversation.platform == platform)
    if status:
        filters.append(Conversation.status == status)

    conversations = Conversation.query.join(Guest).filter(*filters).all()
    return jsonify({'conversations': [c.to_dict() for c in conversations]})
```

**Source:** [Flask-Filter PyPI](https://pypi.org/project/Flask-Filter/), [freeCodeCamp Flask HTMX Search](https://www.freecodecamp.org/news/how-to-implement-instant-search-with-flask-and-htmx/)

### Inline Editing (Guest Profiles)

| Pattern | Recommendation | Rationale |
|---------|----------------|-----------|
| **contenteditable** | NO | Requires complex state management, pasting issues |
| **Toggle form pattern** | YES | Clear edit/view states, familiar UX |
| **Inline form replace** | YES | Replace display element with form on edit click |

**Confidence:** HIGH - PatternFly and htmx click-to-edit patterns both use form toggle approach.

**Implementation Pattern:**
```javascript
// Toggle between display and edit mode
function enableEdit(element, fieldName, currentValue) {
    const displayHTML = element.innerHTML;
    element.dataset.originalValue = currentValue;
    element.dataset.originalHTML = displayHTML;

    element.innerHTML = `
        <input type="text" value="${escapeHTML(currentValue)}" class="inline-edit-input">
        <button class="btn-save" onclick="saveField(this.parentElement, '${fieldName}')">Save</button>
        <button class="btn-cancel" onclick="cancelEdit(this.parentElement)">Cancel</button>
    `;
    element.querySelector('input').focus();
}

async function saveField(element, fieldName) {
    const input = element.querySelector('input');
    const newValue = input.value.trim();
    const guestId = element.closest('[data-guest-id]').dataset.guestId;

    try {
        await apiRequest(`/chatbot/api/guests/${guestId}`, 'PATCH', { [fieldName]: newValue });
        element.innerHTML = `<span class="editable" onclick="enableEdit(this.parentElement, '${fieldName}', '${escapeHTML(newValue)}')">${escapeHTML(newValue)}</span>`;
        showNotification('Saved', 'success');
    } catch (err) {
        showNotification('Failed to save', 'error');
    }
}

function cancelEdit(element) {
    element.innerHTML = element.dataset.originalHTML;
}
```

**Source:** [PatternFly Inline Edit](https://pf3.patternfly.org/v3/pattern-library/forms-and-controls/inline-edit/), [htmx Click-to-Edit](https://htmx.org/examples/click-to-edit/)

### UI State Management

| Pattern | Recommendation | Rationale |
|---------|----------------|-----------|
| **URL query params** | YES for filters | Shareable/bookmarkable state |
| **sessionStorage** | YES for UI preferences | Persists across page navigation |
| **Data attributes** | YES for element state | Clean DOM-based state |

**Implementation Pattern:**
```javascript
// Sync filters with URL
function updateFilters(filters) {
    const url = new URL(window.location);
    Object.entries(filters).forEach(([key, value]) => {
        if (value) {
            url.searchParams.set(key, value);
        } else {
            url.searchParams.delete(key);
        }
    });
    history.replaceState({}, '', url);
    loadConversations(filters);
}

// Restore filters on page load
function restoreFilters() {
    const params = new URLSearchParams(window.location.search);
    return {
        platform: params.get('platform'),
        status: params.get('status'),
        search: params.get('q')
    };
}
```

## Supporting Libraries

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| None required | - | - | Vanilla JS sufficient for scope | HIGH |

**Rationale:** The existing codebase already has sufficient utilities (debounce, apiRequest, showNotification). Adding libraries for this scope would be overengineering.

## What NOT to Use

| Avoid | Why | Use Instead | Confidence |
|-------|-----|-------------|------------|
| htmx | New paradigm, changes development model, constraint violation | Enhanced vanilla JS patterns | HIGH |
| Alpine.js | Framework dependency, learning curve | Data attributes + vanilla JS | HIGH |
| jQuery | Deprecated pattern, adds 87KB | Native DOM APIs (already modern) | HIGH |
| Flask-SocketIO | Requires async workers, Redis, complex setup | Short polling with setInterval | HIGH |
| Flask-SSE | Requires Redis pubsub, incompatible with dev server | Short polling | HIGH |
| contenteditable | Pasting issues, complex state, inconsistent browser behavior | Form toggle pattern | HIGH |
| requestAnimationFrame for polling | Ties to display refresh rate (60-144Hz), inappropriate for data | setInterval (appropriate for data polling) | HIGH |

## Alternative: If htmx Were Allowed

If the "no new frameworks" constraint were lifted, htmx would be a strong choice:

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| htmx | 2.0.7 | Declarative AJAX | 14KB, HTML attributes, perfect Flask fit |
| flask-htmx | 0.4.0 | Flask integration | Detect htmx requests, return partials |

**htmx Polling Pattern:**
```html
<div hx-get="/chatbot/api/conversations"
     hx-trigger="every 5s"
     hx-swap="innerHTML">
</div>
```

**htmx Search Pattern:**
```html
<input type="search"
       hx-get="/chatbot/api/conversations/search"
       hx-trigger="input changed delay:300ms"
       hx-target="#conversation-list">
```

**htmx Click-to-Edit Pattern:**
```html
<div hx-get="/chatbot/api/guests/1/edit"
     hx-trigger="click"
     hx-swap="outerHTML">
    John Smith
</div>
```

**Source:** [htmx Official Docs](https://htmx.org/docs/), [htmx 2.0.7 Release](https://github.com/bigskysoftware/htmx/releases)

## Flask API Enhancements Required

### New Routes Needed

```python
# Search endpoint with multiple filters
@chatbot_bp.route('/api/conversations/search', methods=['GET'])
def api_search_conversations():
    # Implementation above
    pass

# Delta updates for polling
@chatbot_bp.route('/api/conversations/updates', methods=['GET'])
def api_get_updates():
    since = request.args.get('since')  # ISO timestamp
    # Return only conversations updated since timestamp
    pass

# Partial guest update
@chatbot_bp.route('/api/guests/<int:guest_id>', methods=['PATCH'])
def api_patch_guest(guest_id):
    # Update specific fields only
    pass
```

## Version Compatibility

| Package | Version | Compatible With | Notes |
|---------|---------|-----------------|-------|
| Flask | 2.x/3.x | Python 3.8+ | Already in use |
| SQLAlchemy | 2.x | Flask-SQLAlchemy 3.x | Already in use |

## Installation

```bash
# No new packages required
# Existing requirements.txt is sufficient
```

## Performance Considerations

| Concern | Approach | Rationale |
|---------|----------|-----------|
| Polling overhead | 5-second interval | 720 requests/hour acceptable for 1-10 users |
| Search responsiveness | 300ms debounce | Balances UX with server load |
| DOM updates | Incremental updates | Only update changed elements, not full re-render |
| Memory | Clear old timers | Stop polling on page navigation |

## Sources

### HIGH Confidence (Official Docs)
- [htmx Documentation](https://htmx.org/docs/) - Core attributes, swap options
- [htmx hx-trigger](https://htmx.org/attributes/hx-trigger/) - Polling syntax
- [htmx Click-to-Edit Example](https://htmx.org/examples/click-to-edit/) - Inline edit pattern
- [MDN requestAnimationFrame](https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame) - When NOT to use for polling
- [MDN Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events) - SSE limitations

### MEDIUM Confidence (Tutorials/Guides)
- [freeCodeCamp Flask HTMX Search](https://www.freecodecamp.org/news/how-to-implement-instant-search-with-flask-and-htmx/) - Search pattern
- [PatternFly Inline Edit](https://pf3.patternfly.org/v3/pattern-library/forms-and-controls/inline-edit/) - UX patterns
- [Flask SSE No Dependencies](https://maxhalford.github.io/blog/flask-sse-no-deps/) - SSE limitations explained
- [Medium: Real-Time Flask](https://medium.com/@robertjosephk/real-time-communication-python-flask-socket-vs-polling-11c97f1f2755) - Polling vs WebSockets

### LOW Confidence (Community)
- [GitHub htmx discussions](https://github.com/bigskysoftware/htmx/discussions) - Community patterns

---

*Stack research for: ChatBotAI messaging dashboard enhancements*
*Constraint: No new frontend frameworks - enhance existing vanilla JS*
*Researched: 2026-02-17*
