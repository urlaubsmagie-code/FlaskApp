# Mobile Nav Drawer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the full mobile bottom bar with a left slide-in drawer that reuses the existing desktop sidebar, so every nav section (including the currently-dropped Knowledge Base and Debug) is reachable on mobile with room to grow.

**Architecture:** On mobile (≤768px) the `.sidebar` stops being `display:none` and becomes an off-canvas drawer (`translateX(-100%)` → `.open` slides it in). A fixed hamburger button opens it; a dimmed backdrop + Esc + nav-link-tap close it. The `.bottom-nav` and `.account-panel` — a full duplicate of the sidebar footer — are deleted. One nav, shared desktop + mobile.

**Tech Stack:** Jinja2 templates, vanilla CSS (`style.css`), vanilla JS inline in `base.html`. No new files, no libraries. Playwright MCP for the smoke check.

## Global Constraints

- German-first UI; all user-facing strings in German (English via i18n).
- Reuse existing `.sidebar` markup as the drawer — do NOT create a second nav menu.
- Do NOT touch `.mobile-overflow-btn` / `.mobile-overflow-menu` — that is the **conversation-page action menu**, unrelated to the bottom bar.
- Do NOT touch `.mobile-brand-banner` — the top wine band stays.
- Hamburger is hidden on the conversation page (reuse the existing `body.conversation-page` hide pattern); that page uses its own back arrow.
- Bump `style.css` cache version `v52` → `v53` in `base.html:20` when CSS changes.
- This is pure CSS/DOM/template work — no unit-testable logic. Each task is verified with a browser check (Playwright MCP), not pytest.
- Wine palette var: `--sidebar-bg` (`#4A1520`).

---

### Task 1: Drawer CSS + hamburger + backdrop + toggle JS (additive, old bottom bar still present)

Make the sidebar open as a mobile drawer. Leave the old `.bottom-nav`/`.account-panel` in place for now so the drawer can be verified before anything is deleted. Transitionally both exist on mobile — that is fine and intentional.

**Files:**
- Modify: `templates/chatbot/base.html` — add hamburger button, backdrop div, close-X in sidebar header, inline toggle JS; bump CSS version.
- Modify: `static/css/style.css` — desktop-default hidden rules + mobile drawer rules.

**Interfaces:**
- Produces (DOM ids the JS binds): `#mobileMenuBtn` (hamburger), `#drawerBackdrop` (backdrop), `#drawerCloseBtn` (close X). Drawer element is the existing `.sidebar`; open state = class `open` on it and class `visible` on the backdrop.

- [ ] **Step 1: Add the hamburger button** — in `templates/chatbot/base.html`, immediately after `<div class="app-container">` (currently line 25) and before `<nav class="sidebar">`:

```html
        <!-- Mobile drawer trigger (mobile only, hidden on desktop + conversation page via CSS) -->
        <button class="mobile-menu-btn" id="mobileMenuBtn" aria-label="Menü öffnen" aria-expanded="false">
            <i class="fas fa-bars"></i>
        </button>
```

- [ ] **Step 2: Add a close-X inside the sidebar header** — in `templates/chatbot/base.html`, inside `<div class="sidebar-header">` (after the `<div class="logo">…</div>` block, currently around line 32), add:

```html
                <button class="drawer-close-btn" id="drawerCloseBtn" aria-label="Menü schließen">&times;</button>
```

- [ ] **Step 3: Add the backdrop** — in `templates/chatbot/base.html`, immediately after the sidebar `</nav>` (currently line 149):

```html
        <!-- Drawer backdrop (mobile only) -->
        <div class="drawer-backdrop" id="drawerBackdrop"></div>
```

- [ ] **Step 4: Add desktop-default hidden rules** — in `static/css/style.css`, next to the existing base `.bottom-nav { display: none; }` block (around line 2057), add:

```css
.mobile-menu-btn { display: none; }
.drawer-backdrop { display: none; }
.drawer-close-btn { display: none; }
```

- [ ] **Step 5: Add mobile drawer rules** — in `static/css/style.css`, inside `@media (max-width: 768px)` (block starts line 2080). Replace the existing rule

```css
    .sidebar {
        display: none;
    }
```

with:

```css
    /* --- Sidebar becomes an off-canvas drawer --- */
    .sidebar {
        display: flex;
        flex-direction: column;
        position: fixed;
        top: 0;
        left: 0;
        height: 100vh;
        width: min(80vw, 300px);
        z-index: 1000;
        transform: translateX(-100%);
        transition: transform 0.25s ease;
        overflow-y: auto;
        box-shadow: 2px 0 12px rgba(0, 0, 0, 0.25);
    }
    .sidebar.open {
        transform: translateX(0);
    }

    .drawer-backdrop {
        display: block;
        position: fixed;
        inset: 0;
        background: rgba(0, 0, 0, 0.45);
        z-index: 999;
        opacity: 0;
        visibility: hidden;
        transition: opacity 0.25s ease;
    }
    .drawer-backdrop.visible {
        opacity: 1;
        visibility: visible;
    }

    .mobile-menu-btn {
        display: flex;
        position: fixed;
        top: 8px;
        left: 8px;
        z-index: 1001;
        width: 44px;
        height: 44px;
        align-items: center;
        justify-content: center;
        background: var(--sidebar-bg, #4A1520);
        color: #fff;
        border: none;
        border-radius: 8px;
        font-size: 1.2rem;
        cursor: pointer;
    }
    body.conversation-page .mobile-menu-btn {
        display: none;
    }

    .drawer-close-btn {
        display: block;
        margin-left: auto;
        background: none;
        border: none;
        color: #fff;
        font-size: 1.8rem;
        line-height: 1;
        cursor: pointer;
        padding: 0 4px;
    }
```

- [ ] **Step 6: Add the toggle JS** — in `templates/chatbot/base.html`, inside the existing trailing `<script>` block (the one with `refreshEmailReviewBadge`, starting line 258), append this IIFE before the closing `</script>`:

```javascript
    (function initNavDrawer() {
      var btn = document.getElementById('mobileMenuBtn');
      var sidebar = document.querySelector('.sidebar');
      var backdrop = document.getElementById('drawerBackdrop');
      var closeBtn = document.getElementById('drawerCloseBtn');
      if (!btn || !sidebar || !backdrop) return;
      function open() {
        sidebar.classList.add('open');
        backdrop.classList.add('visible');
        btn.setAttribute('aria-expanded', 'true');
      }
      function close() {
        sidebar.classList.remove('open');
        backdrop.classList.remove('visible');
        btn.setAttribute('aria-expanded', 'false');
      }
      btn.addEventListener('click', open);
      backdrop.addEventListener('click', close);
      if (closeBtn) closeBtn.addEventListener('click', close);
      sidebar.querySelectorAll('.nav-menu a').forEach(function (a) {
        a.addEventListener('click', close);
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') close();
      });
    })();
```

- [ ] **Step 7: Bump the CSS cache version** — in `templates/chatbot/base.html:20`, change `css/style.css') }}?v=52` to `?v=53`.

- [ ] **Step 8: Verify in browser (Playwright MCP)** — with the dev server running (`python -m ChatBotAI.run`), log in, open the inbox:
  - Resize viewport to 375×800 (`browser_resize`).
  - `browser_snapshot`: the `☰` hamburger is visible top-left; the old bottom bar is still present (not yet removed — expected).
  - Click the hamburger → snapshot: sidebar has class `open`, backdrop visible, all 7 nav items readable (Posteingang, Team-Leistung, Einstellungen, Wissensdatenbank, E-Mail-Abgleich, Hilfe, and Debug if admin).
  - Click the backdrop → drawer closes. Re-open, press `Escape` → closes. Re-open, click a nav link → navigates and closes.
  - Open a conversation → hamburger is hidden, back arrow present.
  Expected: all pass. If the sidebar renders full-width or won't slide, re-check Step 5 selectors.

- [ ] **Step 9: Commit**

```bash
git add templates/chatbot/base.html static/css/style.css
git commit -m "feat(mobile-nav): add slide-in drawer reusing the desktop sidebar

Hamburger + backdrop + toggle open the existing .sidebar as an off-canvas
drawer on mobile. Bottom bar still present; removed in the next commit.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Delete the bottom bar + account panel

Now that the drawer is the mobile nav, remove the two redundant mobile-only components and their dead JS. The drawer footer already provides theme, language, sound, push, online users, and logout.

**Files:**
- Modify: `templates/chatbot/base.html` — delete `<nav class="bottom-nav">` and `<div class="account-panel">` blocks.
- Modify: `static/css/style.css` — delete `.bottom-nav*` and `.account-panel*` rules; trim `.main-content` bottom padding.
- Modify: `static/js/app.js` — delete the dead `accountNavItem`/`accountPanel` toggle block.

**Interfaces:**
- Consumes: the drawer from Task 1 (must be working before deleting the fallback bottom bar).

- [ ] **Step 1: Confirm nothing else depends on the doomed markup** — run:

```bash
grep -rn "bottom-nav\|account-panel\|accountNavItem\|accountPanel\|data-page=\"account\"" static/js templates
```

Expected remaining hits after this task: only the null-guarded `mobile*` element reads in `app.js` (`mobileOnlineList`, `mobileSoundToggleBtn`, etc.) which are harmless no-ops once the elements are gone — leave them. If any NON-guarded consumer appears, stop and reassess.

- [ ] **Step 2: Delete the bottom-nav markup** — in `templates/chatbot/base.html`, remove the entire `<!-- Bottom Navigation … --> <nav class="bottom-nav"> … </nav>` block (currently lines ~163–189).

- [ ] **Step 3: Delete the account-panel markup** — in `templates/chatbot/base.html`, remove the entire `<!-- Account Panel … --> <div class="account-panel" id="accountPanel"> … </div>` block (currently lines ~191–242).

- [ ] **Step 4: Delete the dead toggle JS** — in `static/js/app.js`, remove the block that binds `accountNavItem` / `accountPanel` (currently lines ~925–943, the `const accountNavItem = …` through its closing `}`). Leave the null-guarded `mobile*` reads in `updateSoundToggleUI`, `updateBrowserNotifyToggleUI`, `updateThemeIcon`, and the online-users updater — they no-op safely.

- [ ] **Step 5: Delete the CSS** — in `static/css/style.css`:
  - Remove the base rules `.bottom-nav { display: none; }` (~2057) and `.account-panel { display: none; }` (~2073). **Keep** `.mobile-brand-banner`, `.mobile-overflow-btn`, `.mobile-overflow-menu`.
  - In `@media (max-width: 768px)`: remove the `/* --- Bottom Navigation --- */` rules (all `.bottom-nav`, `.bottom-nav-item`, `body.conversation-page .bottom-nav`) and the `/* --- Account Panel --- */` rules (all `.account-panel*`). **Stop before** `/* --- Conversation Overflow Menu --- */` (~2329) — keep that block.
  - In `@media (max-width: 374px)`: remove the `.bottom-nav-item` and `.bottom-nav-item i` overrides (~2754–2760).

- [ ] **Step 6: Trim the bottom padding** — in `static/css/style.css`, the mobile `.main-content` rule (~2124) has `padding-bottom: calc(72px + env(safe-area-inset-bottom, 0px));` (space for the now-gone bar). Change to:

```css
        padding-bottom: calc(12px + env(safe-area-inset-bottom, 0px));
```

- [ ] **Step 7: Bump the CSS cache version** — `?v=53` → `?v=54` in `templates/chatbot/base.html:20`.

- [ ] **Step 8: Verify in browser (Playwright MCP)** — dev server running, 375×800:
  - Inbox: no bottom bar; content runs to the bottom; hamburger opens the drawer.
  - From the drawer footer, toggle Dark Mode (page theme flips), toggle Sound and Push (icons change), switch language DE→EN (nav labels change), see the Online list, and Logout works.
  - Every section reachable: tap each of the 7 nav items.
  Expected: all pass, no console errors about missing elements.

- [ ] **Step 9: Commit**

```bash
git add templates/chatbot/base.html static/css/style.css static/js/app.js
git commit -m "feat(mobile-nav): remove bottom bar + account panel, drawer is now sole mobile nav

Deletes the redundant .bottom-nav and .account-panel (a full duplicate of the
sidebar footer) plus their dead toggle JS. Knowledge Base + Debug are now
reachable on mobile. Keeps the conversation-page overflow menu untouched.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Deliberately out of scope (from the spec)

- No swipe-to-open gesture, no animated hamburger→X morph, no open-state persistence, no focus-trap/`inert`, no body-scroll-lock while open. Add later only if the team asks.
- The `mobile*` null-guarded reads in `app.js` are left in place deliberately — deleting 6 harmless no-op guards is churn with no benefit. `// ponytail: harmless no-ops after account-panel removal` if a note is wanted.
- Problem Report's mobile entry point is handled in the separate Problem Report plan (it becomes one drawer nav item), not here.

## Self-Review

- **Spec coverage:** drawer CSS (Task 1 §5) · backdrop (§3/§5) · hamburger + conversation-page hide (§1/§5) · toggle JS incl. Esc + link-close (§6) · deletions of bottom-nav/account-panel/dead JS (Task 2) · Problem Report interaction (noted, deferred to its plan) · a11y aria-label/aria-expanded (§1/§6) · cache bumps (both tasks) · smoke check (both §8). All covered.
- **Placeholder scan:** none — every step has concrete code/commands.
- **Type/id consistency:** `#mobileMenuBtn`, `#drawerBackdrop`, `#drawerCloseBtn`, classes `open`/`visible` used identically in markup, CSS, and JS across both tasks.
