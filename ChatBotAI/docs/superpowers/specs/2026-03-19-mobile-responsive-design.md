# Mobile Responsive Design Spec

## Overview
Make the ChatBotAI app fully usable on mobile phones (360px+ width). Currently the app shows a desktop layout on phones with a 260px fixed sidebar and no mobile breakpoints below 768px.

## Decisions
- **Navigation**: Bottom nav bar (4 tabs: Inbox, Statistics, Settings, Account)
- **Conversation**: Full-screen with hidden bottom nav, back button to return
- **Approach**: CSS media queries + minimal JS (no framework)
- **Breakpoint**: Single mobile breakpoint at 768px (deliberate simplification — a 480px sub-breakpoint was considered but dropped as YAGNI since layouts are flexible enough with one break)
- **Minimum width**: 360px
- **Landscape**: Same mobile layout, no special handling

## Breakpoints & Navigation

### Mobile Mode (max-width: 768px)
- Sidebar: `display: none` (completely hidden, not collapsed)
- `main-content`: `margin-left: 0`, full viewport width
- Bottom nav: fixed to bottom, 56px tall, z-index above content but below modals
- Bottom nav: add `padding-bottom: env(safe-area-inset-bottom)` for notched iPhones
- 4 tabs: Inbox (icon + label), Statistics (icon + label), Settings (icon + label), Account (icon + label)
- Active tab highlighted with `--primary-color`
- Respects dark mode via existing CSS variables

### Desktop Mode (min-width: 769px)
- No changes to current behavior
- Bottom nav: `display: none`

### Conversation Page Exception
- Body gets class `conversation-page` via Jinja2 block: add `{% block body_class %}{% endblock %}` to `base.html`'s `<body>` tag, then override in `conversation.html` with `{% block body_class %}conversation-page{% endblock %}`
- Bottom nav hidden via CSS: `body.conversation-page .bottom-nav { display: none }`
- Back button visible in conversation header

## Page-by-Page Specs

### Inbox (mobile)
- **Page header**: `.page-header` wraps to stack title and action buttons. Action buttons (Mark All Read, Sync, Refresh) wrap into a second row, full-width, 44px min height
- **Stats card**: `.stats-card` keeps 3-column layout but with smaller font and reduced padding. Numbers stay visible, labels abbreviate if needed
- **Filter bar**: Filters stack vertically, full-width. Search box full-width (remove max-width: 300px constraint)
- **Filter buttons**: Override padding to ensure 44px min touch target height
- **Conversation cards**: Full-width, reflowed layout:
  - Row 1: Avatar (40px) + Guest name + Platform icon + Timestamp (right)
  - Row 2: Property name + Unread badge (right)
  - Row 3: Message preview (truncated 2 lines)
- **Touch targets**: Minimum 44px height on all interactive elements
- **Sync buttons**: Full-width or grouped row at top, 44px min height

### Conversation (mobile)
- **Header**: Back arrow (left, reuse existing `.back-btn` class) + Guest name + platform icon (center) + "..." overflow menu button (right)
- **Overflow menu**: A `<button class="mobile-overflow-btn">` with `fas fa-ellipsis-v` icon. Clicking toggles a `.mobile-overflow-menu` dropdown (position: absolute, right: 0, top: 100%). Contains: AI toggle, property selector, auto-respond toggle, guest profile link. These are **duplicated** in the overflow menu HTML (not moved via JS). The JS toggle functions (`toggleAI()`, `toggleAutoRespond()`) must target elements by ID so they update regardless of which copy (desktop `.conversation-actions` or mobile overflow menu) the user interacts with. Click outside or second click closes it. Requires small JS handler in `conversation.js`.
- **Messages**: Max-width 85-90%, guest left-aligned, owner/AI right-aligned
- **Container height**: Use `height: 100vh; height: 100dvh;` (vh fallback first, dvh override second) to avoid mobile browser chrome issues
- **AI suggestion**: Full-width, between messages and input
- **Input area**: Fixed to bottom. Textarea full-width, send button right. Action buttons (template, AI suggest) in compact row above textarea
- **Template dropdown**: Opens upward on mobile (`.template-dropdown-menu { bottom: 100%; top: auto; }`) to avoid clipping at screen bottom
- **All buttons**: 44px min touch target

### Settings (mobile)
- `.settings-grid`: Single column, full-width cards (drop minmax(400px))
- Setting items: Label on top, input/select below, full-width
- All inputs/selects full-width
- Buttons/toggles: 44px min height

### Guest Profile (mobile)
- `.profile-grid`: Single column, full-width (drop minmax(350px))
- `.info-grid`: Single column (drop 2-column)
- Memory sections stack vertically
- Merge modal: Already width: 90%, verify touch-sized buttons
- Existing `.back-btn` on this page is already visible and sufficient — no changes needed

### Statistics (mobile)
- `.stats-overview-grid`: 2 columns (already partially handled at 768px)
- Consolidate with existing statistics 768px media query block (lines 2508-2530) into one unified mobile block
- Charts/tables: Horizontal scroll wrapper if overflow
- Team table: Existing smaller font handling sufficient

### Login
- Already responsive. Verify touch target sizes only.

### Debug
- Low priority. Ensure single column, no horizontal overflow.

## HTML Changes

### base.html
Update viewport meta to support safe-area-inset on notched iPhones:
```html
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
```

Add `{% block body_class %}{% endblock %}` to body tag:
```html
<body class="{% block body_class %}{% endblock %}">
```

Add bottom nav before closing `</body>`:
```html
<nav class="bottom-nav">
  <a href="/chatbot/" class="bottom-nav-item" data-page="inbox">
    <i class="fas fa-inbox"></i>
    <span data-i18n="nav.inbox">Posteingang</span>
  </a>
  <a href="/chatbot/statistics" class="bottom-nav-item" data-page="statistics">
    <i class="fas fa-chart-bar"></i>
    <span data-i18n="nav.statistics">Statistiken</span>
  </a>
  <a href="/chatbot/settings" class="bottom-nav-item" data-page="settings">
    <i class="fas fa-cog"></i>
    <span data-i18n="nav.settings">Einstellungen</span>
  </a>
  <a href="#" class="bottom-nav-item" data-page="account" id="accountNavItem">
    <i class="fas fa-user"></i>
    <span data-i18n="nav.account">Konto</span>
  </a>
</nav>
```

### Account Tab Behavior
The Account tab opens a slide-up panel (`.account-panel`) anchored above the bottom nav. Toggled via JS click handler on `#accountNavItem`. Click outside or second click closes it.

Account panel HTML added to `base.html` alongside the bottom nav:
```html
<div class="account-panel">
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
Note: Sound/push toggle functions must update BOTH sidebar icons (desktop) and account panel icons (mobile) to keep state in sync. The `toggleNotificationSound()` and `toggleBrowserNotifications()` functions should target both `#soundToggleIcon` and `#mobileSoundToggleIcon` (and similarly for push).

### conversation.html
- Override body class: `{% block body_class %}conversation-page{% endblock %}`
- Back button already exists (`.back-btn`). Ensure it's visible on mobile (currently may be hidden on desktop — keep desktop behavior, show on mobile via CSS)
- Add overflow menu button and dropdown to conversation header:
```html
<button class="mobile-overflow-btn" aria-label="Menu">
  <i class="fas fa-ellipsis-v"></i>
</button>
<div class="mobile-overflow-menu" style="display:none;">
  <!-- AI toggle, property selector, auto-respond, guest profile link moved here on mobile -->
</div>
```

## CSS Changes (style.css)

### New: Bottom Nav Styles
```css
.bottom-nav {
  display: none; /* hidden on desktop */
}
.mobile-overflow-btn {
  display: none; /* hidden on desktop */
}
.account-panel {
  display: none; /* hidden on desktop */
}

@media (max-width: 768px) {
  .bottom-nav {
    display: flex;
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    height: 56px;
    padding-bottom: env(safe-area-inset-bottom);
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
}
```

### Modified: Mobile Breakpoint (replace existing 768px query)
Consolidate both existing 768px media query blocks (lines 1808-1863 and 2508-2530) into one unified mobile block.

Key changes at `@media (max-width: 768px)`:
- `.sidebar { display: none }`
- `.main-content { margin-left: 0; padding: 12px; padding-bottom: calc(72px + env(safe-area-inset-bottom)); }` (56px nav + 16px breathing + safe area for notched phones)
- `.conversation-page .main-content { padding-bottom: 0; }` (no bottom nav padding)
- `.conversation-page .bottom-nav { display: none; }`
- `.search-box { max-width: 100%; width: 100%; }`
- `.filter-bar { flex-direction: column; }`
- `.filter-group { min-width: 100%; }`
- `.filter-btn { min-height: 44px; }` (touch target)
- `.page-header { flex-wrap: wrap; }` and `.header-actions { width: 100%; flex-wrap: wrap; }`
- `.conversation-card` reflow styles
- `.profile-grid { grid-template-columns: 1fr; }`
- `.settings-grid { grid-template-columns: 1fr; }`
- `.info-grid { grid-template-columns: 1fr; }`
- `.conversation-actions { display: none; }` (replaced by overflow menu on mobile)
- `.mobile-overflow-btn { display: flex; }` (shown on mobile only)
- `.back-btn { display: flex; min-height: 44px; min-width: 44px; }` (reuse existing class, show on mobile, bump from 40px to meet 44px touch target)
- `.notification-toast { bottom: 76px !important; }` (above bottom nav — `!important` needed because toast styles are JS-injected in `app.js` which would otherwise win by source order)
- `.conversation-container { height: 100vh; height: 100dvh; }` (vh fallback first, dvh override second — browsers that support dvh use it, others fall back to vh)
- `.template-dropdown-menu { bottom: 100%; top: auto; }` (open upward on mobile)
- Touch target: all buttons, links, inputs get `min-height: 44px`
- Stats overview grid: 2 columns (moved from separate media query)

## JavaScript Changes

### conversation.js
- Add overflow menu toggle: click `mobile-overflow-btn` shows/hides `.mobile-overflow-menu`
- Add click-outside handler to close overflow menu

### app.js
- Add Account panel toggle: click `#accountNavItem` shows/hides `.account-panel`
- Add click-outside handler to close account panel
- Set active state on bottom nav based on current URL path
- Update `toggleNotificationSound()` and `toggleBrowserNotifications()` to sync both sidebar and mobile account panel icons

### i18n.js
- Add NEW translation keys only (existing keys like `nav.inbox`, `nav.settings`, `nav.statistics` are already present):
  - `nav.account` (de: "Konto", en: "Account")
  - `conversation.back` (de: "Zurück", en: "Back")
  - `account.logout` (de: "Abmelden", en: "Logout")
  - `account.darkMode` (de: "Dunkelmodus", en: "Dark Mode")
  - `account.language` (de: "Sprache", en: "Language")
  - `account.sound` (de: "Ton", en: "Sound")
  - `account.push` (de: "Push", en: "Push")

## Cache Versioning
Bump all static asset version numbers by 1 across all templates (check each file's current version individually — they are not all the same).

## Files Modified
1. `static/css/style.css` — bulk of changes (new bottom nav, account panel, overflow menu, expanded 768px media query)
2. `templates/chatbot/base.html` — body_class block, bottom nav HTML, account panel HTML
3. `templates/chatbot/conversation.html` — body_class override, overflow menu button + dropdown
4. `static/js/app.js` — account panel toggle, bottom nav active state
5. `static/js/conversation.js` — overflow menu toggle + click-outside
6. `static/js/i18n.js` — new translation keys
7. All templates — bump cache versions

## Files NOT Modified
- `static/js/inbox.js` — no changes needed
- `static/js/filter-state.js` — no changes needed
- `models.py`, `routes.py`, `services/*` — backend unchanged

## Testing
- Test on 360px, 414px (iPhone), 768px (tablet boundary), and 1024px+ (desktop)
- Test both light and dark modes
- Test conversation page: bottom nav hidden, back button works, overflow menu opens/closes
- Test all 4 bottom nav tabs navigate correctly
- Test Account panel opens with correct controls and logout works
- Test filter bar stacking on inbox
- Test settings/profile cards single-column on mobile
- Test landscape orientation doesn't break
- Test toast notifications appear above bottom nav
- Test template dropdown opens upward on mobile
- Test on notched iPhone (safe area inset)
