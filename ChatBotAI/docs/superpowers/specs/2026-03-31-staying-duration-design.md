# Staying Duration Display — Design Spec

**Date**: 2026-03-31
**Status**: Draft

## Goal

Show reservation check-in/check-out dates and night count in the conversation header and inbox list, so hosts can see at a glance when a guest is staying.

## Format

Compact: `DD.MM – DD.MM (Xn)` where X = number of nights.
Example: `31.03 – 05.04 (5n)`

Hidden entirely when dates are not available.

## 1. Model Changes

Add two nullable Date columns to `Conversation`:

```python
check_in = db.Column(db.Date, nullable=True)
check_out = db.Column(db.Date, nullable=True)
```

Expose in `to_dict()`:
```python
'check_in': self.check_in.isoformat() if self.check_in else None,
'check_out': self.check_out.isoformat() if self.check_out else None,
```

## 2. Migration

New file: `migrations/versions/p13_reservation_dates_add_checkin_checkout.py`

Adds `check_in` and `check_out` Date columns to the `conversation` table.

## 3. Smoobu Sync Enrichment

In `smoobu_service.py` `sync_messages()`, after a conversation is created or found:

- Parse `arrival`/`check-in` and `departure`/`check-out` from the reservation detail (`res_detail`).
- Set `conv.check_in` and `conv.check_out` if not already populated.
- For the backfill case: when an existing conversation has `smoobu_reservation_id` but no `check_in`, fetch the reservation detail and populate the dates. This runs once per conversation during the next sync cycle.

Date parsing: Smoobu returns dates as `YYYY-MM-DD` strings. Parse with `datetime.strptime(val, '%Y-%m-%d').date()` or `date.fromisoformat(val)`.

## 4. Conversation Header (conversation.html)

Currently shows:
```
Platform - Property Name
```

After change, the `conversation-meta-text` span becomes two lines:
```
Booking.com - APT-204
31.03 – 05.04 (5n)
```

Implementation: Add a second `<span>` below `conversation-meta-text` that renders the dates using a Jinja helper/inline logic. Only shown when `conversation.check_in` and `conversation.check_out` are both set.

Night count: `(conversation.check_out - conversation.check_in).days`

## 5. Inbox List (inbox.js)

Currently the `conversation-subject` div shows property name or subject:
```html
<div class="conversation-subject">${conv.property_name || conv.subject || 'No subject'}</div>
```

After change, append stay dates when available:
```
APT-204 · 31.03 – 05.04 (5n)
```

Implementation: In `createConversationCard()` and `updateConversationCard()`, format the dates from `conv.check_in` / `conv.check_out` (ISO strings from API) and append to the subject text with a `·` separator.

JS formatting helper:
```javascript
function formatStayDates(checkIn, checkOut) {
    if (!checkIn || !checkOut) return '';
    const ci = new Date(checkIn);
    const co = new Date(checkOut);
    const nights = Math.round((co - ci) / 86400000);
    const fmt = d => `${String(d.getDate()).padStart(2,'0')}.${String(d.getMonth()+1).padStart(2,'0')}`;
    return `${fmt(ci)} – ${fmt(co)} (${nights}n)`;
}
```

## 6. CSS

Minimal styling — the date line in conversation header uses smaller/muted text. Inbox subject line stays single-line with the dates appended.

## 7. Edge Cases

- **No dates**: Hide entirely — no empty brackets or placeholders.
- **Same-day checkout**: Shows `(0n)` — unlikely but handled.
- **Non-Smoobu conversations** (Gmail, test): No dates available, nothing shown.
- **Guest with multiple reservations**: Each conversation has its own dates — no ambiguity.

## 8. Files Changed

| File | Change |
|------|--------|
| `models.py` | Add `check_in`, `check_out` columns + `to_dict()` |
| `migrations/versions/p13_...py` | New migration |
| `services/smoobu_service.py` | Populate dates during sync + backfill |
| `templates/chatbot/conversation.html` | Show dates in header |
| `static/js/inbox.js` | Show dates in inbox cards |
| `static/css/style.css` | Minor styling for date line |
| `routes.py` | No changes needed (dates come from model) |
| `templates/chatbot/base.html` | Bump cache version for inbox.js |
