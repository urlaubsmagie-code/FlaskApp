# Urlaubsmagie Brand Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebrand the ChatBotAI web app from generic blue to the Urlaubsmagie wine/burgundy identity across light mode, dark mode, sidebar, buttons, and login page. Brand the AI assistant as UMI-Bot across all UI labels and system prompts.

**Architecture:** Pure CSS variable swap in `:root` and `[data-theme="dark"]` blocks, plus targeted fixes for hardcoded blue values scattered in the stylesheet. Login page gets the UM logo and wine-tinted styling. One static asset (logo PNG) is copied in. All user-facing "KI"/"AI" strings become "UMI", and the AI system prompt gets UMI's personality.

**Tech Stack:** CSS custom properties, Jinja2 templates, i18n strings, Ollama system prompts

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

---

### Task 8: Add UMI Personality to AI System Prompts

**Files:**
- Modify: `services/ai_service.py` — lines 660, 753, 824

- [ ] **Step 1: Update `_build_compact_prompt()` role line (line 660)**

Change from:

```python
"You are a vacation rental host replying to a guest.",
```

To:

```python
"You are UMI, the friendly AI assistant for Urlaubsmagie vacation rentals. You are warm, helpful, and casual — always treating guests like welcome visitors.",
```

- [ ] **Step 2: Update closing message shortcut (line 752-755)**

Change from:

```python
closing_system = (
    f"You are a vacation rental host. The guest ({guest_name}) is thanking you "
    "for your help. Reply briefly and warmly in the SAME LANGUAGE as the guest's message. "
    "Keep it to 1-2 sentences. Do NOT bring up any other topics."
)
```

To:

```python
closing_system = (
    f"You are UMI, the friendly AI assistant for Urlaubsmagie. The guest ({guest_name}) is thanking you "
    "for your help. Reply briefly and warmly in the SAME LANGUAGE as the guest's message. "
    "Keep it to 1-2 sentences. Do NOT bring up any other topics."
)
```

- [ ] **Step 3: Update `_build_chat_messages()` full prompt (line 824)**

Change from:

```python
"You are a vacation rental host writing a reply to a guest.",
```

To:

```python
"You are UMI, the friendly AI assistant for Urlaubsmagie vacation rentals. You are warm, helpful, and casual — always treating guests like welcome visitors.",
```

- [ ] **Step 4: Commit**

```bash
git add services/ai_service.py
git commit -m "feat: add UMI personality to AI system prompts"
```

---

### Task 9: Rename KI/AI to UMI in i18n and Template Labels

**Files:**
- Modify: `static/js/i18n.js` — German (~45) and English (~30) string replacements
- Modify: `templates/chatbot/conversation.html` — ~7 hardcoded "KI" labels
- Modify: `templates/chatbot/settings.html` — ~15 hardcoded "KI" labels
- Modify: `templates/chatbot/inbox.html` — line 114 "KI:" sender prefix
- Modify: `templates/chatbot/help.html` — ~50 "KI" references in help text
- Modify: `templates/chatbot/guest_profile.html` — "KI-extrahiert" label
- Modify: `static/js/inbox.js` — ~5 JS fallback strings
- Modify: `static/js/knowledge.js` — ~4 JS fallback strings

**Important:** Only rename user-facing display text. Do NOT rename CSS classes, Python variables, database fields, API routes, or i18n key names.

- [ ] **Step 1: Update German strings in i18n.js**

In `static/js/i18n.js`, within the `de` section, replace all user-facing "KI" with "UMI":

```
"KI aktiviert" → "UMI aktiviert"
"KI deaktiviert" → "UMI deaktiviert"
"KI-Vorschlag" → "UMI-Vorschlag"
"KI-Antwort für diese Nachricht" → "UMI-Antwort für diese Nachricht"
"KI-Antwort senden" → "UMI-Antwort senden"
"KI nicht erreichbar. Läuft Ollama?" → "UMI nicht erreichbar. Läuft Ollama?"
"KI denkt nach..." → "UMI denkt nach..."
"KI-Antworten" → "UMI-Antworten"
"Automatische KI-Antwort" → "Automatische UMI-Antwort"
"KI-Hauptschalter ist AUS (Einstellungen)" → "UMI-Hauptschalter ist AUS (Einstellungen)"
"KI-Assistent" → "UMI-Assistent"
"KI-extrahiert" → "UMI-extrahiert"
"KI-Konfiguration" → "UMI-Konfiguration"
"KI-Hauptschalter" → "UMI-Hauptschalter"
"Automatisch KI-Antworten auf Gastnachrichten generieren" → "Automatisch UMI-Antworten auf Gastnachrichten generieren"
"Ton für KI-generierte Antworten auswählen" → "Ton für UMI-generierte Antworten auswählen"
"Anzahl der vorherigen Nachrichten für KI-Kontext" → "Anzahl der vorherigen Nachrichten für UMI-Kontext"
"Eigene Anweisungen, die die KI bei jeder Antwort berücksichtigen soll" → "Eigene Anweisungen, die UMI bei jeder Antwort berücksichtigen soll"
"Kreativität der KI-Antworten (0.0 = vorhersagbar, 1.0 = kreativ)" → "Kreativität der UMI-Antworten (0.0 = vorhersagbar, 1.0 = kreativ)"
"Maximale Länge der KI-Antworten (128-4096)" → "Maximale Länge der UMI-Antworten (128-4096)"
"KI-Server Status" → "UMI-Server Status"
"KI-Verbindung testen" → "UMI-Verbindung testen"
"KI-Modell" → "UMI-Modell"
"Verarbeiten führt KI auf ungelesene E-Mails aus." → "Verarbeiten führt UMI auf ungelesene E-Mails aus."
"Unterkünfte helfen der KI, relevantere Antworten zu geben." → "Unterkünfte helfen UMI, relevantere Antworten zu geben."
"KI-Antwort generiert" → "UMI-Antwort generiert"
"Fügen Sie Fakten hinzu, die die KI bei Gästeanfragen nutzen soll." → "Fügen Sie Fakten hinzu, die UMI bei Gästeanfragen nutzen soll."
"Wenn Sie KI-Entwürfe bearbeiten, lernt die KI automatisch daraus." → "Wenn Sie UMI-Entwürfe bearbeiten, lernt UMI automatisch daraus."
"KI sagte" → "UMI sagte"
"KI-Korrektur gespeichert" → "UMI-Korrektur gespeichert"
"KI aktiv" → "UMI aktiv"
"KI pausiert" → "UMI pausiert"
'inbox.senderAI': 'KI' → 'inbox.senderAI': 'UMI'
"KI-Entwurf erstellt — wartet auf Freigabe" → "UMI-Entwurf erstellt — wartet auf Freigabe"
"KI-Antwort erstellen" → "UMI-Antwort erstellen"
"KI-Freigabe" → "UMI-Freigabe" (3 occurrences)
"KI-Antworten müssen vor dem Versand genehmigt werden" → "UMI-Antworten müssen vor dem Versand genehmigt werden"
```

- [ ] **Step 2: Update English strings in i18n.js**

In `static/js/i18n.js`, within the `en` section, replace all user-facing "AI" with "UMI":

```
"AI enabled" → "UMI enabled"
"AI disabled" → "UMI disabled"
"AI Suggest" → "UMI Suggest"
"AI suggestion for this message" → "UMI suggestion for this message"
"Send AI Response" → "Send UMI Response"
"AI not reachable. Is Ollama running?" → "UMI not reachable. Is Ollama running?"
"AI is thinking..." → "UMI is thinking..."
"AI Responses" → "UMI Responses"
"Automatic AI Response" → "Automatic UMI Response"
"AI Master Switch is OFF (Settings)" → "UMI Master Switch is OFF (Settings)"
"AI Assistant" → "UMI Assistant"
"AI-Extracted" → "UMI-Extracted"
"AI Configuration" → "UMI Configuration"
"AI Master Switch" → "UMI Master Switch"
... (apply the same pattern to all English AI→UMI strings)
'inbox.senderAI': 'AI' → 'inbox.senderAI': 'UMI'
```

- [ ] **Step 3: Update hardcoded labels in conversation.html**

In `templates/chatbot/conversation.html`, replace:
- Line 60: `title="KI-Antworten"` → `title="UMI-Antworten"`
- Line 64: `title="Automatische KI-Antwort"` → `title="Automatische UMI-Antwort"`
- Line 102: `KI:` → `UMI:`
- Line 160: `KI-Assistent` → `UMI-Assistent`
- Line 169: `title="KI-Antwort für diese Nachricht"` → `title="UMI-Antwort für diese Nachricht"`
- Line 198: `KI-Vorschlag` → `UMI-Vorschlag`
- Line 201: `KI-Antwort erstellen` → `UMI-Antwort erstellen`

- [ ] **Step 4: Update hardcoded labels in settings.html**

In `templates/chatbot/settings.html`, replace all `KI-` prefixed German labels with `UMI-`:
- Line 16: `KI-Konfiguration` → `UMI-Konfiguration`
- Line 22: `KI-Hauptschalter` → `UMI-Hauptschalter`
- Line 48: `KI-Freigabe` → `UMI-Freigabe`
- Line 49: `KI-Antworten müssen...` → `UMI-Antworten müssen...`
- Line 62: `KI sendet sofort` → `UMI sendet sofort`
- Line 98: `KI-generierte` → `UMI-generierte`
- Line 112: `KI-Kontext` → `UMI-Kontext`
- Line 122: `die KI bei jeder` → `UMI bei jeder`
- Line 139: `KI-Antworten` → `UMI-Antworten`
- Line 153: `KI-Antworten` → `UMI-Antworten`
- Line 172: `KI-Modell` → `UMI-Modell`
- Line 237: `KI-Verbindung testen` → `UMI-Verbindung testen`
- Line 261: `der KI` → `UMI`
- Line 333: `KI auf ungelesene` → `UMI auf ungelesene`
- Line 375: `von der KI` → `von UMI`

- [ ] **Step 5: Update inbox.html sender prefix**

In `templates/chatbot/inbox.html`, line 114, change:
```
{% elif conv.last_message.sender_type == 'ai' %}KI: {% endif %}
```
To:
```
{% elif conv.last_message.sender_type == 'ai' %}UMI: {% endif %}
```

- [ ] **Step 6: Update guest_profile.html**

In `templates/chatbot/guest_profile.html`, line 83, change:
```
KI-extrahiert
```
To:
```
UMI-extrahiert
```

- [ ] **Step 7: Update help.html**

In `templates/chatbot/help.html`, replace all user-facing "KI" with "UMI" throughout (~50 occurrences). Key replacements:
- "Wichtiger Hinweis zur KI" → "Wichtiger Hinweis zu UMI"
- "Die KI ist ein hilfreiches..." → "UMI ist ein hilfreiches..."
- All "KI-Vorschlag", "KI-Antwort", "KI-System", etc. → "UMI-Vorschlag", "UMI-Antwort", "UMI-System"
- "die KI" → "UMI" (when used as subject/object in sentences)
- Line 139 hardcoded color: also change `color:#2563eb` → `color:var(--primary-color)` (or `color:#7B2332` since help.html may not have the variable)

- [ ] **Step 8: Update JS fallback strings in inbox.js**

In `static/js/inbox.js`, change:
- Line 73: `'KI'` → `'UMI'`
- Line 80: `'KI aktiv'` → `'UMI aktiv'` and `'KI pausiert'` → `'UMI pausiert'`
- Line 86: `'KI-Freigabe'` → `'UMI-Freigabe'`
- Line 152: `'KI'` → `'UMI'`
- Line 193: `'KI-Freigabe'` → `'UMI-Freigabe'`
- Lines 204-205: `'KI aktiv'` → `'UMI aktiv'` and `'KI pausiert'` → `'UMI pausiert'`

- [ ] **Step 9: Update JS fallback strings in knowledge.js**

In `static/js/knowledge.js`, change:
- Line 102/106: `'KI bei Gästeanfragen'` → `'UMI bei Gästeanfragen'`
- Line 168: `'KI-Entwürfe bearbeiten, lernt die KI'` → `'UMI-Entwürfe bearbeiten, lernt UMI'`
- Line 177: `'KI sagte'` → `'UMI sagte'`

- [ ] **Step 10: Commit**

```bash
git add static/js/i18n.js static/js/inbox.js static/js/knowledge.js templates/chatbot/conversation.html templates/chatbot/settings.html templates/chatbot/inbox.html templates/chatbot/guest_profile.html templates/chatbot/help.html
git commit -m "feat: rename all KI/AI labels to UMI across UI"
```

---

### Task 10: Add "Powered by UMI" to Login Page

**Files:**
- Modify: `templates/chatbot/login.html`

- [ ] **Step 1: Update the login subtitle**

In `templates/chatbot/login.html`, change the login header subtitle from:

```html
<p data-i18n="auth.loginSubtitle">Melden Sie sich an, um fortzufahren</p>
```

To:

```html
<p style="font-size: 0.8rem; color: var(--text-light); margin-top: 8px;">Powered by UMI</p>
<p data-i18n="auth.loginSubtitle">Melden Sie sich an, um fortzufahren</p>
```

- [ ] **Step 2: Verify login page**

The login page should now show:
1. UM logo (from Task 6)
2. "ChatBotAI" title
3. "Powered by UMI" in subtle light text
4. "Melden Sie sich an, um fortzufahren" subtitle
5. Login form with wine-colored button

- [ ] **Step 3: Commit**

```bash
git add templates/chatbot/login.html
git commit -m "feat: add 'Powered by UMI' to login page"
```

---

### Task 11: Bump JS Cache Versions and Final UMI Verification

**Files:**
- Modify: `templates/chatbot/base.html` — i18n.js cache version
- Modify: Various templates — inbox.js, knowledge.js cache versions

- [ ] **Step 1: Bump i18n.js cache version**

In `templates/chatbot/base.html`, find the i18n.js script tag and bump from `v=18` to `v=19`.

- [ ] **Step 2: Bump inbox.js cache version**

Find the inbox.js script tag (in `templates/chatbot/inbox.html`) and bump from `v=19` to `v=20`.

- [ ] **Step 3: Bump knowledge.js cache version**

Find the knowledge.js script tag (in `templates/chatbot/knowledge.html`) and bump from `v=3` to `v=4`.

- [ ] **Step 4: Full UMI verification pass**

Check that "KI" no longer appears in any user-facing location:
- [ ] Inbox: sender prefix shows "UMI:" not "KI:"
- [ ] Inbox: filter button says "UMI-Freigabe"
- [ ] Inbox: AI badge tooltip says "UMI aktiv" / "UMI pausiert"
- [ ] Conversation: buttons say "UMI-Vorschlag", "UMI-Antwort erstellen"
- [ ] Conversation: AI toggle tooltip says "UMI-Antworten"
- [ ] Conversation: AI messages labeled "UMI-Assistent"
- [ ] Settings: all "KI" labels now show "UMI"
- [ ] Knowledge: correction labels say "UMI sagte"
- [ ] Help: all text references UMI not KI
- [ ] Guest Profile: memory badge says "UMI-extrahiert"
- [ ] Login: shows "Powered by UMI"
- [ ] Switch to English: all "AI" labels now show "UMI"

- [ ] **Step 5: Commit**

```bash
git add templates/chatbot/base.html templates/chatbot/inbox.html templates/chatbot/knowledge.html
git commit -m "chore: bump JS cache versions for UMI rebrand"
```
