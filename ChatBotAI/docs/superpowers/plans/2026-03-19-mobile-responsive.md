# Mobile Responsive Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the ChatBotAI app fully usable on mobile phones (360px+) with bottom navigation, full-screen conversations, and touch-friendly targets.

**Architecture:** CSS-first approach with a single 768px breakpoint. Sidebar hidden on mobile, replaced by a fixed bottom nav bar. Conversation page goes full-screen (bottom nav hidden, back button in header). Minimal JS added for overflow menu and account panel toggles.

**Tech Stack:** CSS media queries, existing CSS variables, vanilla JS, Jinja2 templates, Font Awesome icons.

**Spec:** `docs/superpowers/specs/2026-03-19-mobile-responsive-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `templates/chatbot/base.html` | Modify | viewport-fit, body_class block, bottom nav HTML, account panel HTML |
| `templates/chatbot/conversation.html` | Modify | body_class override, overflow menu HTML |
| `static/css/style.css` | Modify | Bottom nav styles, account panel styles, overflow menu styles, rewrite 768px media query |
| `static/js/app.js` | Modify | Bottom nav active state, account panel toggle, icon sync for mobile toggles, toast mobile offset |
| `static/js/conversation.js` | Modify | Overflow menu toggle + click-outside |
| `static/js/i18n.js` | Modify | New translation keys |
| All templates with `?v=` | Modify | Bump cache versions |

---

## Task 1: Base Template — Viewport, Body Class Block, Bottom Nav HTML

**Files:**
- Modify: `templates/chatbot/base.html`

- [ ] **Step 1: Update viewport meta tag**

In `base.html:5`, change:
```html
<meta name="viewport" content="width=device-width, initial-scale=1.0">
```
to:
```html
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
```

- [ ] **Step 2: Add body_class block**

In `base.html:24`, change:
```html
<body>
```
to:
```html
<body class="{% block body_class %}{% endblock %}">
```

- [ ] **Step 3: Add bottom nav and account panel HTML**

In `base.html`, after line 119 (`</main>`) and before `</div>` (closing `.app-container`), add:
```html
        <!-- Bottom Navigation (mobile only, hidden by CSS on desktop) -->
        <nav class="bottom-nav">
            <a href="{{ url_for('chatbot.index') }}" class="bottom-nav-item {% if request.endpoint == 'chatbot.index' %}active{% endif %}" data-page="inbox">
                <i class="fas fa-inbox"></i>
                <span data-i18n="nav.inbox">Posteingang</span>
            </a>
            <a href="{{ url_for('chatbot.statistics') }}" class="bottom-nav-item {% if request.endpoint == 'chatbot.statistics' %}active{% endif %}" data-page="statistics">
                <i class="fas fa-chart-bar"></i>
                <span data-i18n="nav.statistics">Statistiken</span>
            </a>
            <a href="{{ url_for('chatbot.settings') }}" class="bottom-nav-item {% if request.endpoint == 'chatbot.settings' %}active{% endif %}" data-page="settings">
                <i class="fas fa-cog"></i>
                <span data-i18n="nav.settings">Einstellungen</span>
            </a>
            <a href="#" class="bottom-nav-item" data-page="account" id="accountNavItem">
                <i class="fas fa-user"></i>
                <span data-i18n="nav.account">Konto</span>
            </a>
        </nav>

        <!-- Account Panel (mobile only, toggled by JS) -->
        <div class="account-panel" id="accountPanel">
            {% if current_user.is_authenticated %}
            <div class="account-panel-user">
                <span class="user-avatar">{{ current_user.display_name[0]|upper }}</span>
                <span class="account-panel-name">{{ current_user.display_name }}</span>
            </div>
            {% endif %}
            <div class="account-panel-controls">
                <button id="mobileThemeToggleBtn" class="account-panel-btn" onclick="toggleTheme()">
                    <i class="fas fa-moon"></i>
                    <span data-i18n="account.darkMode">Dunkelmodus</span>
                </button>
                <button id="mobileSoundToggleBtn" class="account-panel-btn" onclick="toggleNotificationSound()">
                    <i class="fas fa-volume-up" id="mobileSoundToggleIcon"></i>
                    <span data-i18n="account.sound">Sound</span>
                </button>
                <button id="mobilePushToggleBtn" class="account-panel-btn" onclick="toggleBrowserNotifications()">
                    <i class="fas fa-bell" id="mobilePushToggleIcon"></i>
                    <span data-i18n="account.push">Push</span>
                </button>
                <div class="account-panel-language">
                    <select id="mobileLanguageSelector" onchange="i18n.setLanguage(this.value)">
                        <option value="de">Deutsch</option>
                        <option value="en">English</option>
                    </select>
                </div>
            </div>
            {% if current_user.is_authenticated %}
            <form action="{{ url_for('chatbot.logout') }}" method="POST" class="account-panel-logout">
                <button type="submit" class="account-panel-btn account-panel-logout-btn">
                    <i class="fas fa-sign-out-alt"></i>
                    <span data-i18n="account.logout">Abmelden</span>
                </button>
            </form>
            {% endif %}
        </div>
```

- [ ] **Step 4: Verify template renders**

Run the dev server and load any page. Confirm:
- No template errors
- Bottom nav and account panel HTML are in the DOM (inspect elements) but not visible on desktop
- Existing sidebar works as before

- [ ] **Step 5: Commit**

```bash
git add templates/chatbot/base.html
git commit -m "feat(mobile): add viewport-fit, body_class block, bottom nav and account panel HTML"
```

---

## Task 2: Conversation Template — Body Class, Overflow Menu

**Files:**
- Modify: `templates/chatbot/conversation.html`

- [ ] **Step 1: Add body_class override**

At the top of `conversation.html`, after line 1 (`{% extends "chatbot/base.html" %}`), add:
```html
{% block body_class %}conversation-page{% endblock %}
```

- [ ] **Step 2: Add overflow menu to conversation header**

In `conversation.html`, after the closing `</div>` of `.conversation-actions` (line 54), add:
```html
        <button class="mobile-overflow-btn" aria-label="Menu" id="mobileOverflowBtn">
            <i class="fas fa-ellipsis-v"></i>
        </button>
        <div class="mobile-overflow-menu" id="mobileOverflowMenu">
            <div class="overflow-menu-item">
                <select id="mobilePropertySelector" class="mobile-property-selector" onchange="assignProperty(this.value)"
                    title="Unterkunft zuweisen">
                    <option value="" data-i18n="conversation.property.none">-- Unterkunft --</option>
                </select>
            </div>
            <button class="overflow-menu-item" onclick="toggleAI()" id="mobileAiToggleBtn">
                <i class="fas fa-robot"></i>
                <span>KI: <span class="toggle-status" id="mobileAiStatus">{{ 'AN' if conversation.ai_enabled else 'AUS' }}</span></span>
            </button>
            <button class="overflow-menu-item" onclick="toggleAutoRespond()" id="mobileAutoRespondBtn" {% if not conversation.ai_enabled %}disabled{% endif %}>
                <i class="fas fa-bolt"></i>
                <span>Auto: <span id="mobileAutoRespondStatus">{{ 'AN' if conversation.auto_respond else 'AUS' }}</span></span>
            </button>
            <a href="{{ url_for('chatbot.guest_profile', guest_id=guest.id) }}" class="overflow-menu-item">
                <i class="fas fa-user"></i>
                <span data-i18n="conversation.guest.profile">Gästeprofil</span>
            </a>
        </div>
```

- [ ] **Step 3: Verify template renders**

Load a conversation page. Confirm:
- `<body class="conversation-page">` in the DOM
- Overflow menu elements are in the DOM but not visible on desktop
- Existing conversation functionality unchanged

- [ ] **Step 4: Commit**

```bash
git add templates/chatbot/conversation.html
git commit -m "feat(mobile): add conversation-page body class and overflow menu HTML"
```

---

## Task 3: CSS — Bottom Nav, Account Panel, Overflow Menu (Desktop Hidden)

**Files:**
- Modify: `static/css/style.css`

- [ ] **Step 1: Add desktop-hidden base styles**

At the end of `style.css` (before the existing `/* Responsive */` section at line 1805), add:
```css
/* ============================================================================
   Mobile Components (hidden on desktop, shown via media query)
   ============================================================================ */
.bottom-nav {
    display: none;
}

.mobile-overflow-btn {
    display: none;
}

.mobile-overflow-menu {
    display: none;
}

.account-panel {
    display: none;
}
```

- [ ] **Step 2: Verify desktop unchanged**

Load the app on desktop (>768px). Confirm none of the new elements are visible and all existing layouts are unchanged.

- [ ] **Step 3: Commit**

```bash
git add static/css/style.css
git commit -m "feat(mobile): add desktop-hidden base styles for mobile components"
```

---

## Task 4: CSS — Rewrite Mobile Media Query

**Files:**
- Modify: `static/css/style.css`

- [ ] **Step 1: Replace the existing 768px media query**

Replace the block at lines 1808-1863:
```css
@media (max-width: 768px) {
    .sidebar {
        width: 60px;
    }
    /* ... all existing rules ... */
}
```

With the full mobile media query:
```css
@media (max-width: 768px) {
    /* --- Hide sidebar, show bottom nav --- */
    .sidebar {
        display: none;
    }

    .main-content {
        margin-left: 0;
        padding: 12px;
        padding-bottom: calc(72px + env(safe-area-inset-bottom, 0px));
    }

    /* --- Bottom Navigation --- */
    .bottom-nav {
        display: flex;
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        height: 56px;
        padding-bottom: env(safe-area-inset-bottom, 0px);
        background: var(--card-bg);
        border-top: 1px solid var(--border-color);
        z-index: 100;
        justify-content: space-around;
        align-items: center;
    }

    .bottom-nav-item {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 2px;
        color: var(--text-secondary);
        text-decoration: none;
        font-size: 0.7rem;
        padding: 8px 12px;
        min-height: 44px;
        justify-content: center;
    }

    .bottom-nav-item.active {
        color: var(--primary-color);
    }

    .bottom-nav-item i {
        font-size: 1.2rem;
    }

    /* --- Conversation Page: full-screen, no bottom nav --- */
    body.conversation-page .bottom-nav {
        display: none;
    }

    body.conversation-page .main-content {
        padding-bottom: 0;
    }

    body.conversation-page .conversation-container {
        height: 100vh;
        height: 100dvh;
    }

    /* --- Account Panel --- */
    .account-panel {
        display: none;
        position: fixed;
        bottom: 56px;
        bottom: calc(56px + env(safe-area-inset-bottom, 0px));
        left: 0;
        right: 0;
        background: var(--card-bg);
        border-top: 1px solid var(--border-color);
        z-index: 101;
        padding: 16px;
        box-shadow: var(--shadow-lg);
    }

    .account-panel.open {
        display: block;
    }

    .account-panel-user {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 12px;
        padding-bottom: 12px;
        border-bottom: 1px solid var(--border-color);
    }

    .account-panel-name {
        font-weight: 600;
        color: var(--text-primary);
    }

    .account-panel-controls {
        display: flex;
        flex-direction: column;
        gap: 4px;
    }

    .account-panel-btn {
        display: flex;
        align-items: center;
        gap: 12px;
        width: 100%;
        padding: 12px;
        min-height: 44px;
        background: none;
        border: none;
        border-radius: var(--border-radius);
        color: var(--text-primary);
        font-size: 0.875rem;
        cursor: pointer;
        text-align: left;
    }

    .account-panel-btn:hover {
        background: var(--bg-primary);
    }

    .account-panel-btn i {
        width: 20px;
        text-align: center;
        color: var(--text-secondary);
    }

    .account-panel-language {
        padding: 4px 12px;
    }

    .account-panel-language select {
        width: 100%;
        padding: 8px 12px;
        min-height: 44px;
        border: 1px solid var(--border-color);
        border-radius: var(--border-radius);
        background: var(--bg-secondary);
        color: var(--text-primary);
        font-size: 0.875rem;
    }

    .account-panel-logout {
        margin-top: 8px;
        padding-top: 8px;
        border-top: 1px solid var(--border-color);
    }

    .account-panel-logout-btn {
        color: var(--danger-color);
    }

    .account-panel-logout-btn i {
        color: var(--danger-color);
    }

    /* --- Conversation Overflow Menu --- */
    .conversation-actions {
        display: none;
    }

    .mobile-overflow-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 44px;
        height: 44px;
        background: none;
        border: none;
        color: var(--text-primary);
        font-size: 1.2rem;
        cursor: pointer;
        border-radius: var(--border-radius);
    }

    .mobile-overflow-btn:hover {
        background: var(--bg-primary);
    }

    .mobile-overflow-menu {
        position: absolute;
        right: 12px;
        top: 100%;
        background: var(--card-bg);
        border: 1px solid var(--border-color);
        border-radius: var(--border-radius);
        box-shadow: var(--shadow-lg);
        z-index: 200;
        min-width: 220px;
        overflow: hidden;
    }

    .mobile-overflow-menu.open {
        display: block;
    }

    .overflow-menu-item {
        display: flex;
        align-items: center;
        gap: 12px;
        width: 100%;
        padding: 12px 16px;
        min-height: 44px;
        background: none;
        border: none;
        color: var(--text-primary);
        font-size: 0.875rem;
        cursor: pointer;
        text-decoration: none;
        text-align: left;
    }

    .overflow-menu-item:hover {
        background: var(--bg-primary);
    }

    .overflow-menu-item i {
        width: 20px;
        text-align: center;
        color: var(--text-secondary);
    }

    .overflow-menu-item select {
        flex: 1;
        padding: 6px 8px;
        border: 1px solid var(--border-color);
        border-radius: var(--border-radius);
        background: var(--bg-secondary);
        color: var(--text-primary);
        font-size: 0.8125rem;
    }

    /* --- Back button (show on mobile) --- */
    .back-btn {
        min-height: 44px;
        min-width: 44px;
    }

    /* --- Conversation header --- */
    .conversation-header-bar {
        position: relative;
    }

    /* --- Messages --- */
    .message {
        max-width: 90%;
    }

    /* --- Page Header (inbox etc.) --- */
    .page-header {
        flex-wrap: wrap;
        gap: 8px;
    }

    .header-actions {
        width: 100%;
        flex-wrap: wrap;
        gap: 8px;
    }

    .header-actions .btn {
        min-height: 44px;
        flex: 1;
        min-width: 0;
    }

    /* --- Stats card (inbox) --- */
    .stats-card {
        font-size: 0.8125rem;
        padding: 8px 12px;
    }

    /* --- Filter bar --- */
    .filter-bar {
        flex-direction: column;
        align-items: stretch;
    }

    .search-box {
        max-width: 100%;
        width: 100%;
    }

    .filter-group {
        min-width: 100%;
    }

    .filter-btn {
        min-height: 44px;
    }

    /* --- Conversation cards --- */
    .conversation-card {
        flex-direction: column;
        align-items: flex-start;
        gap: 4px;
    }

    .conversation-info {
        width: 100%;
    }

    .conversation-meta {
        flex-direction: row;
        width: 100%;
        justify-content: flex-start;
    }

    .conversation-avatar {
        width: 40px;
        height: 40px;
        font-size: 1rem;
    }

    /* --- Profile page --- */
    .profile-grid {
        grid-template-columns: 1fr;
    }

    .info-grid {
        grid-template-columns: 1fr;
    }

    /* --- Settings page --- */
    .settings-grid {
        grid-template-columns: 1fr;
    }

    /* --- Statistics page (consolidated from separate query) --- */
    .stats-overview-grid {
        grid-template-columns: repeat(2, 1fr);
    }

    .stat-bar-label {
        width: 80px;
        font-size: 0.75rem;
    }

    .team-compare-table {
        font-size: 0.8125rem;
    }

    .team-compare-table th,
    .team-compare-table td {
        padding: 8px 6px;
    }

    .user-daily-grid {
        overflow-x: auto;
    }

    /* --- Touch targets --- */
    .btn,
    button,
    select,
    .nav-link {
        min-height: 44px;
    }

    input[type="text"],
    input[type="search"],
    input[type="email"],
    input[type="password"],
    input[type="number"],
    textarea {
        min-height: 44px;
        font-size: 16px; /* prevents iOS zoom on focus */
    }

}
```

- [ ] **Step 2: Delete the separate statistics 768px media query**

Remove the block at lines 2508-2530 (after the above replacement, line numbers will have shifted — search for `/* Statistics responsive */`):
```css
/* Statistics responsive */
@media (max-width: 768px) {
    .stats-overview-grid {
        grid-template-columns: repeat(2, 1fr);
    }
    /* ... rest of statistics-specific rules ... */
}
```

These rules are now consolidated into the main mobile media query above.

- [ ] **Step 3: Test on desktop**

Load all pages at >768px width. Confirm nothing changed visually on desktop.

- [ ] **Step 4: Test on mobile width**

Use browser DevTools responsive mode at 375px width. Confirm:
- Sidebar is hidden
- Bottom nav is visible at the bottom
- Main content is full-width with no left margin
- On a conversation page: bottom nav is hidden, back button is visible
- Filter bar stacks vertically on inbox
- Profile/settings cards are single-column
- Statistics grid shows 2 columns

- [ ] **Step 5: Test dark mode**

Toggle dark mode and verify all mobile components respect dark theme variables (bottom nav background, account panel colors, overflow menu colors).

- [ ] **Step 6: Commit**

```bash
git add static/css/style.css
git commit -m "feat(mobile): rewrite 768px media query with full mobile layout"
```

---

## Task 5: JavaScript — Account Panel Toggle & Bottom Nav Active State

**Files:**
- Modify: `static/js/app.js`

- [ ] **Step 1: Add account panel and bottom nav logic**

In `app.js`, inside the existing `DOMContentLoaded` handler (line 701), add at the end (before the closing `});` on line 788, before the `console.log`):

```javascript
    // --- Mobile: Account panel toggle ---
    const accountNavItem = document.getElementById('accountNavItem');
    const accountPanel = document.getElementById('accountPanel');
    if (accountNavItem && accountPanel) {
        accountNavItem.addEventListener('click', function(e) {
            e.preventDefault();
            accountPanel.classList.toggle('open');
        });

        // Close account panel on click outside
        document.addEventListener('click', function(e) {
            if (accountPanel.classList.contains('open') &&
                !accountPanel.contains(e.target) &&
                !accountNavItem.contains(e.target)) {
                accountPanel.classList.remove('open');
            }
        });
    }

    // --- Mobile: sync language selector with sidebar ---
    const mobileLangSelector = document.getElementById('mobileLanguageSelector');
    const desktopLangSelector = document.getElementById('languageSelector');
    if (mobileLangSelector && desktopLangSelector) {
        mobileLangSelector.value = desktopLangSelector.value;
    }
```

- [ ] **Step 2: Update sound toggle UI to sync mobile icons**

Replace the `updateSoundToggleUI` function (lines 409-420) with:
```javascript
function updateSoundToggleUI(enabled) {
    const icons = [document.getElementById('soundToggleIcon'), document.getElementById('mobileSoundToggleIcon')];
    const btns = [document.getElementById('soundToggleBtn'), document.getElementById('mobileSoundToggleBtn')];
    icons.forEach(icon => {
        if (!icon) return;
        icon.className = enabled ? 'fas fa-volume-up' : 'fas fa-volume-mute';
    });
    btns.forEach(btn => {
        if (!btn) return;
        enabled ? btn.classList.remove('disabled') : btn.classList.add('disabled');
    });
}
```

- [ ] **Step 3: Update browser notify toggle UI to sync mobile icons**

Replace the `updateBrowserNotifyToggleUI` function (lines 440-451) with:
```javascript
function updateBrowserNotifyToggleUI(enabled) {
    const icons = [document.getElementById('browserNotifyToggleIcon'), document.getElementById('mobilePushToggleIcon')];
    const btns = [document.getElementById('browserNotifyToggleBtn'), document.getElementById('mobilePushToggleBtn')];
    icons.forEach(icon => {
        if (!icon) return;
        icon.className = enabled ? 'fas fa-bell' : 'fas fa-bell-slash';
    });
    btns.forEach(btn => {
        if (!btn) return;
        enabled ? btn.classList.remove('disabled') : btn.classList.add('disabled');
    });
}
```

- [ ] **Step 4: Update toast base offset for mobile**

In the `showNotification` function (line 90), change:
```javascript
    toast.style.bottom = `${20 + offset}px`;
```
to:
```javascript
    const baseOffset = window.innerWidth <= 768 ? 76 : 20;
    toast.style.bottom = `${baseOffset + offset}px`;
```

And in `_repositionToasts` (line 110), change:
```javascript
        t.style.bottom = `${20 + i * 56}px`;
```
to:
```javascript
        const baseOffset = window.innerWidth <= 768 ? 76 : 20;
        t.style.bottom = `${baseOffset + i * 56}px`;
```

- [ ] **Step 5: Update theme icon to sync mobile button**

In `updateThemeIcon` function (line 476), add after the existing icon update:
```javascript
    const mobileBtn = document.getElementById('mobileThemeToggleBtn');
    if (mobileBtn) {
        const mobileIcon = mobileBtn.querySelector('i');
        mobileIcon.className = theme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
    }
```

- [ ] **Step 6: Test account panel**

At 375px width:
- Tap Account tab → panel slides up
- Tap outside → panel closes
- Dark mode toggle works from panel
- Sound/push toggles update icons in both panel and sidebar
- Language selector matches sidebar language
- Logout button works

- [ ] **Step 7: Commit**

```bash
git add static/js/app.js
git commit -m "feat(mobile): add account panel toggle, icon sync, and toast mobile offset"
```

---

## Task 6: JavaScript — Conversation Overflow Menu

**Files:**
- Modify: `static/js/conversation.js`

- [ ] **Step 1: Add overflow menu toggle and property selector sync**

At the end of `conversation.js` (before the final `DOMContentLoaded` block or at the end of the file), add:

```javascript
// --- Mobile overflow menu ---
document.addEventListener('DOMContentLoaded', function() {
    const overflowBtn = document.getElementById('mobileOverflowBtn');
    const overflowMenu = document.getElementById('mobileOverflowMenu');

    if (overflowBtn && overflowMenu) {
        overflowBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            overflowMenu.classList.toggle('open');
        });

        document.addEventListener('click', function(e) {
            if (overflowMenu.classList.contains('open') &&
                !overflowMenu.contains(e.target) &&
                !overflowBtn.contains(e.target)) {
                overflowMenu.classList.remove('open');
            }
        });
    }

    // Sync mobile property selector with desktop one after properties load.
    // loadPropertySelector() runs on DOMContentLoaded in conversation.js and populates
    // the desktop selector via fetch. We wait briefly then copy options to mobile.
    const mobilePropertySelector = document.getElementById('mobilePropertySelector');
    const desktopPropertySelector = document.getElementById('propertySelector');
    if (mobilePropertySelector && desktopPropertySelector) {
        function syncMobilePropertySelector() {
            if (desktopPropertySelector.options.length > 1) {
                mobilePropertySelector.innerHTML = desktopPropertySelector.innerHTML;
                mobilePropertySelector.value = desktopPropertySelector.value;
            }
        }
        // Also listen for changes on the desktop selector
        desktopPropertySelector.addEventListener('change', function() {
            mobilePropertySelector.value = desktopPropertySelector.value;
        });
        mobilePropertySelector.addEventListener('change', function() {
            desktopPropertySelector.value = mobilePropertySelector.value;
        });
        // Initial sync after properties have loaded (loadPropertySelector uses fetch)
        setTimeout(syncMobilePropertySelector, 500);
    }
});
```

- [ ] **Step 2: Update toggleAI to sync both desktop and mobile status**

In the `toggleAI` function (line 569), in the `.then(data => {` success handler, after line 585 (`autoBtn.classList.toggle('auto-respond-active', autoRespond);`), add:
```javascript
        // Sync mobile overflow menu status
        const mobileAiStatus = document.getElementById('mobileAiStatus');
        if (mobileAiStatus) mobileAiStatus.textContent = aiEnabled ? 'ON' : 'OFF';
        const mobileAutoRespondBtn = document.getElementById('mobileAutoRespondBtn');
        if (mobileAutoRespondBtn) mobileAutoRespondBtn.disabled = !aiEnabled;
        const mobileAutoRespondStatus = document.getElementById('mobileAutoRespondStatus');
        if (mobileAutoRespondStatus) mobileAutoRespondStatus.textContent = autoRespond ? 'ON' : 'OFF';
```
Note: Uses 'ON'/'OFF' to match existing desktop behavior in `conversation.js:578`.

- [ ] **Step 3: Update toggleAutoRespond to sync both statuses**

In the `toggleAutoRespond` function (line 590), in the `.then(data => {` success handler, after line 607 (`btn.classList.toggle('auto-respond-active', autoRespond);`), add:
```javascript
        // Sync mobile overflow menu status
        const mobileAutoRespondStatus = document.getElementById('mobileAutoRespondStatus');
        if (mobileAutoRespondStatus) mobileAutoRespondStatus.textContent = autoRespond ? 'ON' : 'OFF';
```

- [ ] **Step 4: Test overflow menu**

At 375px width on a conversation page:
- Desktop `.conversation-actions` is hidden
- "..." button is visible
- Clicking "..." opens the dropdown menu
- Property selector shows same options as desktop
- AI toggle works and syncs status text
- Auto-respond toggle works and syncs
- Guest profile link navigates correctly
- Clicking outside closes the menu

- [ ] **Step 5: Commit**

```bash
git add static/js/conversation.js
git commit -m "feat(mobile): add overflow menu toggle and action sync"
```

---

## Task 7: i18n — New Translation Keys

**Files:**
- Modify: `static/js/i18n.js`

- [ ] **Step 1: Add German translation keys**

In `i18n.js`, in the `de:` block, after the last statistics key (line 325, `'stats.error': 'Fehler beim Laden der Statistiken'`), add:
```javascript

        // Mobile Navigation & Account
        'nav.account': 'Konto',
        'conversation.back': 'Zurück',
        'account.darkMode': 'Dunkelmodus',
        'account.sound': 'Ton',
        'account.push': 'Push',
        'account.language': 'Sprache',
        'account.logout': 'Abmelden'
```

- [ ] **Step 2: Add English translation keys**

In the `en:` block, after the last statistics key (line 646, `'stats.error': 'Error loading statistics'`), add:
```javascript

        // Mobile Navigation & Account
        'nav.account': 'Account',
        'conversation.back': 'Back',
        'account.darkMode': 'Dark Mode',
        'account.sound': 'Sound',
        'account.push': 'Push',
        'account.language': 'Language',
        'account.logout': 'Logout'
```

- [ ] **Step 3: Test translations**

Switch between German and English. Verify bottom nav labels and account panel labels translate.

- [ ] **Step 4: Commit**

```bash
git add static/js/i18n.js
git commit -m "feat(mobile): add i18n keys for mobile nav and account panel"
```

---

## Task 8: Cache Version Bump

**Files:**
- Modify: `templates/chatbot/base.html`
- Modify: `templates/chatbot/conversation.html`
- Modify: `templates/chatbot/inbox.html`

- [ ] **Step 1: Bump versions in base.html**

Change:
- `style.css?v=9` → `style.css?v=10`
- `i18n.js?v=10` → `i18n.js?v=11`
- `app.js?v=8` → `app.js?v=9`

- [ ] **Step 2: Bump versions in conversation.html**

Change:
- `conversation.js?v=8` → `conversation.js?v=9`

(`polling.js?v=8` unchanged — we didn't modify it)

- [ ] **Step 3: Bump versions in inbox.html**

No changes needed — `inbox.js` and `filter-state.js` were not modified.

- [ ] **Step 4: Commit**

```bash
git add templates/chatbot/base.html templates/chatbot/conversation.html
git commit -m "chore: bump cache versions for modified static assets"
```

---

## Task 9: Full Integration Testing

- [ ] **Step 1: Desktop regression test (>768px)**

Load each page at 1024px+ width and verify:
- Inbox: sidebar visible, no bottom nav, cards/filters normal
- Conversation: sidebar visible, no bottom nav, action buttons in header
- Settings: sidebar visible, multi-column cards
- Guest Profile: sidebar visible, multi-column grid
- Statistics: sidebar visible, 4-column stats grid
- Login: unchanged

- [ ] **Step 2: Mobile test (375px)**

Load each page at 375px width and verify:
- **All pages**: Sidebar hidden, bottom nav visible with 4 tabs, correct active state
- **Inbox**: Filter bar stacked, conversation cards reflowed, search full-width, page header wraps, stats card compact
- **Conversation**: No bottom nav, back button visible (top-left), "..." overflow menu works, messages 90% width, input area at bottom
- **Settings**: Single-column cards, full-width inputs
- **Guest Profile**: Single-column, back button works
- **Statistics**: 2-column grid, table scrollable

- [ ] **Step 3: Dark mode test**

Toggle dark mode at 375px. Verify all mobile components (bottom nav, account panel, overflow menu) use dark theme colors properly.

- [ ] **Step 4: Account panel test**

At 375px: tap Account → panel opens → toggle dark mode → toggle sound → change language → tap outside → panel closes. Verify all toggles sync with sidebar state.

- [ ] **Step 5: Conversation overflow menu test**

At 375px on a conversation: tap "..." → dropdown opens → toggle AI → toggle auto-respond → select property → visit guest profile. Verify all actions work and status text syncs.

- [ ] **Step 6: Toast notification test**

At 375px, trigger a toast (e.g., mark all read on inbox). Verify toast appears above the bottom nav, not behind it.

- [ ] **Step 7: 360px minimum width test**

Set DevTools to 360px width. Verify all pages render without horizontal overflow or clipped content.

- [ ] **Step 8: 768px boundary test**

Resize browser slowly across 768px. Verify clean transition between mobile and desktop layouts with no visual glitches.

- [ ] **Step 9: Landscape orientation test**

Rotate DevTools to landscape (e.g., 667x375). Verify all pages render correctly without broken layouts.

**Known limitation:** When the mobile keyboard opens on conversation pages, `100dvh` may cause the input area to shift. This is a common mobile web issue and can be addressed in a follow-up if needed.
