# Phase 8: Profile Editing - Research

**Researched:** 2026-02-19
**Domain:** CRUD operations for guest profiles and memory items (Flask + vanilla JavaScript)
**Confidence:** HIGH

## Summary

Phase 8 implements manual editing of guest profiles and memory items. The core challenge is creating an intuitive editing experience while maintaining the existing patterns established in the codebase. Research confirms the standard approach: modal forms for structured data (guest basic info) and inline editing with `contenteditable` for atomic memory items.

The codebase already has the backend infrastructure in place. Routes.py includes `api_add_guest_detail` and `api_delete_guest_detail` endpoints. Memory_service.py has the `store_detail` and `delete_guest_detail` methods. The primary work is frontend UI and two missing backend endpoints (guest update and detail update).

**Primary recommendation:** Use the native HTML `<dialog>` element for the guest edit modal, extend existing JavaScript patterns from app.js, and implement inline editing using `contenteditable` with blur/Enter key save triggers.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PROF-01 | User can edit guest basic info (name, email, phone) via modal form | Native `<dialog>` element with form validation; requires new PATCH endpoint |
| PROF-02 | User can add new memory items to guest profile | Existing POST endpoint `/api/guests/<id>/details` works; needs UI form |
| PROF-03 | User can delete memory items from guest profile | Existing DELETE endpoint works; need delete button with confirmation |
| PROF-04 | User can edit existing memory items inline (click to edit) | `contenteditable` with blur/Enter save; requires new PATCH endpoint |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Native `<dialog>` | HTML5 | Modal dialogs | No polyfill needed (Baseline 2022); built-in accessibility |
| `contenteditable` | HTML5 | Inline text editing | Native browser support; simpler than input replacement |
| Fetch API | ES6 | AJAX requests | Already used throughout app.js |
| Flask/SQLAlchemy | (existing) | Backend CRUD | Already established in codebase |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `plaintext-only` | HTML5.2 | Contenteditable mode | Prevents rich text paste; Baseline March 2025 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Native `<dialog>` | Custom div modal | Less accessible; more JavaScript needed |
| `contenteditable` | Input replacement pattern | More complex; flicker during transition |
| Inline editing | Modal for all edits | Less intuitive for quick edits |

**Installation:**
No new packages required. All functionality uses native browser APIs and existing Flask/SQLAlchemy stack.

## Architecture Patterns

### Recommended Pattern: Progressive Enhancement

The guest_profile.html template already renders static content from the server. The pattern is:
1. Server renders complete page (works without JS)
2. JavaScript enhances with edit capabilities
3. API endpoints handle updates

### API Endpoints Needed

**Existing endpoints (ready to use):**
```
POST   /api/guests/<id>/details     - Add memory item (api_add_guest_detail)
DELETE /api/guests/<id>/details/<detail_id> - Delete memory item (api_delete_guest_detail)
GET    /api/guests/<id>             - Get guest profile (api_get_guest)
```

**New endpoints required:**
```
PATCH  /api/guests/<id>             - Update guest basic info (name, email, phone)
PATCH  /api/guests/<id>/details/<detail_id> - Update memory item value
```

### Pattern 1: Modal Form for Guest Basic Info
**What:** Dialog-based form for editing name, email, phone
**When to use:** Structured data requiring multiple fields
**Example:**
```html
<!-- Source: W3C WAI ARIA Dialog Pattern -->
<dialog id="editGuestModal" aria-labelledby="editGuestTitle" aria-modal="true">
    <form method="dialog" id="editGuestForm">
        <h2 id="editGuestTitle">Edit Guest Information</h2>
        <div class="form-group">
            <label for="editGuestName">Name</label>
            <input type="text" id="editGuestName" name="name" required>
        </div>
        <div class="form-group">
            <label for="editGuestEmail">Email</label>
            <input type="email" id="editGuestEmail" name="email">
        </div>
        <div class="form-group">
            <label for="editGuestPhone">Phone</label>
            <input type="tel" id="editGuestPhone" name="phone">
        </div>
        <div class="form-actions">
            <button type="button" class="btn btn-secondary" onclick="closeEditModal()">Cancel</button>
            <button type="submit" class="btn btn-primary">Save Changes</button>
        </div>
    </form>
</dialog>
```

```javascript
// Source: MDN Dialog Element + existing app.js patterns
const modal = document.getElementById('editGuestModal');
const form = document.getElementById('editGuestForm');

function openEditModal(guest) {
    document.getElementById('editGuestName').value = guest.name || '';
    document.getElementById('editGuestEmail').value = guest.email || '';
    document.getElementById('editGuestPhone').value = guest.phone || '';
    modal.showModal();
}

function closeEditModal() {
    modal.close();
}

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = {
        name: document.getElementById('editGuestName').value,
        email: document.getElementById('editGuestEmail').value,
        phone: document.getElementById('editGuestPhone').value
    };

    try {
        await apiRequest(`/chatbot/api/guests/${guestId}`, 'PATCH', data);
        showNotification('Guest updated successfully', 'success');
        location.reload(); // Simple refresh to show updated data
    } catch (error) {
        showNotification('Failed to update guest', 'error');
    }
});

// Close on backdrop click
modal.addEventListener('click', (e) => {
    if (e.target === modal) closeEditModal();
});

// Close on Escape (native behavior with showModal)
```

### Pattern 2: Inline Editing for Memory Items
**What:** Click-to-edit for memory item values
**When to use:** Single-value edits needing quick interaction
**Example:**
```javascript
// Source: Sling Academy + CSS-Tricks contenteditable patterns
function initInlineEditing() {
    document.querySelectorAll('.memory-value[data-editable="true"]').forEach(el => {
        el.addEventListener('click', startEditing);
    });
}

function startEditing(e) {
    const el = e.target;
    if (el.contentEditable === 'true') return; // Already editing

    el.dataset.originalValue = el.textContent;
    el.contentEditable = 'plaintext-only';
    el.focus();

    // Select all text for easy replacement
    const range = document.createRange();
    range.selectNodeContents(el);
    window.getSelection().removeAllRanges();
    window.getSelection().addRange(range);

    el.addEventListener('blur', finishEditing, { once: true });
    el.addEventListener('keydown', handleEditKeydown);
}

function handleEditKeydown(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        e.target.blur(); // Triggers finishEditing
    } else if (e.key === 'Escape') {
        e.target.textContent = e.target.dataset.originalValue;
        e.target.blur();
    }
}

async function finishEditing(e) {
    const el = e.target;
    el.contentEditable = 'false';
    el.removeEventListener('keydown', handleEditKeydown);

    const newValue = el.textContent.trim();
    const originalValue = el.dataset.originalValue;

    if (newValue === originalValue || !newValue) {
        el.textContent = originalValue; // Restore if empty or unchanged
        return;
    }

    const detailId = el.dataset.detailId;

    try {
        await apiRequest(`/chatbot/api/guests/${guestId}/details/${detailId}`, 'PATCH', {
            detail_value: newValue
        });
        showNotification('Updated', 'success');
    } catch (error) {
        el.textContent = originalValue; // Restore on error
        showNotification('Failed to update', 'error');
    }
}
```

### Pattern 3: Add Memory Item Form
**What:** Inline form within each memory section for adding new items
**When to use:** Adding new atomic facts to a category
**Example:**
```html
<!-- Within each memory-section -->
<div class="memory-add-form" data-detail-type="family">
    <input type="text" class="memory-key-input" placeholder="Relation (e.g., son)">
    <input type="text" class="memory-value-input" placeholder="Name">
    <button type="button" class="btn btn-sm btn-primary add-memory-btn">
        <i class="fas fa-plus"></i> Add
    </button>
</div>
```

```javascript
document.querySelectorAll('.add-memory-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
        const form = btn.closest('.memory-add-form');
        const detailType = form.dataset.detailType;
        const keyInput = form.querySelector('.memory-key-input');
        const valueInput = form.querySelector('.memory-value-input');

        const detailKey = keyInput.value.trim();
        const detailValue = valueInput.value.trim();

        if (!detailKey || !detailValue) {
            showNotification('Both fields are required', 'error');
            return;
        }

        try {
            const result = await addGuestDetail(guestId, detailType, detailKey, detailValue);
            // Append new item to DOM
            appendMemoryItem(form.parentElement, result);
            keyInput.value = '';
            valueInput.value = '';
        } catch (error) {
            // Error already shown by addGuestDetail
        }
    });
});
```

### Pattern 4: Delete Memory Item
**What:** Delete button on each memory item with confirmation
**When to use:** Removing extracted or manual memory items
**Example:**
```html
<div class="memory-item" data-id="{{ detail.id }}">
    <span class="memory-key">{{ detail.key|title }}</span>
    <span class="memory-value" data-detail-id="{{ detail.id }}" data-editable="true">{{ detail.value }}</span>
    <span class="memory-confidence">{{ (detail.confidence * 100)|round }}%</span>
    <button class="btn-delete-memory" title="Delete" aria-label="Delete memory item">
        <i class="fas fa-times"></i>
    </button>
</div>
```

```javascript
document.querySelectorAll('.btn-delete-memory').forEach(btn => {
    btn.addEventListener('click', async (e) => {
        const item = btn.closest('.memory-item');
        const detailId = item.dataset.id;

        if (!confirm('Delete this memory item?')) return;

        try {
            await deleteGuestDetail(guestId, detailId);
            item.remove();
            // Show "No X recorded" if section now empty
            checkEmptySection(item.parentElement);
        } catch (error) {
            // Error already shown by deleteGuestDetail
        }
    });
});
```

### Anti-Patterns to Avoid
- **Full page reload after every edit:** Use DOM updates instead for responsiveness
- **Alert() for confirmations:** Use styled confirmation modals or native confirm()
- **Inline styles for edit states:** Use CSS classes that can be themed
- **Forgetting optimistic UI rollback:** Always restore original value on API failure
- **No visual feedback during save:** Show loading state for slow operations

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Modal dialogs | Custom div with z-index management | Native `<dialog>` element | Built-in focus trapping, backdrop, accessibility |
| Focus management | Custom focus trap loop | `dialog.showModal()` | Native API handles it |
| Text selection | Manual Range API manipulation | `document.execCommand('selectAll')` or Range API | Browser handles edge cases |
| Form validation | Custom regex checking | HTML5 validation attributes | `required`, `type="email"`, `pattern` |
| AJAX requests | XMLHttpRequest | Existing `apiRequest()` in app.js | Already handles errors, JSON |

**Key insight:** The existing app.js already has `apiRequest()`, `showNotification()`, `addGuestDetail()`, and `deleteGuestDetail()` helper functions. Reuse these rather than creating new patterns.

## Common Pitfalls

### Pitfall 1: Email Uniqueness Constraint
**What goes wrong:** User tries to change email to one already in use by another guest
**Why it happens:** Guest.email has `unique=True` constraint in model
**How to avoid:** Backend must check for conflicts and return clear error; frontend must display validation error
**Warning signs:** IntegrityError on commit

### Pitfall 2: Lost Focus After DOM Update
**What goes wrong:** After adding/deleting items, keyboard focus is lost
**Why it happens:** DOM element with focus is removed or replaced
**How to avoid:** After DOM changes, explicitly set focus to logical next element (add button, next item, or section header)
**Warning signs:** Tab key stops working after operation

### Pitfall 3: Stale Data After Concurrent Edits
**What goes wrong:** User A edits, User B edits, User A saves and overwrites B's changes
**Why it happens:** No optimistic locking or version checking
**How to avoid:** For v1, accept last-write-wins (single user system). Document as known limitation. Future: add `updated_at` comparison
**Warning signs:** Data mysteriously reverting

### Pitfall 4: Empty or Whitespace-Only Values
**What goes wrong:** User clears a field and saves empty string
**Why it happens:** No client-side or server-side validation
**How to avoid:** Trim input, validate non-empty, restore original on empty
**Warning signs:** "null" or empty strings appearing in UI

### Pitfall 5: XSS via Memory Values
**What goes wrong:** User enters `<script>alert('xss')</script>` as memory value
**Why it happens:** Using innerHTML or not escaping output
**How to avoid:** Use textContent for reading/writing `contenteditable`; Jinja auto-escapes by default
**Warning signs:** HTML rendering in text fields

### Pitfall 6: Dialog Not Centering on Scroll
**What goes wrong:** Modal appears off-screen if user has scrolled
**Why it happens:** Using absolute instead of fixed positioning
**How to avoid:** Native `<dialog>` with `showModal()` handles this; add `position: fixed` in CSS
**Warning signs:** Modal appearing at document top regardless of viewport

## Code Examples

### Backend: PATCH Guest Endpoint
```python
# Source: Existing routes.py patterns
@chatbot_bp.route('/api/guests/<int:guest_id>', methods=['PATCH'])
def api_update_guest(guest_id):
    """Update guest basic info (name, email, phone)"""
    guest = Guest.query.get_or_404(guest_id)
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Validate email uniqueness if changing
    if 'email' in data and data['email'] != guest.email:
        existing = Guest.query.filter_by(email=data['email']).first()
        if existing:
            return jsonify({'error': 'Email already in use'}), 409

    # Update allowed fields
    if 'name' in data:
        guest.name = data['name'].strip() if data['name'] else None
    if 'email' in data:
        guest.email = data['email'].strip() if data['email'] else None
    if 'phone' in data:
        guest.phone = data['phone'].strip() if data['phone'] else None

    db.session.commit()
    return jsonify(guest.to_dict())
```

### Backend: PATCH Detail Endpoint
```python
# Source: Existing routes.py patterns
@chatbot_bp.route('/api/guests/<int:guest_id>/details/<int:detail_id>', methods=['PATCH'])
def api_update_guest_detail(guest_id, detail_id):
    """Update a guest detail value"""
    detail = GuestDetail.query.filter_by(id=detail_id, guest_id=guest_id).first_or_404()
    data = request.get_json()

    if 'detail_value' not in data:
        return jsonify({'error': 'detail_value is required'}), 400

    new_value = data['detail_value'].strip()
    if not new_value:
        return jsonify({'error': 'detail_value cannot be empty'}), 400

    detail.detail_value = new_value
    detail.confidence = 1.0  # Manual edits have full confidence
    db.session.commit()

    return jsonify(detail.to_dict())
```

### CSS: Modal Styling (Add to style.css)
```css
/* Source: W3C WAI ARIA Dialog Pattern + existing design system */

/* Edit Modal */
dialog.edit-modal {
    border: none;
    border-radius: var(--border-radius-lg);
    padding: 0;
    max-width: 400px;
    width: 90%;
    box-shadow: var(--shadow-lg);
}

dialog.edit-modal::backdrop {
    background: rgba(0, 0, 0, 0.5);
}

dialog.edit-modal .modal-header {
    padding: 16px 20px;
    border-bottom: 1px solid var(--border-color);
    display: flex;
    justify-content: space-between;
    align-items: center;
}

dialog.edit-modal .modal-header h2 {
    margin: 0;
    font-size: 1.125rem;
}

dialog.edit-modal .modal-body {
    padding: 20px;
}

dialog.edit-modal .form-group {
    margin-bottom: 16px;
}

dialog.edit-modal .form-group label {
    display: block;
    margin-bottom: 6px;
    font-weight: 500;
    font-size: 0.875rem;
}

dialog.edit-modal .form-group input {
    width: 100%;
    padding: 10px 12px;
    border: 1px solid var(--border-color);
    border-radius: var(--border-radius);
    font-size: 0.9375rem;
}

dialog.edit-modal .form-group input:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

dialog.edit-modal .modal-footer {
    padding: 16px 20px;
    border-top: 1px solid var(--border-color);
    display: flex;
    justify-content: flex-end;
    gap: 8px;
}

/* Inline Editing */
.memory-value[data-editable="true"] {
    cursor: pointer;
    transition: background 0.2s;
}

.memory-value[data-editable="true"]:hover {
    background: rgba(37, 99, 235, 0.1);
    border-radius: 4px;
}

.memory-value[contenteditable="true"],
.memory-value[contenteditable="plaintext-only"] {
    outline: 2px solid var(--primary-color);
    background: white;
    padding: 2px 4px;
    border-radius: 4px;
}

/* Delete Button */
.btn-delete-memory {
    background: none;
    border: none;
    color: var(--text-light);
    cursor: pointer;
    padding: 4px;
    border-radius: 4px;
    opacity: 0;
    transition: all 0.2s;
}

.memory-item:hover .btn-delete-memory {
    opacity: 1;
}

.btn-delete-memory:hover {
    color: var(--danger-color);
    background: rgba(239, 68, 68, 0.1);
}

/* Add Memory Form */
.memory-add-form {
    display: flex;
    gap: 8px;
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px dashed var(--border-color);
}

.memory-add-form input {
    flex: 1;
    padding: 6px 10px;
    border: 1px solid var(--border-color);
    border-radius: var(--border-radius);
    font-size: 0.8125rem;
}

.memory-add-form input:focus {
    outline: none;
    border-color: var(--primary-color);
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Custom modal divs | Native `<dialog>` element | Baseline 2022 | No polyfill needed; built-in accessibility |
| `contenteditable="true"` | `contenteditable="plaintext-only"` | Baseline March 2025 | Prevents rich text paste issues |
| `aria-hidden` on background | `aria-modal="true"` on dialog | 2023+ | Simpler implementation |
| jQuery AJAX | Fetch API | ES6 (2015+) | Already used in codebase |

**Deprecated/outdated:**
- Google Chrome Dialog Polyfill: Only needed for IE/Edge Legacy; no longer required
- `document.execCommand()`: Deprecated but still useful for text selection; prefer Selection API

## Open Questions

1. **Should memory item keys be editable?**
   - What we know: Current schema has `detail_key` separate from `detail_value`
   - What's unclear: Do users need to edit the key (e.g., change "son" to "daughter")?
   - Recommendation: Start with value-only editing (simpler UX); add key editing if requested

2. **Confirmation before delete?**
   - What we know: Memory items are AI-extracted and potentially valuable
   - What's unclear: Is native `confirm()` acceptable or need styled modal?
   - Recommendation: Use native `confirm()` for v1 (matches "feature complete over polish" decision)

3. **Should edit button be always visible or hover-only?**
   - What we know: Current design uses hover states (e.g., delete button)
   - What's unclear: Touch device accessibility concerns
   - Recommendation: Hover-only for desktop consistency; add explicit edit button for touch

## Sources

### Primary (HIGH confidence)
- [W3C WAI ARIA Dialog Modal Pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/examples/dialog/) - Accessibility requirements
- [MDN Dialog Element](https://developer.mozilla.org/en-US/docs/Web/HTML/Element/dialog) - Native API reference
- Existing codebase: routes.py, memory_service.py, app.js, guest_profile.html - Established patterns

### Secondary (MEDIUM confidence)
- [Sling Academy: Inline Editing with JavaScript DOM](https://www.slingacademy.com/article/editing-text-content-inline-with-javascript-dom/) - Inline editing patterns
- [CSS-Tricks: Saving contenteditable Content](https://css-tricks.com/snippets/javascript/saving-contenteditable-content-changes-as-json-with-ajax/) - AJAX save patterns
- [Medium: Production-Ready Modal Component](https://medium.com/@francesco.saviano87/building-a-production-ready-modal-component-with-vanilla-javascript-a-complete-guide-4c125d20ddc9) - Modal best practices

### Tertiary (LOW confidence)
- [CopyProgramming: contenteditable Best Practices 2026](https://copyprogramming.com/howto/prevent-line-paragraph-breaks-in-contenteditable) - Recent updates (verify before use)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Uses native browser APIs already supported
- Architecture: HIGH - Extends existing codebase patterns
- Pitfalls: MEDIUM - Based on common patterns, may have edge cases

**Research date:** 2026-02-19
**Valid until:** 2026-03-19 (30 days - stable domain)
