# Phase 7: Search - Research

**Researched:** 2026-02-19
**Domain:** Full-text search integration with existing FTS5 backend and FilterState frontend
**Confidence:** HIGH

## Summary

Phase 7 builds search functionality on top of a solid foundation: FTS5 full-text search infrastructure (Phase 1) and FilterState centralized filter management (Phase 4). The FTS5 virtual table `message_fts` already indexes message content, guest names, and conversation subjects with BM25 ranking. The frontend FilterState module already combines platform, status, guest, and search filters in `applyFilters()`.

The primary work is:
1. Adding a search API endpoint that calls existing `search_messages()` utility
2. Enhancing the frontend to highlight matches using FTS5 `snippet()` function
3. Adding "search" URL parameter to FilterState for bookmarkable search
4. Creating an empty state UI when search returns no results

**Primary recommendation:** Leverage existing backend FTS5 infrastructure and extend FilterState to persist search in URL, with server-side search for accurate highlighting via FTS5 snippet() function.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SRCH-01 | User can search conversations by guest name | FTS5 `guest_name` column indexed, `search_by_guest_name()` utility exists |
| SRCH-02 | User can search across message content with full-text search | FTS5 `content` column indexed, `search_messages()` utility exists with BM25 ranking |
| SRCH-03 | User can combine filters with search (search within filtered results) | FilterState.applyFilters() already combines platform, status, guest, and search in `matchesSearch` check |
| SRCH-04 | User sees search results with highlighted match context | FTS5 `snippet()` function exists in `get_search_snippet()` utility - use for context preview |
| SRCH-05 | User sees helpful empty state when search returns no results | CSS `.empty-state` pattern exists - add search-specific variant with suggestions |
</phase_requirements>

## Standard Stack

### Core (Already Implemented)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLite FTS5 | Built-in | Full-text search with ranking | Standard SQLite extension, porter stemmer, BM25 ranking |
| Flask-SQLAlchemy | Installed | Database ORM with raw SQL support | Already used throughout project |

### Supporting (To Add)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| None | - | - | No new dependencies needed |

### Existing Infrastructure
- `utils/search.py` - `search_messages()`, `search_by_guest_name()`, `get_search_snippet()`
- `static/js/filter-state.js` - `FilterState` with URL sync, `applyFilters()` combining all filters
- `migrations/.../6a66ca2c2d11_add_fts5_search_index.py` - FTS5 virtual table with triggers

**Installation:** No new packages required.

## Architecture Patterns

### Recommended Approach: Hybrid Client-Server Search

Current state: `filterState.applyFilters()` does client-side text matching via `card.textContent.toLowerCase().includes(searchTerm)`. This works for basic matching but:
- Cannot provide accurate match context highlighting
- Does not leverage FTS5 ranking (relevance scoring)
- Searches all text in card (including badges, status) not just message content

**Recommended pattern:**
1. **Client-side filtering for quick feedback** - Keep existing `matchesSearch` for instant UI response
2. **Server-side search for results** - Call `/api/search` endpoint for actual result set with snippets
3. **Replace cards with search results** - When search is active, show ranked results from server

### Pattern 1: Search API Endpoint
**What:** Add `/api/search` endpoint using existing `search_messages()` utility
**When to use:** When user searches (debounced input, or Enter key)
**Example:**
```python
# Source: routes.py (to add)
@chatbot_bp.route('/api/search', methods=['GET'])
def api_search():
    """Search conversations and messages using FTS5"""
    from .utils.search import search_messages, get_search_snippet

    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'results': [], 'query': ''})

    # Get search results with ranking
    results = search_messages(query, limit=50)

    # Add snippets for highlighting
    for r in results:
        r['snippet'] = get_search_snippet(query, r['message_id'])

    # Group by conversation for display
    # ... (group logic)

    return jsonify({'results': grouped, 'query': query})
```

### Pattern 2: FilterState Search URL Persistence
**What:** Add `search` parameter to FilterState URL sync
**When to use:** To make search results bookmarkable and support back button
**Example:**
```javascript
// Source: filter-state.js (to extend)
// In loadFromURL():
this.state.search = params.get('q') || null;

// In saveToURL():
if (this.state.search) {
    url.searchParams.set('q', this.state.search);
} else {
    url.searchParams.delete('q');
}
```

### Pattern 3: FTS5 Snippet Highlighting
**What:** Use FTS5 `snippet()` function to get highlighted match context
**When to use:** Displaying search results with match preview
**Example:**
```python
# Source: utils/search.py (already exists)
def get_search_snippet(query_text, message_id, around=10):
    sql = text("""
        SELECT snippet(message_fts, 0, '<mark>', '</mark>', '...', :around) as snippet
        FROM message_fts
        WHERE message_fts.rowid = :message_id
        AND message_fts MATCH :query
    """)
```

**Note:** This function already exists in `utils/search.py`. Returns HTML with `<mark>` tags for highlighting.

### Pattern 4: Empty Search State
**What:** Dedicated empty state UI for no search results
**When to use:** When FTS5 returns empty result set
**Example HTML:**
```html
<div class="empty-state search-empty">
    <i class="fas fa-search"></i>
    <h3>No results for "{{ query }}"</h3>
    <p>Try searching for:</p>
    <ul>
        <li>Guest names (e.g., "John Smith")</li>
        <li>Keywords from messages</li>
        <li>Conversation subjects</li>
    </ul>
    <button onclick="filterState.reset()">Clear search</button>
</div>
```

### Anti-Patterns to Avoid
- **Client-only search** - Loses FTS5 ranking, can't highlight properly. Use server for results.
- **Full page reload on search** - Use AJAX to update conversation list dynamically.
- **Searching on every keystroke without debounce** - Overloads server. Debounce 300ms.
- **Not escaping HTML in snippets** - FTS5 snippet() returns raw HTML. Must be rendered as HTML.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Text highlighting | Regex-based highlight function | FTS5 `snippet()` | Handles stemming, tokenization edge cases |
| Relevance ranking | Custom scoring algorithm | FTS5 `bm25()` | Industry-standard, already configured |
| Full-text indexing | LIKE '%query%' searches | FTS5 MATCH | O(1) vs O(n), handles stemming |
| Query parsing | Custom tokenizer | FTS5 tokenize option | Porter stemmer, unicode61 already configured |

**Key insight:** FTS5 already handles the hard parts. The planner should use existing `search_messages()` and `get_search_snippet()` rather than building alternatives.

## Common Pitfalls

### Pitfall 1: FTS5 Query Syntax Errors
**What goes wrong:** User input like `"hello` (unclosed quote) or `AND` (reserved word) causes FTS5 MATCH to fail
**Why it happens:** FTS5 has SQL-like query syntax that can conflict with user input
**How to avoid:** Escape or sanitize query before passing to FTS5, or wrap entire query in quotes
**Warning signs:** "FTS syntax error" in logs, search returning empty for valid-looking queries

**Recommendation:** Use simple word matching by default. For advanced users, could add "exact phrase" mode with explicit quotes.

### Pitfall 2: Snippet XSS
**What goes wrong:** FTS5 snippet returns HTML (`<mark>`) which must be rendered as HTML, but message content could contain malicious scripts
**Why it happens:** snippet() includes raw message content with highlighting markers
**How to avoid:** Sanitize snippet output to only allow `<mark>` tags, escape everything else
**Warning signs:** Script tags or event handlers appearing in search results

**Recommendation:** Server-side sanitization of snippet before returning to client.

### Pitfall 3: Search State Desync
**What goes wrong:** Search input value doesn't match URL state after back button
**Why it happens:** popstate handler updates FilterState but doesn't update input element
**How to avoid:** In popstate handler, also set `searchInput.value = this.state.search || ''`
**Warning signs:** URL shows `?q=hello` but input is empty

### Pitfall 4: SQLite String Datetime in Results
**What goes wrong:** `sent_at.isoformat()` throws error because SQLite returns string not datetime
**Why it happens:** Raw SQL queries on SQLite return datetime columns as strings
**How to avoid:** Already handled in `search_messages()` with `isinstance()` check
**Warning signs:** AttributeError on `.isoformat()` in search results

**Status:** Already fixed in Phase 1 implementation.

## Code Examples

### Server-Side: Search API Endpoint
```python
# Source: routes.py (to add)
@chatbot_bp.route('/api/search', methods=['GET'])
def api_search():
    """
    Search conversations and messages using FTS5.
    Returns grouped results by conversation with highlighted snippets.
    """
    from .utils.search import search_messages, get_search_snippet
    import html
    import re

    query = request.args.get('q', '').strip()
    platform = request.args.get('platform')  # Optional filter
    status = request.args.get('status')      # Optional filter

    if not query:
        return jsonify({'results': [], 'query': '', 'total': 0})

    # Get search results
    results = search_messages(query, limit=100)

    # Optionally filter by platform/status
    if platform:
        results = [r for r in results if r['platform'] == platform]
    if status:
        # Need to add status to search_messages result
        pass

    # Add sanitized snippets
    def sanitize_snippet(snippet):
        """Allow only <mark> tags, escape everything else"""
        if not snippet:
            return None
        # Escape HTML, then restore <mark> tags
        escaped = html.escape(snippet)
        escaped = escaped.replace('&lt;mark&gt;', '<mark>')
        escaped = escaped.replace('&lt;/mark&gt;', '</mark>')
        return escaped

    for r in results:
        raw_snippet = get_search_snippet(query, r['message_id'])
        r['snippet'] = sanitize_snippet(raw_snippet)

    # Group by conversation_id for display
    grouped = {}
    for r in results:
        conv_id = r['conversation_id']
        if conv_id not in grouped:
            grouped[conv_id] = {
                'conversation_id': conv_id,
                'guest_name': r['guest_name'],
                'guest_id': r['guest_id'],
                'subject': r['subject'],
                'platform': r['platform'],
                'matches': []
            }
        grouped[conv_id]['matches'].append({
            'message_id': r['message_id'],
            'snippet': r['snippet'],
            'sender_type': r['sender_type'],
            'sent_at': r['sent_at']
        })

    return jsonify({
        'results': list(grouped.values()),
        'query': query,
        'total': len(grouped)
    })
```

### Client-Side: FilterState Search Extension
```javascript
// Source: filter-state.js (extend existing)

// Add to state object in constructor:
this.state = {
    platform: null,
    status: null,
    guest: null,
    search: null  // ADD THIS
};

// Add to loadFromURL():
this.state.search = params.get('q') || null;

// Add to saveToURL():
if (this.state.search) {
    url.searchParams.set('q', this.state.search);
} else {
    url.searchParams.delete('q');
}

// Add setSearch method:
setSearch(query) {
    this.state.search = query || null;
    this.saveToURL();
    // Don't call applyFilters here - let search handler do server fetch
}
```

### Client-Side: Search Input Handler with Debounce
```javascript
// Source: inbox.html (update existing search handler)

let searchTimeout = null;

document.getElementById('searchInput').addEventListener('input', function() {
    const query = this.value.trim();

    // Clear previous timeout
    if (searchTimeout) clearTimeout(searchTimeout);

    // Immediate client-side filtering for quick feedback
    filterState.applyFilters();

    // Debounced server search for accurate results
    searchTimeout = setTimeout(async () => {
        if (query.length >= 2) {
            const results = await fetchSearchResults(query);
            renderSearchResults(results);
        } else if (query.length === 0) {
            // Clear search, restore normal list
            clearSearchResults();
        }
    }, 300);
});

async function fetchSearchResults(query) {
    const params = new URLSearchParams({ q: query });
    if (filterState.state.platform) params.set('platform', filterState.state.platform);
    if (filterState.state.status) params.set('status', filterState.state.status);

    const response = await fetch(`/chatbot/api/search?${params}`);
    return response.json();
}
```

### Empty Search State
```html
<!-- Source: inbox.html (add alongside existing empty-state) -->
<div class="empty-state search-empty" id="searchEmptyState" style="display: none;">
    <i class="fas fa-search"></i>
    <h3>No results found</h3>
    <p class="search-query-display">No matches for "<span id="searchQueryText"></span>"</p>
    <p>Suggestions:</p>
    <ul class="search-suggestions">
        <li>Check spelling</li>
        <li>Try different keywords</li>
        <li>Search for guest name or message content</li>
    </ul>
    <button class="btn btn-secondary" onclick="clearSearch()">
        <i class="fas fa-times"></i> Clear Search
    </button>
</div>
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Client-only text search | FTS5 server-side + client hybrid | Phase 1 infra | Enables proper ranking, highlighting |
| Inline filter logic | Centralized FilterState | Phase 4 | Search integrates cleanly with existing filters |
| Page reload on filter | AJAX-based list update | Phase 2 (polling) | Search results update without reload |

**Deprecated/outdated:**
- Client-only `textContent.includes()` search: Still useful for quick feedback, but not for final results

## Open Questions

1. **Server vs Client Search Authority**
   - What we know: Client search gives instant feedback, server search gives accurate ranking
   - What's unclear: Should search results completely replace inbox list, or just highlight/filter?
   - Recommendation: Replace list when search active, restore on clear. Show match count.

2. **Search Result Grouping**
   - What we know: FTS5 returns message-level results, but inbox shows conversations
   - What's unclear: Show multiple matches per conversation? How to indicate match count?
   - Recommendation: Group by conversation, show first match snippet, indicate total matches.

3. **Search Within Filters vs Global Search**
   - What we know: SRCH-03 requires "search within filtered results"
   - What's unclear: Does this mean server-side filtering or client-side post-filter?
   - Recommendation: Pass platform/status to search API, filter results server-side.

## Sources

### Primary (HIGH confidence)
- `utils/search.py` - Existing FTS5 search utilities, verified implementation
- `static/js/filter-state.js` - FilterState module, verified implementation
- `.planning/phases/01-infrastructure-foundation/01-02-SUMMARY.md` - FTS5 decisions
- SQLite FTS5 documentation - Official source for snippet(), bm25() functions

### Secondary (MEDIUM confidence)
- Prior phase plans (04-01, 04-02) - Filter integration patterns

### Tertiary (LOW confidence)
- None - all findings verified against codebase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All components exist and verified
- Architecture: HIGH - Builds on proven Phase 1/4 patterns
- Pitfalls: HIGH - Based on actual issues encountered in Phase 1

**Research date:** 2026-02-19
**Valid until:** N/A (codebase-specific research)
