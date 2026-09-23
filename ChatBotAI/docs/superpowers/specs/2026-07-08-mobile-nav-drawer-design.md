# Mobile Nav Drawer — Design Spec

**Date:** 2026-07-08
**Status:** approved, ready for implementation plan
**Scope:** One self-contained feature. Replaces the mobile bottom bar with a left slide-in drawer.

## Goal

The mobile bottom bar has 6 fixed slots and is already full (Inbox · E-Mail-Abgleich ·
Team-Leistung · Einstellungen · Hilfe · Konto). It silently drops two real sections that
exist in the desktop sidebar — **Wissensdatenbank** and **Debug** — and has no room for
new features (Problem melden, and whatever comes next). Replace it with an off-canvas
drawer that slides in from the left, giving every section a full-width row with space to
grow.

## Core idea — reuse the desktop sidebar, don't build a new component

On desktop (>768px) the `.sidebar` already holds the complete, correct nav: all 7 nav
items plus online users, theme toggle, language selector, sound/push controls, logout, and
AI status. On mobile it is currently `display:none`, replaced by a separate `.bottom-nav`
and `.account-panel`.

The redesign stops hiding `.sidebar` on mobile and renders it as an off-canvas drawer
instead. **One nav, shared between desktop and mobile — no duplicate menu to keep in
sync.** The `.bottom-nav` and `.account-panel` are deleted; the drawer footer already
covers everything the account panel did (theme, language, sound, push, online users,
logout) and more.

Net effect: a **deletion**, not an addition — two mobile-only components removed, one CSS
transform + a ~15-line toggle added.

## Components

### 1. The drawer (`static/css/style.css`, mobile `@media (max-width: 768px)` block)

Reuse the existing `.sidebar` markup unchanged. Change only its mobile CSS:

- Replace `.sidebar { display: none; }` with an off-canvas panel:
  `position: fixed; top: 0; left: 0; height: 100vh; z-index: 1000;`
  `transform: translateX(-100%); transition: transform 0.25s ease;`
  Keep it scrollable (`overflow-y: auto`) so a long nav + online list fits on small screens.
- Open state: `.sidebar.open { transform: translateX(0); }` with a right-edge `box-shadow`
  for depth.
- Width: comfortable but not full-screen (e.g. `min(78vw, 300px)`) so the backdrop shows
  the drawer is a temporary overlay.

### 2. Backdrop (`base.html` + CSS)

New element `<div class="drawer-backdrop" id="drawerBackdrop"></div>` in `base.html`
(sibling of the sidebar). Full-screen dimmed layer, `z-index: 999` (below drawer, above
content), hidden by default, shown as `.visible` when the drawer is open. Tapping it
closes the drawer. Desktop: never shown (mobile media query only).

### 3. Hamburger trigger (`base.html` + CSS)

New `<button class="mobile-menu-btn" id="mobileMenuBtn" aria-label="Menü">☰</button>`
(FontAwesome `fa-bars`) in `base.html`.

- `position: fixed; top; left; z-index: 1001;` shown **only** on mobile (`display:none` on
  desktop, shown inside the mobile media query).
- **Hidden on the conversation page** by reusing the existing
  `body.conversation-page { ... }` rule that already hides `.mobile-brand-banner`. That
  page has a top-left back arrow (`.back-btn`, `conversation.html:15`) — the correct
  drill-down pattern. Navigation flow on a conversation: back → inbox → ☰.
- Style it to sit cleanly over the `.mobile-brand-banner` (wine `--sidebar-bg`), matching
  the existing mobile header band.

### 4. Toggle JS (~15 lines, inline in `base.html` alongside the existing scripts)

Vanilla, no new file:

- Hamburger click → `sidebar.classList.add('open')` + `backdrop.classList.add('visible')`.
- Backdrop click → close (remove both classes).
- Any `.nav-menu a` (nav link) click → close, so navigating feels immediate.
- `Escape` key → close.
- No open-state persistence: the drawer always starts closed on page load.

## Deletions (the lazy win)

- Remove the `<nav class="bottom-nav">…</nav>` block from `base.html` (and its
  `body.conversation-page .bottom-nav` hide rule).
- Remove the `<div class="account-panel">…</div>` block from `base.html`.
- Remove `.bottom-nav*` and `.account-panel*` CSS (the large mobile media-query sections,
  ~roughly `style.css:2131`–`2330` plus the `<374px` overrides).
- Remove the `accountNavItem` open/close JS for the account panel.
- Drop `.main-content { padding-bottom: calc(72px + safe-area) }` — no bottom bar to clear.
  (Keep a small safe-area bottom padding if needed for gesture bars.)

Verify nothing else references `.bottom-nav`, `bottom-nav-item`, `account-panel`,
`accountNavItem`, or `data-page` before deleting (grep JS + templates).

## Interaction with the Problem Report feature

The Problem Report spec (`2026-07-08-problem-report-design.md`) deferred its **mobile**
entry point "until the separate mobile-nav drawer redesign lands." That is now.

- Problem Report is already planned as a desktop sidebar nav item (`⚠ Problem melden`).
  Because the drawer IS the sidebar, that single nav item serves mobile too.
- **Supersedes** the Problem Report spec's mobile plan: it no longer needs a button in the
  account-panel controls (the account panel is deleted). One drawer nav item covers both
  desktop and mobile. No mobile-specific control.
- No ordering dependency in code, but if both ship together, drop the account-panel entry
  point from the Problem Report work.

## Accessibility

- Hamburger button has `aria-label`. Consider `aria-expanded` toggled with the open state.
- `Escape` closes (covered above).
- Focusable nav links remain in DOM at all times (drawer is transformed off-screen, not
  removed), so no focus-trap machinery needed — keep it lazy.

## Cache versions to bump

- `style.css` — currently v52 → v53 (CSS changes).
- `base.html` version comment / query string if used for cache-busting the inline script.
- No JS-file version bumps (toggle is inline, not in `app.js`/`inbox.js`/etc.).

## Deliberately lazy / out of scope

- **No swipe-to-open gesture** — tap the hamburger. Add a touch handler later only if the
  team asks.
- **No animated hamburger→X morph** — static `fa-bars` icon.
- **No open-state persistence** across navigations — always starts closed.
- **No focus trap / inert background** — links stay in DOM; overkill for this app.
- **No slim hybrid bottom bar** — full drawer only (decided during brainstorming).

## One check to leave behind

Manual Playwright smoke check (pure CSS/DOM toggle, no unit-testable logic):

1. Resize viewport to 375px → `.mobile-menu-btn` visible, `.bottom-nav` gone.
2. Tap hamburger → `.sidebar` has `.open`, backdrop visible, nav readable.
3. Tap a nav link → navigates and drawer closes.
4. Open a conversation → hamburger hidden, back arrow present.
