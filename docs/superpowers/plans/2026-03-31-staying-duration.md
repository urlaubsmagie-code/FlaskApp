# Staying Duration Display — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show reservation check-in/check-out dates and night count in the conversation header and inbox list.

**Architecture:** Add `check_in`/`check_out` Date columns to the Conversation model. Populate them during Smoobu sync (including backfill for existing conversations). Display in the Jinja template (conversation header) and JS (inbox cards) using compact `DD.MM – DD.MM (Xn)` format.

**Tech Stack:** Flask/SQLAlchemy, Alembic migration, Jinja2, vanilla JS

---

### Task 1: Add check_in / check_out columns to Conversation model

**Files:**
- Modify: `models.py:257-260` (add columns after `smoobu_reservation_id`)
- Modify: `models.py:274-304` (update `to_dict()`)

- [ ] **Step 1: Add the two Date columns**

In `models.py`, after line 257 (`smoobu_reservation_id`), add:

```python
    # Reservation stay dates (from Smoobu)
    check_in = db.Column(db.Date, nullable=True)
    check_out = db.Column(db.Date, nullable=True)
```

- [ ] **Step 2: Expose dates in to_dict()**

In `models.py`, inside the `to_dict()` method, after the `'property_name'` line (296), add:

```python
            'check_in': self.check_in.isoformat() if self.check_in else None,
            'check_out': self.check_out.isoformat() if self.check_out else None,
```

- [ ] **Step 3: Commit**

```bash
git add models.py
git commit -m "feat(model): add check_in/check_out date columns to Conversation"
```

---

### Task 2: Create Alembic migration

**Files:**
- Create: `migrations/versions/p13_reservation_dates_add_checkin_checkout.py`

- [ ] **Step 1: Write the migration file**

Create `migrations/versions/p13_reservation_dates_add_checkin_checkout.py`:

```python
"""Add check_in and check_out date columns to conversation

Revision ID: p13_reservation_dates
Revises: p12_sessions
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'p13_reservation_dates'
down_revision = 'p12_sessions'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.add_column(sa.Column('check_in', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('check_out', sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table('conversation', schema=None) as batch_op:
        batch_op.drop_column('check_out')
        batch_op.drop_column('check_in')
```

- [ ] **Step 2: Run the migration**

```bash
cd C:\Users\admin\Documents\FlaskApp
python -m ChatBotAI.run db upgrade
```

Expected: Migration applies cleanly, two new columns on the `conversation` table.

- [ ] **Step 3: Commit**

```bash
git add migrations/versions/p13_reservation_dates_add_checkin_checkout.py
git commit -m "migrate: add check_in/check_out to conversation table (p13)"
```

---

### Task 3: Populate dates during Smoobu sync + backfill existing conversations

**Files:**
- Modify: `services/smoobu_service.py:612-622` (enrichment block)

- [ ] **Step 1: Add a helper to parse Smoobu date strings**

In `smoobu_service.py`, add this helper function near the top of the file (after the existing imports and helpers, around line 40):

```python
def _parse_smoobu_date(value):
    """Parse a Smoobu date string (YYYY-MM-DD) into a date object, or None."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except (ValueError, TypeError):
        return None
```

Also add `from datetime import date` to the existing datetime imports at the top of the file (it already imports `datetime` and `timedelta` — add `date` alongside them).

- [ ] **Step 2: Populate dates on new conversations during enrichment**

In `smoobu_service.py`, in the enrichment block around line 612-622 (the `if not existing_conv:` block), extend it to also set the dates on the conversation. Replace the block:

```python
                # Enrich guest data from reservation (only for new conversations)
                if not existing_conv:
                    final_conv = Conversation.query.filter_by(
                        platform_id=f"smoobu-{reservation_id}"
                    ).first()
                    if final_conv and final_conv.guest:
                        if not res_detail:
                            res_detail = self.get_reservation(reservation_id)
                        if res_detail:
                            self._enrich_guest_from_reservation(
                                final_conv.guest, res_detail, reservation_id)
```

with:

```python
                # Enrich guest data and stay dates from reservation
                final_conv = Conversation.query.filter_by(
                    platform_id=f"smoobu-{reservation_id}"
                ).first()
                if final_conv:
                    # Backfill check_in/check_out if missing
                    if not final_conv.check_in or not final_conv.check_out:
                        if not res_detail:
                            res_detail = self.get_reservation(reservation_id)
                        if res_detail:
                            ci = _parse_smoobu_date(
                                res_detail.get('arrival') or res_detail.get('check-in'))
                            co = _parse_smoobu_date(
                                res_detail.get('departure') or res_detail.get('check-out'))
                            if ci and not final_conv.check_in:
                                final_conv.check_in = ci
                            if co and not final_conv.check_out:
                                final_conv.check_out = co
                            db.session.commit()

                    # Enrich guest details (only for new conversations)
                    if not existing_conv and final_conv.guest:
                        if not res_detail:
                            res_detail = self.get_reservation(reservation_id)
                        if res_detail:
                            self._enrich_guest_from_reservation(
                                final_conv.guest, res_detail, reservation_id)
```

This handles both new conversations (full enrichment) and existing conversations missing dates (backfill). The `get_reservation()` call is made only when dates are missing, and the result is reused for guest enrichment.

- [ ] **Step 3: Commit**

```bash
git add services/smoobu_service.py
git commit -m "feat(smoobu): populate check_in/check_out dates during sync with backfill"
```

---

### Task 4: Display stay dates in conversation header

**Files:**
- Modify: `templates/chatbot/conversation.html:36-39`

- [ ] **Step 1: Add stay dates below the platform/property line**

In `templates/chatbot/conversation.html`, replace lines 36-39:

```html
                <span class="conversation-meta-text">
                    {{ conversation.platform|capitalize }}
                    {% if conversation.property %}- {{ conversation.property.name }}{% elif conversation.subject %}- {{ conversation.subject }}{% endif %}
                </span>
```

with:

```html
                <span class="conversation-meta-text">
                    {{ conversation.platform|capitalize }}
                    {% if conversation.property %}- {{ conversation.property.name }}{% elif conversation.subject %}- {{ conversation.subject }}{% endif %}
                </span>
                {% if conversation.check_in and conversation.check_out %}
                <span class="conversation-stay-dates">
                    {{ conversation.check_in.strftime('%d.%m') }} – {{ conversation.check_out.strftime('%d.%m') }}
                    ({{ (conversation.check_out - conversation.check_in).days }}n)
                </span>
                {% endif %}
```

- [ ] **Step 2: Commit**

```bash
git add templates/chatbot/conversation.html
git commit -m "feat(ui): show stay dates in conversation header"
```

---

### Task 5: Display stay dates in inbox cards

**Files:**
- Modify: `static/js/inbox.js:60-102` (createConversationCard)

- [ ] **Step 1: Add formatStayDates helper function**

In `static/js/inbox.js`, add this function near the top of the file (before `createConversationCard`), alongside the other formatting helpers:

```javascript
function formatStayDates(checkIn, checkOut) {
    if (!checkIn || !checkOut) return '';
    const ci = new Date(checkIn + 'T00:00:00');
    const co = new Date(checkOut + 'T00:00:00');
    const nights = Math.round((co - ci) / 86400000);
    const fmt = d => `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}`;
    return `${fmt(ci)} – ${fmt(co)} (${nights}n)`;
}
```

Note: `T00:00:00` is appended to avoid timezone-shift issues when parsing date-only ISO strings.

- [ ] **Step 2: Update createConversationCard to show dates in subject line**

In `static/js/inbox.js`, replace line 91:

```javascript
            <div class="conversation-subject">${escapeHtml(conv.property_name || conv.subject || 'No subject')}</div>
```

with:

```javascript
            <div class="conversation-subject">${escapeHtml(conv.property_name || conv.subject || 'No subject')}${conv.check_in && conv.check_out ? ` <span class="stay-dates">${formatStayDates(conv.check_in, conv.check_out)}</span>` : ''}</div>
```

- [ ] **Step 3: Commit**

```bash
git add static/js/inbox.js
git commit -m "feat(ui): show stay dates in inbox conversation cards"
```

---

### Task 6: CSS styling for stay dates

**Files:**
- Modify: `static/css/style.css` (add after `.conversation-meta-text` block around line 893)

- [ ] **Step 1: Add CSS for conversation header stay dates**

In `static/css/style.css`, after the `.conversation-meta-text` rule (around line 893), add:

```css
.conversation-stay-dates {
    font-size: 0.75rem;
    color: var(--text-light);
    display: block;
    margin-top: 1px;
}
```

- [ ] **Step 2: Add CSS for inbox stay dates**

In `static/css/style.css`, after the `.conversation-subject` rule (around line 579), add:

```css
.conversation-subject .stay-dates {
    color: var(--text-light);
    font-size: 0.8125rem;
    margin-left: 4px;
}
```

- [ ] **Step 3: Commit**

```bash
git add static/css/style.css
git commit -m "style: add styling for stay dates in header and inbox"
```

---

### Task 7: Bump cache versions and final verification

**Files:**
- Modify: `templates/chatbot/base.html` (bump inbox.js and style.css cache versions)

- [ ] **Step 1: Bump cache version for inbox.js**

In `templates/chatbot/base.html`, find the inbox.js script tag and bump the version query parameter (e.g., `?v=17` → `?v=18`).

- [ ] **Step 2: Bump cache version for style.css**

In `templates/chatbot/base.html`, find the style.css link tag and bump the version query parameter (e.g., `?v=22` → `?v=23`).

- [ ] **Step 3: Test manually**

1. Run the migration: `python -m ChatBotAI.run db upgrade`
2. Start the dev server: `python -m ChatBotAI.run`
3. Trigger a Smoobu sync (Settings > Smoobu > Sync Messages)
4. Check inbox — conversations with reservations should show dates after the property name
5. Open a conversation — header should show dates below the platform line
6. Check a non-Smoobu conversation — no dates should appear

- [ ] **Step 4: Commit**

```bash
git add templates/chatbot/base.html
git commit -m "chore: bump cache versions for inbox.js (v18) and style.css (v23)"
```
