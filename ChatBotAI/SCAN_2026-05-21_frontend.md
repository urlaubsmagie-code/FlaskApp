# Frontend Security & UX Audit — 2026-05-21

## Summary
17 issues identified — CRITICAL: 2, HIGH: 4, MEDIUM: 6, LOW: 4, INFO: 1

---

## CRITICAL

### [CRITICAL] Unescaped HTML from search results (XSS)
- **File:** static/js/inbox.js:522
- **Issue:** `snippetEl.innerHTML = result.first_snippet;` assumes server-side sanitization without client-side defense.
- **Impact:** If backend sanitization regresses, search snippets become XSS vectors.
- **Suggested approach:** Defense-in-depth `escapeHtml()` + CSP `script-src`.

### [CRITICAL] Unsanitized error messages in AI banner (XSS)
- **File:** static/js/conversation.js:482
- **Issue:** `banner.innerHTML = \`<i>...</i> ${message}\`;` — API error string injected unescaped.
- **Impact:** Backend returning HTML in `data.error` would execute as code.
- **Suggested approach:** Use `textContent` or `escapeHtml(message)`.

## HIGH

### [HIGH] Search snippet sanitization trust gap
- **File:** static/js/inbox.js:561-581
- **Issue:** Comments claim server sanitizes, no client-side fallback.
- **Suggested approach:** Apply `escapeHtml()` defensively.

### [HIGH] Event listener duplication on polling (memory leak)
- **File:** static/js/inbox.js:398-408
- **Issue:** Filter button listeners added on DOMContentLoaded; `updateInboxList()` re-renders without `removeEventListener`.
- **Impact:** Listeners accumulate over long sessions → CPU spike.
- **Suggested approach:** Event delegation on `.filter-bar`.

### [HIGH] Polling interval stacking on rapid visibility changes
- **File:** static/js/inbox.js:1056; static/js/polling.js:43-54
- **Issue:** `PollingManager.start()` lacks `if (this.isPolling) return;` idempotent guard.
- **Suggested approach:** Add guard clause.

### [HIGH] Message send double-click race
- **File:** static/js/conversation.js:339-368
- **Issue:** `tempId = Date.now()` is ms-unique; slow network allows duplicate sends; re-enable in `.finally()` allows re-entry.
- **Suggested approach:** `sendInProgress` flag; return early.

## MEDIUM

### [MEDIUM] Missing CSRF tokens on all state-changing fetch() calls
- **Files:** conversation.js, inbox.js, app.js (all fetch POST/PUT/PATCH/DELETE)
- **Impact:** CSRF possible if user visits malicious page while logged in.
- **Suggested approach:** Inject CSRF token + validate server-side (Flask-WTF).

### [MEDIUM] Excessive `!important` in CSS (23 occurrences)
- **File:** static/css/style.css:1091-3784
- **Issue:** Blocks dark-mode wine palette overrides.
- **Suggested approach:** Restructure specificity, remove `!important`.

### [MEDIUM] Icon-only buttons missing aria-label
- **File:** templates/chatbot/conversation.html:65-98
- **Issue:** 12+ buttons have `title` but no `aria-label`.
- **Suggested approach:** Add `aria-label` per button.

### [MEDIUM] Modals don't manage focus stack
- **File:** static/js/conversation.js (no trap / returnFocus)
- **Suggested approach:** Store `lastFocusedElement`, restore on close.

### [MEDIUM] Polling ignores prefers-reduced-motion
- **File:** static/js/inbox.js:786; polling.js
- **Suggested approach:** Slow to 30s when reduced-motion is set.

### [MEDIUM] Hardcoded English in loading states
- **File:** static/js/inbox.js:916, 1000
- **Suggested approach:** Use i18n keys.

## LOW

### [LOW] Cache version mismatch (manual maintenance)
- **File:** templates/chatbot/base.html:20,243-244
- **Suggested approach:** Git hash or mtime based versioning.

### [LOW] Service worker has no offline caching
- **File:** static/sw.js
- **Suggested approach:** Add install + fetch handlers with cache strategy.

### [LOW] Inbox filters not persisted on back navigation
- **Suggested approach:** sessionStorage + restore.

### [LOW] viewport-fit=cover without safe-area-inset CSS
- **File:** templates/chatbot/base.html:5; static/css/style.css
- **Suggested approach:** Apply `env(safe-area-inset-*)` paddings.

## INFO
Codebase is generally well-structured; `escapeHtml()` is used in most contexts; main gaps are the two innerHTML sinks above and missing CSRF infrastructure.
