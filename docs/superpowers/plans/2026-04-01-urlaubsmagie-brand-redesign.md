# Urlaubsmagie Brand Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebrand the ChatBotAI web app from generic blue to the Urlaubsmagie wine/burgundy identity across light mode, dark mode, sidebar, buttons, and login page.

**Architecture:** Pure CSS variable swap in `:root` and `[data-theme="dark"]` blocks, plus targeted fixes for hardcoded blue values scattered in the stylesheet. Login page gets the UM logo and wine-tinted styling. One static asset (logo PNG) is copied in.

**Tech Stack:** CSS custom properties, Jinja2 templates, static asset management

---

### Task 1: Copy Logo Asset to Static Folder

**Files:**
- Create: `static/img/um-logo.png` (copy from `C:\Users\admin\Documents\FlaskApp\Image\UMProfile.png`)

- [ ] **Step 1: Create the img directory and copy the logo**

```bash
mkdir -p static/img
cp "/c/Users/admin/Documents/FlaskApp/Image/UMProfile.png" static/img/um-logo.png
```

- [ ] **Step 2: Verify the file exists**

```bash
ls -la static/img/um-logo.png
```
Expected: file exists, non-zero size

- [ ] **Step 3: Commit**

```bash
git add static/img/um-logo.png
git commit -m "chore: add Urlaubsmagie logo to static assets"
```

---

### Task 2: Update Light Mode CSS Variables

**Files:**
- Modify: `static/css/style.css:6-58` (`:root` block)

- [ ] **Step 1: Replace the `:root` color variables**

In `static/css/style.css`, change the `:root` block (lines 6-58) from:

```css
:root {
    /* Colors */
    --primary-color: #2563eb;
    --primary-hover: #1d4ed8;
    --secondary-color: #64748b;
    --success-color: #22c55e;
    --warning-color: #f59e0b;
    --danger-color: #ef4444;

    /* Background */
    --bg-primary: #f8fafc;
    --bg-secondary: #ffffff;
    --bg-sidebar: #1e293b;
```

To:

```css
:root {
    /* Colors — Urlaubsmagie wine/burgundy brand */
    --primary-color: #7B2332;
    --primary-hover: #5E1A27;
    --primary-light: #F9E8EB;
    --secondary-color: #64748b;
    --success-color: #22c55e;
    --warning-color: #f59e0b;
    --danger-color: #ef4444;

    /* Background */
    --bg-primary: #FDF6F7;
    --bg-secondary: #ffffff;
    --bg-sidebar: #4A1520;
```

Leave everything else in `:root` unchanged (text colors, borders, shadows, spacing, platform colors, avatar palette).

- [ ] **Step 2: Verify visually**

Open `http://localhost:5000/chatbot/` in a browser. The sidebar should be dark wine, buttons should be wine-colored, page background should have a faint warm tint. All text should remain readable.

- [ ] **Step 3: Commit**

```bash
git add static/css/style.css
git commit -m "style: swap light mode CSS variables to Urlaubsmagie wine palette"
```

---

### Task 3: Update Dark Mode CSS Variables

**Files:**
- Modify: `static/css/style.css:63-74` (`:root[data-theme="dark"]` block)

- [ ] **Step 1: Replace dark mode variables**

In `static/css/style.css`, change the dark mode block from:

```css
:root[data-theme="dark"] {
    --bg-primary: #0f172a;
    --bg-secondary: #1e293b;
    --card-bg: #1e293b;
    --text-primary: #f1f5f9;
    --text-secondary: #94a3b8;
    --text-light: #64748b;
    --border-color: #334155;
    --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
    --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.4);
    --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.4);
}
```

To:

```css
:root[data-theme="dark"] {
    --primary-color: #8B2D3C;
    --primary-hover: #7B2332;
    --bg-primary: #1A0F12;
    --bg-secondary: #2A1519;
    --card-bg: #2A1519;
    --text-primary: #f1f5f9;
    --text-secondary: #94a3b8;
    --text-light: #64748b;
    --border-color: #3D2025;
    --shadow-sm: 0 1px 2px rgba(26, 15, 18, 0.3);
    --shadow-md: 0 4px 6px -1px rgba(26, 15, 18, 0.4);
    --shadow-lg: 0 10px 15px -3px rgba(26, 15, 18, 0.4);
}
```

- [ ] **Step 2: Update dark mode memory-item hover**

Change line 87 from:

```css
:root[data-theme="dark"] .memory-item:hover {
    background-color: #334155;
}
```

To:

```css
:root[data-theme="dark"] .memory-item:hover {
    background-color: #3D2025;
}
```

- [ ] **Step 3: Verify dark mode visually**

Toggle dark mode in settings. Backgrounds should have a warm wine-tinted darkness, not blue-gray. Borders should be warm. Primary buttons should be slightly lighter wine (`#8B2D3C`).

- [ ] **Step 4: Commit**

```bash
git add static/css/style.css
git commit -m "style: swap dark mode CSS variables to wine-tinted palette"
```

---

### Task 4: Fix Hardcoded Blue Values in CSS

**Files:**
- Modify: `static/css/style.css` — lines 721-723, 1182, 2707-2708, 2802, 2807, 2870

These are places where blue `#2563eb` or `rgba(37, 99, 235, ...)` is hardcoded instead of using the CSS variable.

- [ ] **Step 1: Fix unread conversation indicator (line 721-723)**

Change from:

```css
.conversation-card.unread {
    position: relative;
    background: #eff6ff;
    border-left: 4px solid var(--primary-color);
    box-shadow: inset 0 0 0 1px rgba(37, 99, 235, 0.1);
}
```

To:

```css
.conversation-card.unread {
    position: relative;
    background: var(--primary-light, #F9E8EB);
    border-left: 4px solid var(--primary-color);
    box-shadow: inset 0 0 0 1px rgba(123, 35, 50, 0.1);
}
```

- [ ] **Step 2: Fix modal input focus (lines 2707-2708)**

Change from:

```css
dialog.edit-modal .form-group input:focus {
    outline: none;
    border-color: #2563eb;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}
```

To:

```css
dialog.edit-modal .form-group input:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px rgba(123, 35, 50, 0.1);
}
```

- [ ] **Step 3: Fix memory value editable hover (line 2802)**

Change from:

```css
.memory-value[data-editable="true"]:hover {
    background-color: rgba(37, 99, 235, 0.1);
}
```

To:

```css
.memory-value[data-editable="true"]:hover {
    background-color: rgba(123, 35, 50, 0.1);
}
```

- [ ] **Step 4: Fix memory value contenteditable outline (line 2807)**

Change from:

```css
.memory-value[contenteditable="true"],
.memory-value[contenteditable="plaintext-only"] {
    outline: 2px solid #2563eb;
    background-color: white;
    min-width: 50px;
}
```

To:

```css
.memory-value[contenteditable="true"],
.memory-value[contenteditable="plaintext-only"] {
    outline: 2px solid var(--primary-color);
    background-color: white;
    min-width: 50px;
}
```

- [ ] **Step 5: Fix memory add form input focus (line 2870)**

Change from:

```css
.memory-add-form input:focus {
    outline: none;
    border-color: #2563eb;
}
```

To:

```css
.memory-add-form input:focus {
    outline: none;
    border-color: var(--primary-color);
}
```

- [ ] **Step 6: Commit**

```bash
git add static/css/style.css
git commit -m "style: replace hardcoded blue values with wine brand colors"
```

---

### Task 5: Update Sidebar Active State Styling

**Files:**
- Modify: `static/css/style.css:184-213` (sidebar nav styles)

- [ ] **Step 1: Update logo icon color in sidebar**

The `.logo i` (line 184-187) uses `var(--primary-color)` which will already be wine. No change needed — just verify it looks good on the dark wine sidebar.

- [ ] **Step 2: Update nav-link hover and active states**

Change from:

```css
.nav-link:hover,
.nav-link.active {
    background: rgba(255, 255, 255, 0.1);
    color: var(--text-white);
}
```

To:

```css
.nav-link:hover {
    background: rgba(255, 255, 255, 0.1);
    color: var(--text-white);
}

.nav-link.active {
    background: #7B2332;
    color: var(--text-white);
    border-left: 3px solid #F9E8EB;
}
```

- [ ] **Step 3: Verify sidebar navigation**

Click through different pages (Inbox, Settings, Knowledge, etc.). The active page should show a wine-colored highlight with a light left border. Hover should still show a subtle white overlay.

- [ ] **Step 4: Commit**

```bash
git add static/css/style.css
git commit -m "style: update sidebar active state with wine brand highlight"
```

---

### Task 6: Rebrand Login Page

**Files:**
- Modify: `templates/chatbot/login.html`

- [ ] **Step 1: Update login page CSS variables and focus styles**

In `templates/chatbot/login.html`, replace the `:root` and dark mode variable blocks (lines 10-28) with:

```css
:root {
    --primary-color: #7B2332;
    --primary-hover: #5E1A27;
    --bg-primary: #ffffff;
    --bg-secondary: #ffffff;
    --text-primary: #1e293b;
    --text-secondary: #64748b;
    --text-light: #94a3b8;
    --border-color: #e2e8f0;
    --danger-color: #ef4444;
}
:root[data-theme="dark"] {
    --bg-primary: #1A0F12;
    --bg-secondary: #2A1519;
    --text-primary: #f1f5f9;
    --text-secondary: #94a3b8;
    --text-light: #64748b;
    --border-color: #3D2025;
}
```

- [ ] **Step 2: Update the focus box-shadow color**

Change line 90 from:

```css
box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
```

To:

```css
box-shadow: 0 0 0 3px rgba(123, 35, 50, 0.1);
```

- [ ] **Step 3: Replace the robot icon with the UM logo**

Change the login header (lines 144-148) from:

```html
<div class="login-header">
    <div class="logo-icon"><i class="fas fa-robot"></i></div>
    <h1>ChatBotAI</h1>
    <p data-i18n="auth.loginSubtitle">Melden Sie sich an, um fortzufahren</p>
</div>
```

To:

```html
<div class="login-header">
    <img src="{{ url_for('chatbot.static', filename='img/um-logo.png') }}" alt="Urlaubsmagie" style="width: 80px; height: auto; margin-bottom: 12px;">
    <h1>ChatBotAI</h1>
    <p data-i18n="auth.loginSubtitle">Melden Sie sich an, um fortzufahren</p>
</div>
```

- [ ] **Step 4: Remove the now-unused `.logo-icon` CSS rule**

Delete the `.logo-icon` style block (lines 52-56):

```css
.login-header .logo-icon {
    font-size: 2.5rem;
    color: var(--primary-color);
    margin-bottom: 12px;
}
```

- [ ] **Step 5: Verify login page**

Open `http://localhost:5000/chatbot/login`. Should show:
- White background
- UM logo (mountain/bridge silhouette) centered above form
- Wine-colored login button
- Wine focus ring on inputs
- No blue remnants

- [ ] **Step 6: Commit**

```bash
git add templates/chatbot/login.html
git commit -m "style: rebrand login page with UM logo and wine palette"
```

---

### Task 7: Bump Cache Version and Final Verification

**Files:**
- Modify: `templates/chatbot/base.html:20` (CSS cache version)

- [ ] **Step 1: Bump CSS cache version**

In `templates/chatbot/base.html`, line 20, change:

```html
<link rel="stylesheet" href="{{ url_for('chatbot.static', filename='css/style.css') }}?v=32">
```

To:

```html
<link rel="stylesheet" href="{{ url_for('chatbot.static', filename='css/style.css') }}?v=33">
```

- [ ] **Step 2: Full verification pass**

Check each page in both light and dark mode:
- [ ] Login page: UM logo, wine button, white bg (light), dark wine bg (dark)
- [ ] Inbox: wine sidebar (desktop), wine active tab (mobile bottom nav), warm background
- [ ] Conversation: wine send button, wine action buttons, wine message input focus
- [ ] Guest Profile: wine-tinted memory edit highlights
- [ ] Settings: wine toggle accents
- [ ] Knowledge: wine buttons
- [ ] Statistics: wine accents
- [ ] Help: wine accents
- [ ] Dark mode on all above: warm wine-tinted backgrounds, lighter wine buttons

- [ ] **Step 3: Commit**

```bash
git add templates/chatbot/base.html
git commit -m "chore: bump CSS cache version for brand redesign"
```
