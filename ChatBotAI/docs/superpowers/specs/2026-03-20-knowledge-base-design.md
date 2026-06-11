# Knowledge Base — Structured Facts for AI Context

**Date:** 2026-03-20
**Status:** Approved

## Overview

Add a Knowledge Base system that lets the host store structured facts (WiFi passwords, check-in procedures, nearby places, etc.) that the AI can reference when responding to guests. Entries can be global (apply to all properties) or per-property.

This complements the existing free-text "Host Instructions" field, which remains for behavioral guidance ("be formal", "mention discounts"). The Knowledge Base handles concrete, queryable facts.

## Decisions

- **Scope:** Both global and per-property entries
- **Categories:** Predefined (6 fixed categories)
- **Entry format:** Simple label + value (not Q&A)
- **Data layer:** New `KnowledgeEntry` DB table (not JSON blob or file)
- **UI location:** Separate page at `/chatbot/knowledge`
- **Settings link:** Note below Host Instructions textarea pointing to Knowledge Base page

## Data Model

New `KnowledgeEntry` table in `models.py`:

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer, PK | Auto-increment |
| `property_id` | Integer, FK -> property.id, nullable | `NULL` = global, set = per-property |
| `category` | String(50), not null | One of the predefined categories |
| `label` | String(200), not null | Short title, e.g. "WiFi Password" |
| `value` | Text, not null | The actual information |
| `sort_order` | Integer, default 0 | Ordering within a category. Auto-incremented on create (max existing + 1). |
| `created_at` | DateTime | Auto-set |
| `updated_at` | DateTime | Auto-set on update |

**Composite index:** `(property_id, category)` for fast AI context queries.

**Relationship:** `Property` has `knowledge_entries` backref (cascade delete on property deletion). Global entries (`property_id = NULL`) are not FK-linked and are unaffected by property deletions.

**Methods:** Include `to_dict()` and `__repr__()` following existing model conventions.

### Predefined Categories

| Key | Display (DE) | Display (EN) |
|-----|-------------|-------------|
| `general` | Allgemeine Infos | General Info |
| `checkin_checkout` | Check-in / Check-out | Check-in / Check-out |
| `nearby` | In der Nähe | Nearby Places |
| `house_rules` | Hausregeln | House Rules |
| `emergency` | Notfallkontakte | Emergency Contacts |
| `faq` | Häufige Fragen | FAQ / Common Questions |

## Migration

New migration file `p6_knowledge_add_knowledge_entry.py` following the existing chain:
- Depends on: `p5_perf_add_composite_indexes`
- Creates: `knowledge_entry` table with all columns and composite index

## AI Context Integration

### Loading Logic

Knowledge entries must be loaded in **all three code paths** that generate AI responses:

1. **`MessageRouter._generate_ai_response()`** in `message_router.py` — auto-respond flow
2. **`api_generate_ai_response()`** in `routes.py` — "Generate AI Response" button
3. **`api_suggest_ai_response()`** in `routes.py` — "AI Suggest" button

All three paths must query and pass knowledge entries to `ai_service.generate_guest_response()`.

**Query logic (shared):**
1. Get `conversation.property_id`
2. Query: `KnowledgeEntry` WHERE `property_id IS NULL` OR `property_id = conversation.property_id`
3. Order by `category`, `sort_order`
4. Pass as list of dicts to `generate_guest_response()` via new optional `knowledge_entries` parameter (default `None` for backward compatibility)

### Prompt Size Safety

With 65+ properties, entries could accumulate. The formatted knowledge base section is capped at **2000 characters** in the prompt. If the formatted text exceeds this, entries are included in category order until the limit is reached, with a note "(...additional entries omitted)" appended. This prevents crowding out conversation history in the model's context window.

### Prompt Injection (in `ai_service.py` `_build_chat_messages`)

Injected into system prompt between property info and host instructions:

```
=== HOST KNOWLEDGE BASE ===
[General Info]
- WiFi Password: SunnyBeach2024
- Emergency Contact: +49 170 1234567

[Check-in / Check-out]
- Key Handover: Key box next to the front door, code 4521#

[Nearby Places]
- Supermarket: Lidl, 5 minutes walk on Hauptstrasse
===
```

New formatting method `_format_knowledge_entries()` in `AIService`.

### Signature Change

`generate_guest_response()` gets a new optional parameter `knowledge_entries: Optional[List[Dict]] = None`. This maintains backward compatibility — existing callers that don't pass it will work unchanged.

## API Routes

All under `/chatbot/api/knowledge`. Authentication is handled by the existing `before_request` handler in `routes.py` — no additional decorators needed.

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/api/knowledge` | List entries. `?property_id=X` for per-property, `?property_id=global` for global only, no param = all |
| `POST` | `/api/knowledge` | Create entry. Body: `{property_id, category, label, value}`. `property_id` null for global. |
| `PUT` | `/api/knowledge/<id>` | Update entry. Body: any subset of fields. |
| `DELETE` | `/api/knowledge/<id>` | Delete entry. |

Standard JSON responses matching existing API patterns in `routes.py`.

### Input Validation

- `category` must be one of the 6 predefined values. Reject with 400 if not.
- `label` is required, max 200 characters.
- `value` is required, max 2000 characters (prevents single entries from bloating the prompt).
- `property_id` if provided must reference an existing Property. Reject with 400 if not found.
- Duplicate labels within the same `(property_id, category)` scope are allowed (different WiFi networks, multiple nearby restaurants, etc.).

## Page Route

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/chatbot/knowledge` | Render knowledge base page. |

## Navigation

Add "Knowledge Base" / "Wissensdatenbank" entry to navigation in `base.html`:
- **Sidebar:** New nav item with database/book icon, placed between Settings and Debug
- **Mobile bottom nav:** Add to the overflow menu (not the main 4 bottom buttons)

## UI: Knowledge Base Page

**Template:** `templates/chatbot/knowledge.html` extending `base.html`.

### Layout

- **Header:** "Knowledge Base" title + `[+ Add Entry]` button
- **Filter bar:** Property dropdown — options: "All", "Global", then each property name from DB
- **Entries list:** Grouped by category with category headers. Each entry shows:
  - Label (bold) + value (regular text)
  - Property name tag or "Global" badge
  - Edit (pencil) and Delete (trash) icon buttons
- **Empty state:** Message when no entries exist yet, encouraging the user to add their first entry

### Add/Edit Modal

- **Scope:** Radio buttons "Global" / "Per Property" — selecting "Per Property" shows a property dropdown
- **Category:** Dropdown with the 6 predefined categories
- **Label:** Text input (required)
- **Value:** Textarea (required, supports multi-line)
- **Buttons:** Save / Cancel

### JavaScript

New `static/js/knowledge.js` external file following the pattern of `inbox.js` and `conversation.js`:
- CRUD operations via fetch to API routes
- Property filter dropdown handler
- Modal open/close/submit logic
- Category grouping and rendering

### Styling

Uses existing CSS variables (dark/light theme support). Card-based layout consistent with other pages. No new CSS file needed — styles go in `style.css` or inline in the template following existing patterns.

## UI: Settings Page Link

Below the existing Host Instructions textarea, add a note:

> "Für strukturierte Fakten (WLAN, Check-in, Umgebung) nutze die [Wissensdatenbank →](/chatbot/knowledge)"

With i18n key for English:

> "For structured facts (WiFi, check-in, nearby places), use the [Knowledge Base →](/chatbot/knowledge)"

## i18n

New keys in `static/js/i18n.js` for both German (default) and English:
- Page title, button labels, category names
- Modal labels, placeholders, validation messages
- Empty state text
- Settings page link text
- Navigation entry label

## Cache Versions

Bump cache versions for modified files:
- `i18n.js` version bump
- `style.css` version bump (if modified)
- New `knowledge.js` starts at v1

## Files Changed

| File | Change |
|------|--------|
| `models.py` | Add `KnowledgeEntry` model with `to_dict()` and `__repr__()` |
| `migrations/versions/p6_knowledge_*.py` | New migration |
| `routes.py` | Add page route + 4 API routes + load knowledge in existing AI routes |
| `services/message_router.py` | Load knowledge entries in `_generate_ai_response` |
| `services/ai_service.py` | Add `knowledge_entries` param + `_format_knowledge_entries()` |
| `templates/chatbot/knowledge.html` | New page template |
| `templates/chatbot/base.html` | Add navigation entry (sidebar + mobile overflow) |
| `templates/chatbot/settings.html` | Add link note below Host Instructions |
| `static/js/knowledge.js` | New JS file for Knowledge Base page |
| `static/js/i18n.js` | Add i18n keys + version bump |
| `static/css/style.css` | Minor styles if needed + version bump |
