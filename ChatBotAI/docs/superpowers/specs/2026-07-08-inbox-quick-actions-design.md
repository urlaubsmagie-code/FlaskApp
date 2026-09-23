# Inbox Quick-Actions Menu (⋮) — Design

**Date:** 2026-07-08
**Status:** Approved (pending spec review)
**Author:** Claude + user

## Goal

Let the team manage a chat directly from the inbox — **without opening it** — via a
three-dots (⋮) menu on each conversation card. Speeds up triage, especially on
mobile.

## Non-goals

- No long-press gesture in v1 (undiscoverable as a sole trigger; may add later as a
  bonus, never as the only entry point).
- No bulk/multi-select actions.
- No new AI behavior — reuse the existing generate + approval-queue pipeline.

## UX

### Trigger
- A **⋮ button** on each inbox card, in the meta row where the close **X** is today.
- The standalone **X is removed**; "Chat schließen" moves into the menu.
- Tapping ⋮ opens a small popover anchored to the button. Same interaction on
  desktop and mobile.
- The card is an `<a>` link — the ⋮ button and every menu action MUST call
  `event.stopPropagation()` + `event.preventDefault()` so they don't navigate into
  the chat (same pattern the current `btn-close-conv` uses).
- Popover closes on: outside click, `Esc`, scroll of the list, or opening another
  card's menu. Only one menu open at a time.

### Menu items (order)
1. **Als gelesen / ungelesen markieren** — toggles the card's read state. Label
   reflects current state.
2. **Auto-Antwort AN/AUS** (nur dieser Chat) — toggles `conversation.auto_respond`.
   Label shows current state.
3. **UMI-Antwort** — generate a reply and preview it inline (see flow below).
   Hidden/disabled when the chat is **escalated** or **UMI is off** for it.
4. **Chat schließen** — sets status to `closed`. Hidden when already closed.

### UMI-Antwort flow — two modes (global setting)

A global admin setting **`inbox_umi_instant_send`** (default **off**) controls whether
the inbox UMI-Antwort action previews or sends instantly. This is the "drop the
seatbelt once UMI is accurate enough" lever.

**Preview mode (default, `inbox_umi_instant_send = off`):**
1. Tap **UMI-Antwort** → the popover swaps to a loading state (spinner).
2. Call `POST /api/conversations/<id>/ai-response` → returns the drafted text +
   `message_id` as a **pending draft** (does not send).
3. Popover shows the drafted text with **[Abbrechen] [Senden]**.
4. **Senden** → `POST /api/messages/<message_id>/approve` → delivers to the guest via
   Smoobu/Gmail. Popover closes, card refreshes.
5. **Abbrechen** → `POST /api/messages/<message_id>/reject` → discards the draft.
   Popover closes.

Keeps a human in the loop (you see the words) while never leaving the inbox.

**Instant mode (`inbox_umi_instant_send = on`):**
- Menu label reads **"UMI-Antwort senden"**.
- One tap → generate (`ai-response`) → immediately `approve` the returned draft →
  delivered. No preview, no confirm. Brief "Gesendet"/"Fehler" toast.

**Safety rails apply in BOTH modes** (see below): the action is hidden on escalated /
AI-off chats, and escalation during generation still flags the chat instead of
sending nonsense. Instant mode never bypasses escalation.

## Actions → endpoints (all already exist)

| Action | Endpoint | Notes |
|---|---|---|
| Mark read/unread | `PATCH /api/conversations/<id>/read` | May need a small `unread` flag if only mark-read is supported today — verify in impl. |
| Toggle auto-respond | `POST /api/conversations/<id>/toggle-auto-respond` | Returns new state. |
| Close chat | `PUT /api/conversations/<id>/status` | Body `{status: 'closed'}`. |
| Generate draft | `POST /api/conversations/<id>/ai-response` | Returns text + `message_id`; clears any prior pending draft. |
| Send draft | `POST /api/messages/<message_id>/approve` | Delivers regardless of auto-respond. |
| Discard draft | `POST /api/messages/<message_id>/reject` | — |

**New backend:**
- `inbox_umi_instant_send` global flag stored in `AISettings` (default `'false'`),
  read by the inbox JS (exposed via the inbox page context or a settings endpoint)
  and toggled from Settings → AI (admin-only). Instant mode is purely a front-end
  sequencing of existing endpoints (generate → approve); no new send path.
- If `ai-response` auto-sends when the chat has `auto_approve` on (no draft to
  preview), add a `draft_only` guard so the preview flow always yields a previewable
  draft. Verify during implementation.

Otherwise zero new endpoints — the menu sequences endpoints that already exist.

## Safety rails (for the send action)
- **UMI-Antwort** item hidden/disabled when the chat is `escalated` or `ai_enabled`
  is false.
- If generation triggers an escalation, UMI's holding message is the draft and the
  chat is flagged — identical to today's auto-respond behavior.
- Send always goes through **approve**, i.e. an explicit human tap — never fires on
  its own.

## Frontend components

Inbox cards render in **two places** — both must get the ⋮ button + menu:
1. Server-side Jinja: `templates/chatbot/inbox.html` (initial load).
2. JS: `createConversationCard()` in `static/js/inbox.js` (polling/dynamic updates).

New JS (in `inbox.js` or a small `inbox-actions.js`):
- `openCardMenu(convId, anchorEl)` / `closeCardMenu()` — one popover element reused,
  repositioned per card (like a lightweight version of the tour tooltip positioning).
- Action handlers: `cardMarkRead`, `cardToggleAutoRespond`, `cardClose`,
  `cardGenerateDraft` → renders preview → `cardSendDraft` / `cardDiscardDraft`.
- After each action, update the affected card in place (reuse existing card-refresh
  path) rather than reloading the whole list.

New CSS in `static/css/style.css`: `.card-menu-btn`, `.card-menu` (popover),
`.card-menu-item`, preview sub-panel. Theme-aware (light/dark).

Settings UI: an admin-only toggle in Settings → AI for `inbox_umi_instant_send`,
with a warning that UMI replies will send from the inbox without a preview.

i18n: new keys under `inbox.menu.*` and `settings.inboxInstantSend.*` in both German
and English.

## Edge cases
- Card is a link → stopPropagation/preventDefault on all menu interactions.
- Menu near the bottom of the viewport → flip above the button.
- Draft generation fails (Ollama down) → show error in the popover, keep it open.
- Two menus: opening one closes any other.
- Closed chats: hide "Chat schließen"; keep read/UMI where sensible.
- Escalated chats: hide "UMI-Antwort".

## Testing
- Backend: existing endpoints already covered; add a test only if a `draft_only`
  flag is introduced.
- Frontend: manual pass on desktop + mobile (Chrome DevTools) — open menu, each
  action, preview + send to a **playtest** conversation (no real guest), Abbrechen
  discards, outside-click/Esc/scroll close, card refreshes in place.
- Instant mode: flip `inbox_umi_instant_send` on, confirm UMI-Antwort sends in one
  tap against a **playtest** chat, and that it stays hidden on an escalated chat.

## Deferred
- Long-press to open the menu on mobile (bonus, later).
- Mark-unread if backend doesn't support it yet.
