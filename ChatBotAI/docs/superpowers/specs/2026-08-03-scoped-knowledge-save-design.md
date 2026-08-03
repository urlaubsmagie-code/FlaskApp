# Scoped + German Knowledge Save from the 🎓 Button — Design

**Date:** 2026-08-03
**Status:** Approved (design), pending implementation plan

## Problem

When a host clicks the 🎓 "save to knowledge" button on one of their own messages
in a conversation, the AI extraction (`api_extract_knowledge_from_message`) does two
things wrong:

1. **No scope choice.** It silently saves the extracted entry to the conversation's
   room only (`property_id` from the conversation). The host can't say "this applies
   to the whole building/street" or "this is general knowledge for all properties."
2. **Wrong language.** The extraction prompt never specifies an output language, so
   the local model returns English labels/values even though the team works in German.

Only the 🎓 flow is in scope. The manual "Add entry" form on the Wissensdatenbank
page already has room-vs-global scope and is **not** touched.

## Grouping key: Smoobu `street`

Properties are individual rooms (B1, F0, GK2…). Rooms in the same building share the
same **street** string that Smoobu returns in `location.street` (e.g. "Hertigswalder
Str. 27", "Bergblick 11"). Today that value is only mashed into the free-text
`Property.address`. We surface it as a structured field and use it as the building key.
No address parsing at match time, no manual per-room assignment.

## Data model

Two new **nullable** columns (Alembic migration):

- `Property.street` (String) — set from Smoobu `location.street` on every sync.
  Backfilled once for existing rows from `address.split(',')[0].strip()` (the address
  is built as `street, zip, city, country`, so element 0 is always the street).
- `KnowledgeEntry.street` (String, nullable, indexed) — the scope key.

A `KnowledgeEntry` now has exactly one of three scopes:

| Scope   | property_id | street                    |
|---------|-------------|---------------------------|
| Room    | `<room id>` | `NULL`                    |
| Street  | `NULL`      | `"Hertigswalder Str. 27"` |
| General | `NULL`      | `NULL`                    |

**Important:** "General" is now `property_id IS NULL AND street IS NULL`. Existing
global entries already satisfy this (street defaults NULL), so no data change needed.

## Retrieval (`message_router.py` ~line 700)

When answering a guest in a conversation with a known room, load non-correction
entries matching **any** of:

- General: `property_id IS NULL AND street IS NULL`
- This room: `property_id == conversation.property_id`
- This street: `street == property.street` (only when the room has a street)

Concretely the current `db.or_(property_id.is_(None), property_id == conv.property_id)`
becomes a three-branch `or_` where the general branch also requires `street.is_(None)`
and a new branch matches the room's street. The no-property branch (conversation with
unknown room) is unchanged: general entries only.

## Backend: extract endpoint

`POST /api/messages/<id>/extract-knowledge` accepts an optional JSON body
`{"scope": "room" | "street" | "general"}` (default `"room"` = today's behavior).

The endpoint resolves scope against the conversation's property:

- `room`    → `property_id = conversation.property_id`, `street = None`
- `street`  → `property_id = None`, `street = property.street`
- `general` → `property_id = None`, `street = None`

Guard rails (return 400 with a clear message, no partial save):
- `scope = room` but conversation has no `property_id` → reject.
- `scope = street` but the property has no `street` → reject.

All entries from one extraction share the resolved scope.

## Backend: German extraction

`AIService.extract_knowledge_from_message` prompt gains an explicit instruction: the
`label` and `value` must be written in **German**, regardless of the source message
language. System prompt reinforces it. No other extraction logic changes. Existing
English entries are left as-is (out of scope; can be hand-edited).

## Frontend: the popup

Clicking 🎓 no longer POSTs immediately. It opens a small popup (reusing the existing
modal/action-sheet styling) with up to three choices, labelled with the real names so
the host knows exactly what each means:

- **Nur dieses Zimmer** — shows the room name (e.g. "B3")
- **Diese Straße** — shows the street (e.g. "Hertigswalder Str. 27")
- **Allgemein**

Availability:
- Room unknown for this conversation → only **Allgemein**.
- Room known but no street → hide **Diese Straße**.

On choice, POST to the existing endpoint with `{scope}`, then the existing
success/error toast flow runs unchanged. Cancel closes the popup, saves nothing.

The popup labels its buttons from the conversation's property `name` and `street`.
The room `name` is already shown in the conversation view; `street` is added to the
property data serialized for the frontend (extend the existing conversation/property
JSON — `street` is the only new field needed). If `street` is empty, the popup hides
**Diese Straße**; if there is no property, it shows only **Allgemein**. The backend
guard rails are the safety net, but the popup already prevents choosing an
unavailable scope.

## Out of scope

- Manual "Add entry" form (unchanged).
- Re-translating existing English entries.
- Any street UI on the Wissensdatenbank page or settings.
- Grouping rooms by anything other than the exact Smoobu street string.

## Testing

- **Model/migration:** `Property.street` and `KnowledgeEntry.street` exist; backfill
  derives street from address element 0.
- **Retrieval:** a street-scoped entry is returned for a room on that street, NOT for a
  room on a different street; a general entry is returned everywhere; a room entry only
  for that room. (extends/mirrors existing message_router knowledge tests if present.)
- **Endpoint scope:** `street` scope saves `property_id=None, street=<prop street>`;
  `room` with no conversation property → 400; `street` with no property street → 400.
- **German:** covered by prompt assertion / manual check (extraction output language is
  model-dependent; assert the instruction is present in the prompt, verify live).
```
