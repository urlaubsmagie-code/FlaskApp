# Problem Report ("Problem melden") — Design Spec

**Date:** 2026-07-08
**Status:** approved, ready for implementation plan
**Scope:** One self-contained feature. Mobile-nav redesign is explicitly OUT (tracked separately).

## Goal

Let the team log things they notice while using the app ("guest wrote but no message
showed", "search slow on mobile", ideas). Reports collect on an admin-only page for triage.

## Data — new table `ProblemReport` (migration `p20`)

`down_revision = 'p19_notion_source'` (current head on `feat/notion-knowledge-sync`).

| field | type | notes |
|---|---|---|
| `id` | int PK | |
| `created_at` | datetime | default `utcnow` |
| `user_id` | FK → User | reporter (login required, always set) |
| `conversation_id` | FK → Conversation, nullable | auto-set from per-chat button; null for general reports |
| `category` | string | one of the 4 fixed keys below |
| `message` | text | free text, required, non-empty |
| `page_url` | string, nullable | where they were, for context |
| `status` | string | `open` / `resolved`, default `open` |
| `resolved_at` | datetime, nullable | set on resolve |
| `resolved_by` | FK → User, nullable | admin who resolved |

Follow the existing model style in `models.py` (see `KnowledgeEntry` / `Message` as templates).

**Categories** — fixed 4-item list, no admin config. Store the stable key, translate in UI:
`missing_message` · `bug` · `idea` · `other`.

## Submit — one shared modal in `base.html`

A single modal (available on every page because it lives in `base.html`), reused by all
three entry points. Textarea + category `<select>` + submit → `POST /chatbot/api/problem-reports`
→ toast "Danke, gemeldet!", modal closes, no navigation.

Entry points:
1. **Desktop sidebar** — new nav item `⚠ Problem melden` in the `.nav-menu` list (`base.html:35`).
   Opens the modal (button/JS, not an `<a href>`).
2. **Mobile** — button in the account panel controls (`base.html:199` `.account-panel-controls`).
   Deliberately NOT in the bottom bar (already 6 items, full). Opens the same modal.
3. **Per-chat** — `⚠ Problem melden` button next to the sync button in the conversation header
   (`conversation.html:87` desktop) and in the mobile overflow menu (`conversation.html:129`).
   Pre-fills `conversation_id` (from the page's conversation id) and `page_url`.

Modal JS: minimal vanilla (open/close/submit via `fetch`), added inline in `base.html` alongside
the existing badge-refresh script, or a tiny block — no new JS file needed.

## Review — admin-only page `/chatbot/problem-reports`

- New sidebar nav item `⚠ Problem-Berichte`, admin-only (wrap in the same
  `{% if current_user.is_admin %}` block as Debug, `base.html:74`).
- **Badge** = open count. Reuse the exact pattern already wired for E-Mail-Abgleich
  (`base.html:259` `refreshEmailReviewBadge` + `/api/email-review/pending-count`): clone it for
  `/api/problem-reports/pending-count`.
- New template `templates/chatbot/problem_reports.html`. List rows: status · reporter ·
  relative time · linked chat (link to conversation if `conversation_id` set) · category label ·
  message. One button per row toggles `open`↔`resolved`.

## Routes (4, all in `routes.py`)

| method + path | guard | purpose |
|---|---|---|
| `POST /api/problem-reports` | `@login_required` | create; body `{message, category, conversation_id?, page_url?}`; validate `message` non-empty and `category` in the 4 keys |
| `GET /problem-reports` | `@admin_required` (`routes.py:18`) | render review page |
| `POST /api/problem-reports/<id>/resolve` | `@admin_required` | toggle status, set/clear `resolved_at`/`resolved_by` |
| `GET /api/problem-reports/pending-count` | `@login_required` | `{count: <open count>}` for the badge |

## i18n

New keys in `static/js/i18n.js` (de default + en), e.g. `problem.report`, `problem.reports`,
`problem.placeholder`, `problem.thanks`, `problem.category.missing_message` / `.bug` / `.idea` /
`.other`, `problem.status.open` / `.resolved`. Bump the `i18n.js` cache version (currently v28).

## Cache versions to bump on implementation
`base.html` `style.css` (currently v52) if CSS added; `i18n.js` v28. No change to inbox/conversation
JS versions unless the per-chat button needs conversation.js (it can be inline `onclick` → likely none).

## Deliberately lazy / out of scope
- **No mobile bottom-bar change.** Global mobile entry sits in the account panel until the
  separate mobile-nav drawer redesign lands; then "Problem melden" moves into the drawer.
- **No modal component framework** — one hand-rolled modal, vanilla JS.
- **No category admin config** — 4 hard-coded keys.
- **No edit/delete of reports, no comments/threads** — just create + resolve toggle. Add later
  only if triage volume demands it.
- **No email/push on submit** — the badge + page cover it. Add a push hook later if reports get missed.

## One check to leave behind
`test_problem_report.py`: assert `POST /api/problem-reports` with empty `message` → 400, with valid
body → 201 + row persisted with `status='open'`; and `/pending-count` reflects open count.
(Follows the existing `tests/` style, e.g. `test_email_reconcile.py`.)
