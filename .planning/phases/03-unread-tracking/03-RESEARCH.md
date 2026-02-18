# Phase 3: Unread Tracking - Research

**Researched:** 2026-02-18
**Domain:** Unread status tracking, visual indicators, Flask/SQLAlchemy, CSS badges
**Confidence:** HIGH

## Summary

Phase 3 implements unread conversation tracking with visual indicators. The infrastructure is already in place: the `Conversation` model has an `is_read` Boolean field (added in Phase 1 with `server_default='1'` so existing conversations start as read). The polling infrastructure from Phase 2 is ready to surface unread state changes.

This phase requires:
1. **Backend API** to mark conversations as read (called when user opens a conversation)
2. **API updates** to include `is_read` in conversation responses (already present in `to_dict()`)
3. **CSS styling** for unread dot indicator and unread conversation highlighting
4. **JavaScript updates** to show indicators in inbox and mark conversations as read on view

The implementation is straightforward because:
- `is_read` field already exists on Conversation model
- `to_dict()` already includes `is_read` in API responses
- Polling infrastructure already updates inbox cards incrementally
- New guest messages already trigger conversation `is_read = False` via message router

**Primary recommendation:** Add a `PATCH /api/conversations/{id}/read` endpoint to mark conversations as read, CSS unread-dot styling, and JavaScript to mark-as-read on conversation view load.

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| FILT-03 | User can see unread indicator (blue dot) on unread conversations | CSS unread-dot class with `::before` pseudo-element positioned via flexbox; uses existing `--primary-color` variable (#2563eb) |
| POLL-05 | User sees visual indicator when new messages arrive | Polling already detects new conversations/updates; add `is_read: false` check to show unread styling; inbox polling re-applies filters including visual state |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Flask/SQLAlchemy | Existing | Backend API and model updates | Already in use; `is_read` field exists |
| Vanilla JavaScript | ES6+ | DOM manipulation for unread indicators | Consistent with existing codebase |
| CSS Custom Properties | Native | Unread dot styling with `--primary-color` | Matches existing design system |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| N/A | - | - | No additional libraries needed |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| CSS `::before` pseudo-element | Separate `<span>` element | Pseudo-element is cleaner, no extra DOM; matches existing badge patterns |
| Boolean `is_read` | Unread count per conversation | Count adds complexity; Boolean sufficient for visual indicator |
| Mark-on-view | Mark-on-click | View-based is more intuitive; matches email UX patterns |

**Installation:**
```bash
# No installation required - all native APIs and existing stack
```

## Architecture Patterns

### Pattern 1: Mark-as-Read on Conversation View Load
**What:** When user opens a conversation, automatically mark it as read
**When to use:** Conversation page load
**Example:**
```javascript
// In conversation.html - on DOMContentLoaded
document.addEventListener('DOMContentLoaded', function() {
    // Mark conversation as read (fire-and-forget)
    fetch(`/chatbot/api/conversations/${conversationId}/read`, {
        method: 'PATCH'
    }).catch(err => console.error('Failed to mark as read:', err));

    // Existing code: scroll to bottom, start polling
    scrollToBottom();
    messagePoller.start();
});
```

### Pattern 2: Unread Indicator via CSS Pseudo-element
**What:** Blue dot indicator positioned relative to conversation card
**When to use:** Unread conversations in inbox
**Example:**
```css
/* Source: Common inbox UI pattern (Gmail, Outlook, Slack) */
.conversation-card.unread {
    position: relative;
}

.conversation-card.unread::before {
    content: '';
    position: absolute;
    left: 8px;
    top: 50%;
    transform: translateY(-50%);
    width: 8px;
    height: 8px;
    background: var(--primary-color);
    border-radius: 50%;
}

/* Optional: bold guest name for unread */
.conversation-card.unread .guest-name {
    font-weight: 700;
}
```

### Pattern 3: Data Attribute for Unread State
**What:** Store `is_read` in data attribute for JavaScript filtering
**When to use:** Conversation cards in inbox
**Example:**
```html
<a href="..." class="conversation-card"
   data-conversation-id="{{ conv.id }}"
   data-is-read="{{ 'true' if conv.is_read else 'false' }}"
   data-status="{{ conv.status }}">
```

### Anti-Patterns to Avoid
- **Marking as read on inbox list load:** Users may scroll past without reading; only mark when actually viewing
- **Full page reload to update read state:** Use AJAX/fetch for smooth UX
- **No accessibility consideration:** Screen readers need text alternative for visual indicator
- **Polling that replaces unread class:** Incremental updates must preserve unread styling until explicitly read

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Unread dot positioning | Complex absolute positioning math | CSS `::before` with flexbox centering | CSS handles centering automatically |
| API response filtering | Custom response building | Existing `to_dict()` with `is_read` | Already includes the field |
| Unread state in polling | Separate API for unread count | Include in existing `/api/conversations` | No extra requests needed |

**Key insight:** The existing API already returns `is_read` in conversation data. The polling system already incrementally updates cards. This phase only needs: (1) CSS for visual indicator, (2) mark-as-read API endpoint, (3) small JS changes to apply/remove unread class.

## Common Pitfalls

### Pitfall 1: Race Condition on Mark-as-Read
**What goes wrong:** User opens conversation, poll runs, conversation gets marked unread by new message, mark-as-read runs, loses the new-message indication
**Why it happens:** Polling and mark-as-read are asynchronous
**How to avoid:** Mark-as-read should only run once on page load, not continuously; message polling does NOT reset read state
**Warning signs:** Conversation appears read even when new messages arrived while viewing

### Pitfall 2: Unread State Lost on Polling Update
**What goes wrong:** Polling replaces conversation card, loses unread class
**Why it happens:** `createConversationCard()` doesn't apply unread class based on `is_read`
**How to avoid:** Always check `conv.is_read` when creating/updating cards and apply `unread` class accordingly
**Warning signs:** Unread dot disappears after 15 seconds (poll interval)

### Pitfall 3: Guest Name in Jinja vs JavaScript Mismatch
**What goes wrong:** JavaScript creates card without bold name, Jinja renders with bold
**Why it happens:** Forgetting to apply unread styling in JavaScript `createConversationCard()`
**How to avoid:** Apply `unread` class in JavaScript card creation: `card.className = 'conversation-card' + (!conv.is_read ? ' unread' : '')`
**Warning signs:** New unread conversations look different than server-rendered ones

### Pitfall 4: Accessibility Omission
**What goes wrong:** Screen reader users cannot tell which conversations are unread
**Why it happens:** Blue dot is purely visual
**How to avoid:** Add `aria-label` or screen-reader-only text: `<span class="sr-only">Unread</span>`
**Warning signs:** No announcement when navigating to unread conversation with screen reader

### Pitfall 5: Not Updating Inbox After Reading
**What goes wrong:** User reads conversation, returns to inbox, still shows unread
**Why it happens:** Inbox was loaded before mark-as-read completed
**How to avoid:** Either (1) update card in localStorage/sessionStorage, or (2) rely on next poll to update, or (3) force poll on page visibility change (already implemented in Phase 2)
**Warning signs:** Inbox shows stale unread state until manual refresh

## Code Examples

Verified patterns from official sources and existing codebase:

### Mark-as-Read API Endpoint
```python
# Source: Flask patterns, consistent with existing routes.py
@chatbot_bp.route('/api/conversations/<int:conversation_id>/read', methods=['PATCH'])
def api_mark_conversation_read(conversation_id):
    """Mark a conversation as read"""
    conversation = Conversation.query.get_or_404(conversation_id)
    conversation.is_read = True
    db.session.commit()
    return jsonify({'success': True, 'is_read': True})
```

### CSS Unread Indicator
```css
/* Source: Standard inbox patterns (Gmail, Outlook, Slack) */
/* Add to static/css/style.css */

/* Unread conversation styling */
.conversation-card.unread {
    position: relative;
    background: var(--bg-secondary);
    border-left: 3px solid var(--primary-color);
}

/* Blue dot indicator */
.conversation-card.unread::before {
    content: '';
    position: absolute;
    left: -12px;  /* Outside the card */
    top: 50%;
    transform: translateY(-50%);
    width: 8px;
    height: 8px;
    background: var(--primary-color);
    border-radius: 50%;
}

/* Bold guest name for unread */
.conversation-card.unread .guest-name {
    font-weight: 700;
}

/* Screen reader only class for accessibility */
.sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
}
```

### JavaScript: Apply Unread Class on Card Creation
```javascript
// Source: Update to existing createConversationCard() in inbox.html
function createConversationCard(conv) {
    const card = document.createElement('a');
    card.href = `/chatbot/conversation/${conv.id}`;
    // Apply unread class based on is_read
    card.className = 'conversation-card' + (!conv.is_read ? ' unread' : '');
    card.dataset.conversationId = conv.id;
    card.dataset.updatedAt = conv.updated_at || '';
    card.dataset.status = conv.status;
    card.dataset.isRead = conv.is_read ? 'true' : 'false';

    // ... rest of card creation
}
```

### JavaScript: Update Unread State on Existing Card
```javascript
// Source: Update to existing updateConversationCard() in inbox.html
function updateConversationCard(card, conv) {
    // Update unread state
    if (conv.is_read) {
        card.classList.remove('unread');
    } else {
        card.classList.add('unread');
    }
    card.dataset.isRead = conv.is_read ? 'true' : 'false';

    // ... rest of update code
}
```

### Jinja Template: Unread Class and Accessibility
```html
<!-- Source: Update to inbox.html conversation card -->
<a href="{{ url_for('chatbot.conversation_view', conversation_id=conv.id) }}"
   class="conversation-card{% if not conv.is_read %} unread{% endif %}"
   data-conversation-id="{{ conv.id }}"
   data-updated-at="{{ conv.updated_at.isoformat() if conv.updated_at else '' }}"
   data-status="{{ conv.status }}"
   data-is-read="{{ 'true' if conv.is_read else 'false' }}">
    {% if not conv.is_read %}
    <span class="sr-only">Unread</span>
    {% endif %}
    <!-- ... rest of card -->
</a>
```

### Mark-as-Read on Conversation View
```javascript
// Source: Add to conversation.html on DOMContentLoaded
document.addEventListener('DOMContentLoaded', function() {
    // Mark conversation as read (fire-and-forget, error logged only)
    fetch(`/chatbot/api/conversations/${conversationId}/read`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' }
    }).catch(err => console.error('Failed to mark as read:', err));

    // Existing initialization
    scrollToBottom();
    messagePoller.start();
});
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Separate unread count badge | Boolean is_read with dot indicator | Current standard | Simpler; dot is sufficient for inbox UI |
| Full page reload on status change | AJAX/fetch with incremental DOM update | 2015+ (SPA era) | Better UX, no flicker |
| Icon-based unread (envelope icon change) | Dot indicator + bold text | Current trend (Gmail, Slack) | Cleaner, more scannable |

**Deprecated/outdated:**
- Envelope icon states (closed = unread, open = read): Harder to scan; dot is more visible
- Count badges per conversation: Overkill for this use case; appropriate for message counts only

## Open Questions

1. **Should marking as read be debounced?**
   - What we know: User opening conversation should mark it read
   - What's unclear: If user quickly navigates away, should it still be marked read?
   - Recommendation: Mark on page load (DOMContentLoaded); no debounce needed since viewing = read

2. **Visual indicator for new messages while viewing conversation (POLL-05)**
   - What we know: POLL-05 says "User sees visual indicator when new messages arrive"
   - What's unclear: Does this mean inbox-level or conversation-level indicator?
   - Recommendation: For inbox - unread dot already handles this. For conversation - new messages auto-scroll, which is sufficient visual feedback. Could add subtle "New messages" banner if needed in future.

3. **Unread filter button?**
   - What we know: Current filters are All/Active/Pending/Closed
   - What's unclear: Should there be an "Unread" filter?
   - Recommendation: Not in scope for this phase (not in requirements). Could add in Phase 4 as part of filter enhancements.

## Sources

### Primary (HIGH confidence)
- Existing codebase analysis: `models.py` (Conversation.is_read field), `routes.py` (API patterns), `inbox.html` (polling/card structure)
- MDN Web Docs - [aria-label attribute](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Attributes/aria-label) - Accessibility patterns
- Phase 2 RESEARCH.md - Polling patterns already implemented

### Secondary (MEDIUM confidence)
- [Bootstrap Badges Documentation](https://getbootstrap.com/docs/5.3/components/badge/) - Positioning patterns for notification badges
- [W3C WAI ARIA Techniques](https://www.w3.org/WAI/WCAG21/Techniques/aria/ARIA6) - aria-label best practices
- [Aditus aria-label examples](https://www.aditus.io/aria/aria-label/) - Screen reader accessibility patterns

### Tertiary (LOW confidence)
- N/A - All patterns verified against official sources or existing codebase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Uses existing infrastructure; `is_read` field already in model
- Architecture: HIGH - Straightforward CRUD + CSS; matches established inbox patterns
- Pitfalls: HIGH - Common issues well-documented; mitigations are standard practices
- Accessibility: MEDIUM - Patterns are standard but require testing with actual screen readers

**Research date:** 2026-02-18
**Valid until:** 2026-03-18 (30 days - stable patterns, unlikely to change)

## Implementation Notes for Planner

1. **Existing infrastructure:**
   - `Conversation.is_read` field exists (Boolean, default True, server_default='1')
   - `Conversation.to_dict()` already includes `is_read` in API responses
   - Polling infrastructure already handles incremental card updates
   - `createConversationCard()` and `updateConversationCard()` functions exist in inbox.html

2. **Required changes:**
   - Add `PATCH /api/conversations/{id}/read` endpoint to routes.py
   - Add CSS for `.conversation-card.unread` and `.sr-only` classes
   - Update Jinja template to add `unread` class conditionally
   - Update JavaScript `createConversationCard()` to apply unread class
   - Update JavaScript `updateConversationCard()` to toggle unread class
   - Add mark-as-read fetch call in conversation.html on DOMContentLoaded

3. **File structure:**
   - `routes.py`: Add mark-as-read endpoint
   - `static/css/style.css`: Add unread styling
   - `templates/chatbot/inbox.html`: Add unread class in Jinja, update JS functions
   - `templates/chatbot/conversation.html`: Add mark-as-read on load

4. **Testing considerations:**
   - Create test conversation, verify unread dot appears
   - Open conversation, return to inbox, verify dot removed
   - Test polling: new message arrives while on inbox, verify dot appears
   - Test accessibility: screen reader announces "Unread" for unread conversations

5. **Prior decisions from earlier phases (MUST honor):**
   - [01-01]: `server_default='1'` for is_read so existing conversations marked as read
   - [02-02]: XSS prevention with `escapeHtml()` - continue using for user-generated content
   - [02-02]: Filter and search reapplied after each polling update - must preserve this behavior
   - [02-03]: 10-second poll interval for conversation - mark-as-read should not interfere
   - [02-03]: Track message IDs immediately after send/AI-generate to prevent duplicates - unchanged
