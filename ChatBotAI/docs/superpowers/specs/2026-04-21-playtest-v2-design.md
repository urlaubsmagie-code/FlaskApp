# Playtest V2 — Design Spec

**Date:** 2026-04-21
**Builds on:** Chat Playtest v1 (already implemented: playtest_events.py, MessageRouter instrumentation, API endpoints, inbox filtering)

## Goal

Upgrade the Chat Playtest to use the real conversation page instead of a custom UI, so all features (UMI-Vorschlag, UMI-Antwort, Vorlagen, Auto-respond, templates) work identically to production. Add a guest profile setup form so the AI can be tested with fake guest information.

## Changes Overview

### 1. Debug Page — Playtest Launcher (replaces current chat UI)

The "Chat Playtest" tab in debug.html becomes a setup/launcher screen:

**Guest Profile Form:**
- Guest name (text input, default: "Playtest Guest")
- Family (text, e.g. "2 Erwachsene, 1 Kind (3 Jahre)")
- Pets (text, e.g. "1 Hund, mittelgroß")
- Allergies (text, e.g. "Glutenunverträglichkeit")
- Preferences (text, e.g. "Spätes Check-in, ruhige Lage")
- Special requests (textarea, free text)

**"Start Playtest" button:**
1. Creates Guest record with the name
2. Creates GuestDetail records for each non-empty field (category: family, pet, allergy, preference, special_request) with confidence=1.0
3. Creates Conversation with platform='playtest'
4. Redirects to `/chatbot/conversation/<id>`

**Previous playtests list (optional nice-to-have):**
- Show recent playtest conversations below the form for quick re-access

### 2. Conversation Page — Playtest Bar

When `conversation.platform == 'playtest'`, show a playtest toolbar at the top of the conversation (between the header and messages area).

**Playtest bar contains:**
- **"PLAYTEST" badge** — visual indicator (styled distinctively, e.g. orange/amber background)
- **"Send as Guest" input** — inline text input + send button. Posts to `POST /api/debug/playtest/<id>/message` with role=guest. After sending, reloads messages (or appends to DOM like normal polling would).
- **"Event Log" toggle button** — expands/collapses a panel below the bar showing pipeline events (reuses the polling from playtest_events.py)
- **"Edit Guest Profile" link** — links to `/chatbot/guest/<guest_id>`

**Event log panel (collapsible):**
- Same event polling and rendering logic from v1 (playtestPollEvents, playtestAddEvent)
- Appears between the playtest bar and the messages area when expanded
- Max-height with scroll, monospace font, color-coded event types

### 3. New API Endpoint

**`POST /api/debug/playtest/start` — update existing endpoint:**
- Accept additional fields: `family`, `pets`, `allergies`, `preferences`, `special_requests`
- Create GuestDetail records for each non-empty field

### 4. Template Data

The conversation page template needs to know it's a playtest. Add `is_playtest` to the template context in the `conversation_view` route:
```python
is_playtest = conversation.platform == 'playtest'
```

Pass to template and to `CONV_CONFIG` JS object.

## Files Modified

| File | Change |
|------|--------|
| `templates/chatbot/debug.html` | Replace chat UI with launcher form, keep event log CSS |
| `templates/chatbot/conversation.html` | Add playtest bar (conditional on is_playtest) |
| `static/js/conversation.js` | Add playtest bar JS (guest send, event log toggle/polling) |
| `routes.py` | Update `conversation_view` to pass is_playtest, update `api_playtest_start` to accept guest details |
| `static/css/style.css` | Add playtest bar styles |

## Files NOT Modified

| File | Reason |
|------|--------|
| `services/playtest_events.py` | Already working from v1 |
| `services/message_router.py` | Already instrumented from v1 |

## What Gets Removed

- The custom chat messages area, role switcher, send/AI buttons from debug.html playtest tab
- The playtest-specific message rendering JS (playtestAddMessage, playtestSend, playtestGenerateAI, playtestSetRole)
- Related CSS (.playtest-msg, .playtest-input, .role-switcher, etc.)

## What Stays

- Playtest CSS for event log (.playtest-event, .playtest-event-list, etc.)
- Event polling JS (playtestPollEvents, playtestAddEvent, playtestClearEvents)
- All playtest API endpoints
- Inbox filtering logic
