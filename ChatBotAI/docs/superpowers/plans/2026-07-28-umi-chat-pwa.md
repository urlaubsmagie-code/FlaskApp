# UMI-Chat Installable Web App (PWA) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the ChatBotAI messenger installable to the home screen ("UMI-Chat") on Android + iPhone and confirm the already-wired Web Push notifications reach installed phones.

**Architecture:** Add a web app manifest (served via a Flask route like `sw.js`), generate app icons from `umi-logo.png`, add PWA head tags to `base.html` + `login.html`, and ship a small platform-aware install-prompt script. Push, the service worker, and the enable-notifications 🔔 bell already exist and are wired — no backend logic changes.

**Tech Stack:** Flask blueprint (ChatBotAI), Jinja templates, vanilla JS, Pillow (icon generation), pytest + node --check for verification.

## Global Constraints

- **App name is "UMI-Chat"** (both `name` and `short_name`). Icon is `umi-logo.png`.
- **Brand color `#7B2332`** for `theme_color`, `background_color`, and maskable/apple icon backgrounds.
- **Scope `/chatbot/`**, `start_url` `/chatbot/`, `display` `standalone`.
- **Reuse, don't rebuild:** service worker (`static/sw.js`, push-only, already has `skipWaiting()`+`clients.claim()`), the `WebPush` subscribe module in `app.js`, the 🔔 enable-notifications bell, and `push_service.notify_new_guest_message()` (already fired from `message_router.py:180`, `smoobu_service.py:891,1349`). Do NOT add offline/asset caching. Do NOT add a notification settings UI.
- Static assets are referenced with `url_for('chatbot.static', filename=...)`; cache-bust query strings are used (`?v=NN`).
- No DB migration. No new Python dependency (Pillow is already available).

---

### Task 1: Generate PWA icons from `umi-logo.png`

**Files:**
- Create: `ChatBotAI/scripts/generate_pwa_icons.py`
- Create (generated, committed): `ChatBotAI/static/img/pwa/icon-192.png`, `icon-512.png`, `icon-maskable-192.png`, `icon-maskable-512.png`, `apple-touch-icon.png`
- Test: `ChatBotAI/tests/test_pwa_icons.py`

**Interfaces:**
- Produces the five icon files at the exact paths the manifest (Task 2) and head tags (Task 3) reference.

- [ ] **Step 1: Write the icon generation script**

Create `ChatBotAI/scripts/generate_pwa_icons.py`:

```python
"""Generate PWA icons from static/img/umi-logo.png (1080x1080 RGBA).

Run once (idempotent): python -m ChatBotAI.scripts.generate_pwa_icons
Writes into static/img/pwa/. Maskable + apple icons sit on the brand burgundy so
Android adaptive masks and iOS (which does not mask) both look right.
"""
import os
from PIL import Image

BRAND = (0x7B, 0x23, 0x32, 255)  # #7B2332
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, 'static', 'img', 'umi-logo.png')
OUT = os.path.join(HERE, 'static', 'img', 'pwa')


def _resized_logo(size):
    logo = Image.open(SRC).convert('RGBA')
    return logo.resize((size, size), Image.LANCZOS)


def _any_icon(size):
    # Transparent logo scaled to the full square (purpose "any").
    return _resized_logo(size)


def _padded_on_brand(size, logo_fraction, flatten):
    # Logo centered on a burgundy square with padding (maskable safe zone / apple).
    canvas = Image.new('RGBA', (size, size), BRAND)
    inner = max(1, int(size * logo_fraction))
    logo = _resized_logo(inner)
    off = (size - inner) // 2
    canvas.paste(logo, (off, off), logo)
    if flatten:
        return canvas.convert('RGB')  # iOS icons must not be transparent
    return canvas


def main():
    os.makedirs(OUT, exist_ok=True)
    _any_icon(192).save(os.path.join(OUT, 'icon-192.png'))
    _any_icon(512).save(os.path.join(OUT, 'icon-512.png'))
    # Maskable: logo at ~62% so it survives Android's circular/rounded crop.
    _padded_on_brand(192, 0.62, flatten=False).save(os.path.join(OUT, 'icon-maskable-192.png'))
    _padded_on_brand(512, 0.62, flatten=False).save(os.path.join(OUT, 'icon-maskable-512.png'))
    # Apple touch icon: 180x180, opaque, logo at ~80%.
    _padded_on_brand(180, 0.80, flatten=True).save(os.path.join(OUT, 'apple-touch-icon.png'))
    print("PWA icons written to", OUT)


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Run the script to generate the icons**

Run: `python -m ChatBotAI.scripts.generate_pwa_icons`
Expected: prints "PWA icons written to ...\static\img\pwa" and creates the 5 PNGs.

- [ ] **Step 3: Write the dimension test**

Create `ChatBotAI/tests/test_pwa_icons.py`:

```python
"""The manifest and head tags reference exact icon paths + sizes; guard that the
generated icons exist with the right dimensions (regenerate via
python -m ChatBotAI.scripts.generate_pwa_icons)."""
import os
from PIL import Image

IMG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'static', 'img', 'pwa')

EXPECTED = {
    'icon-192.png': (192, 192),
    'icon-512.png': (512, 512),
    'icon-maskable-192.png': (192, 192),
    'icon-maskable-512.png': (512, 512),
    'apple-touch-icon.png': (180, 180),
}


def test_pwa_icons_exist_with_correct_dimensions():
    for name, size in EXPECTED.items():
        path = os.path.join(IMG, name)
        assert os.path.exists(path), f"missing {name} — run generate_pwa_icons"
        assert Image.open(path).size == size, f"{name} wrong size"


def test_apple_icon_is_opaque():
    # iOS home-screen icons must not have an alpha channel.
    im = Image.open(os.path.join(IMG, 'apple-touch-icon.png'))
    assert im.mode == 'RGB'
```

- [ ] **Step 4: Run the test**

Run: `python -m pytest ChatBotAI/tests/test_pwa_icons.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/scripts/generate_pwa_icons.py ChatBotAI/static/img/pwa/ ChatBotAI/tests/test_pwa_icons.py
git commit -m "feat(pwa): generate UMI-Chat app icons from logo"
```

---

### Task 2: Serve `manifest.webmanifest`

**Files:**
- Modify: `ChatBotAI/routes.py` (add `manifest()` route next to `service_worker()` at ~line 2941; add its endpoint to the `before_request` whitelist at ~line 116)
- Test: `ChatBotAI/tests/test_pwa_manifest.py`

**Interfaces:**
- Produces route `chatbot.manifest` at `/chatbot/manifest.webmanifest` returning `application/manifest+json`. Head tags (Task 3) link to it via `url_for('chatbot.manifest')`.

- [ ] **Step 1: Write the failing test**

Create `ChatBotAI/tests/test_pwa_manifest.py`:

```python
import json
import pytest
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_manifest_served_with_correct_type_and_content(client):
    # Whitelisted (like sw.js), so reachable without login.
    r = client.get('/chatbot/manifest.webmanifest')
    assert r.status_code == 200
    assert 'application/manifest+json' in r.content_type
    data = json.loads(r.data)
    assert data['name'] == 'UMI-Chat'
    assert data['short_name'] == 'UMI-Chat'
    assert data['scope'] == '/chatbot/'
    assert data['start_url'] == '/chatbot/'
    assert data['display'] == 'standalone'
    assert data['theme_color'] == '#7B2332'
    assert len(data['icons']) == 4
    assert any(i.get('purpose') == 'maskable' for i in data['icons'])
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest ChatBotAI/tests/test_pwa_manifest.py -v`
Expected: FAIL — 404 (route not defined) or redirect to login (not yet whitelisted).

- [ ] **Step 3: Add the manifest route**

In `ChatBotAI/routes.py`, immediately after the `service_worker()` function (ends ~line 2950), add:

```python
@chatbot_bp.route('/manifest.webmanifest')
def manifest():
    """Web app manifest — makes the messenger installable as 'UMI-Chat'."""
    from flask import make_response
    data = {
        "name": "UMI-Chat",
        "short_name": "UMI-Chat",
        "start_url": "/chatbot/",
        "scope": "/chatbot/",
        "display": "standalone",
        "orientation": "portrait",
        "theme_color": "#7B2332",
        "background_color": "#7B2332",
        "icons": [
            {"src": "/chatbot/static/img/pwa/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "/chatbot/static/img/pwa/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "/chatbot/static/img/pwa/icon-maskable-192.png", "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
            {"src": "/chatbot/static/img/pwa/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    resp = make_response(jsonify(data))
    resp.headers['Content-Type'] = 'application/manifest+json'
    resp.headers['Cache-Control'] = 'no-cache'
    return resp
```

- [ ] **Step 4: Whitelist the manifest endpoint (loads pre-login)**

In `ChatBotAI/routes.py`, in the `require_login()` before_request (~line 114-120), add `chatbot.manifest` to the whitelisted endpoints. Change:

```python
        or request.endpoint in ('chatbot.login', 'chatbot.setup', 'chatbot.service_worker')
```
to:
```python
        or request.endpoint in ('chatbot.login', 'chatbot.setup', 'chatbot.service_worker', 'chatbot.manifest')
```

- [ ] **Step 5: Run the test, verify it passes**

Run: `python -m pytest ChatBotAI/tests/test_pwa_manifest.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ChatBotAI/routes.py ChatBotAI/tests/test_pwa_manifest.py
git commit -m "feat(pwa): serve UMI-Chat web app manifest"
```

---

### Task 3: PWA head tags in `base.html` + `login.html`

**Files:**
- Modify: `ChatBotAI/templates/chatbot/base.html` (after the viewport meta, ~line 5)
- Modify: `ChatBotAI/templates/chatbot/login.html` (after the viewport meta, ~line 5)
- Test: `ChatBotAI/tests/test_pwa_manifest.py` (append)

**Interfaces:**
- Consumes `url_for('chatbot.manifest')` (Task 2) and the apple-touch-icon (Task 1).

- [ ] **Step 1: Add the head tags to `base.html`**

In `ChatBotAI/templates/chatbot/base.html`, immediately after the viewport `<meta>` (line 5), add:

```html
    <!-- PWA: installable as "UMI-Chat" -->
    <link rel="manifest" href="{{ url_for('chatbot.manifest') }}">
    <meta name="theme-color" content="#7B2332">
    <link rel="apple-touch-icon" href="{{ url_for('chatbot.static', filename='img/pwa/apple-touch-icon.png') }}">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="UMI-Chat">
```

- [ ] **Step 2: Add the same head tags to `login.html`**

In `ChatBotAI/templates/chatbot/login.html`, immediately after the viewport `<meta>` (line 5), add the identical block from Step 1.

- [ ] **Step 3: Write the tests (append)**

Append to `ChatBotAI/tests/test_pwa_manifest.py`:

```python
def test_login_page_has_pwa_head_tags(client):
    html = client.get('/chatbot/login').get_data(as_text=True)
    assert 'rel="manifest"' in html
    assert 'name="theme-color"' in html
    assert 'apple-touch-icon' in html


def test_inbox_has_pwa_head_tags(app):
    # Authenticated inbox (base.html) must carry the manifest link too.
    from ChatBotAI.models import User, db
    user = User(username='t', display_name='T', is_admin=True)
    user.set_password('pw'); db.session.add(user); db.session.commit()
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(user.id); s['_fresh'] = True
    html = c.get('/chatbot/').get_data(as_text=True)
    assert 'rel="manifest"' in html
    assert 'apple-mobile-web-app-title' in html
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest ChatBotAI/tests/test_pwa_manifest.py -v`
Expected: PASS (all, incl. the 2 new).

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/templates/chatbot/base.html ChatBotAI/templates/chatbot/login.html ChatBotAI/tests/test_pwa_manifest.py
git commit -m "feat(pwa): add manifest + apple head tags to base and login"
```

---

### Task 4: Platform-aware install prompt

**Files:**
- Create: `ChatBotAI/static/js/pwa-install.js`
- Modify: `ChatBotAI/templates/chatbot/base.html` (load the script next to `app.js`, ~line 228)

**Interfaces:**
- Consumes nothing from earlier tasks at runtime except the installable manifest (Task 2/3). Self-contained UI (injects its own DOM + inline styles).

- [ ] **Step 1: Write the install-prompt script**

Create `ChatBotAI/static/js/pwa-install.js`:

```javascript
// UMI-Chat install prompt. Android/Chromium: use the native beforeinstallprompt.
// iOS Safari: no such event, so show a one-line "Add to Home Screen" hint. Hidden
// entirely when already running installed (standalone).
(function () {
    function isStandalone() {
        return window.matchMedia('(display-mode: standalone)').matches
            || window.navigator.standalone === true;
    }
    function isIOS() {
        return /iphone|ipad|ipod/i.test(window.navigator.userAgent);
    }
    if (isStandalone()) return;  // already installed — nothing to show

    var DISMISS_KEY = 'umi_install_hint_dismissed';

    function banner(innerHtml) {
        var el = document.createElement('div');
        el.id = 'umiInstallBanner';
        el.style.cssText =
            'position:fixed;left:12px;right:12px;bottom:12px;z-index:9999;'
            + 'background:#7B2332;color:#fff;padding:12px 14px;border-radius:10px;'
            + 'box-shadow:0 4px 16px rgba(0,0,0,.3);display:flex;align-items:center;'
            + 'gap:10px;font-size:0.95rem;max-width:520px;margin:0 auto;';
        el.innerHTML = innerHtml;
        document.body.appendChild(el);
        return el;
    }
    function closeBtn(el) {
        var b = document.createElement('button');
        b.innerHTML = '&times;';
        b.setAttribute('aria-label', 'Schließen');
        b.style.cssText = 'margin-left:auto;background:transparent;border:0;color:#fff;'
            + 'font-size:1.4rem;line-height:1;cursor:pointer;padding:0 4px;';
        b.onclick = function () {
            try { localStorage.setItem(DISMISS_KEY, '1'); } catch (e) {}
            el.remove();
        };
        el.appendChild(b);
    }

    // Android / Chromium: capture the native prompt and offer a button.
    var deferred = null;
    window.addEventListener('beforeinstallprompt', function (e) {
        e.preventDefault();
        deferred = e;
        var el = banner('<i class="fas fa-download"></i>'
            + '<span>UMI-Chat als App installieren</span>'
            + '<button id="umiInstallBtn" style="background:#fff;color:#7B2332;'
            + 'border:0;border-radius:6px;padding:6px 12px;font-weight:600;cursor:pointer;">'
            + 'Installieren</button>');
        closeBtn(el);
        document.getElementById('umiInstallBtn').onclick = function () {
            el.remove();
            if (deferred) { deferred.prompt(); deferred = null; }
        };
    });

    // iOS Safari: no beforeinstallprompt — show a hint once (dismissible).
    document.addEventListener('DOMContentLoaded', function () {
        if (!isIOS()) return;
        try { if (localStorage.getItem(DISMISS_KEY)) return; } catch (e) {}
        var el = banner('<i class="fas fa-arrow-up-from-bracket"></i>'
            + '<span>UMI-Chat installieren: Teilen-Symbol antippen, '
            + 'dann „Zum Home-Bildschirm".</span>');
        closeBtn(el);
    });
})();
```

- [ ] **Step 2: Load the script in `base.html`**

In `ChatBotAI/templates/chatbot/base.html`, immediately after the `app.js` script tag (~line 228), add:

```html
    <script src="{{ url_for('chatbot.static', filename='js/pwa-install.js') }}?v=1"></script>
```

- [ ] **Step 3: Syntax check**

Run: `node --check ChatBotAI/static/js/pwa-install.js`
Expected: no output (valid).

- [ ] **Step 4: Manual verification (no JS harness in repo)**

With the app running, open the inbox in Chrome DevTools device mode:
- Desktop/Android Chrome: after the manifest + SW load, a **"UMI-Chat als App installieren / Installieren"** banner appears; clicking it fires the native install dialog.
- Toggle an iOS user agent + reload: the **"Teilen-Symbol … Zum Home-Bildschirm"** hint appears instead; the × dismisses it and it stays dismissed on reload.
- Run the app installed (or emulate `display-mode: standalone`): no banner appears.

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/static/js/pwa-install.js ChatBotAI/templates/chatbot/base.html
git commit -m "feat(pwa): platform-aware install prompt for UMI-Chat"
```

---

### Task 5: Fix the push-notification icon (broken favicon → logo)

**Files:**
- Modify: `ChatBotAI/static/sw.js` (line 34)

**Interfaces:**
- Consumes `icon-192.png` from Task 1.

- [ ] **Step 1: Point the notification icon at a real, branded icon**

In `ChatBotAI/static/sw.js`, the push handler currently sets
`icon: '/chatbot/static/favicon.ico'` (line 34) — that file does NOT exist, so push
notifications show no logo. Change the `options` object (lines 32-37) to:

```javascript
    var options = {
        body: data.body || '',
        icon: '/chatbot/static/img/pwa/icon-192.png',
        badge: '/chatbot/static/img/pwa/icon-192.png',
        tag: data.tag || 'chatbotai',
        data: { url: data.url || '/chatbot/' }
    };
```

- [ ] **Step 2: Syntax check + confirm the referenced icon exists**

Run: `node --check ChatBotAI/static/sw.js`
Run: `test -f ChatBotAI/static/img/pwa/icon-192.png && echo "icon present"`
Expected: valid JS; "icon present".

- [ ] **Step 3: Commit**

```bash
git add ChatBotAI/static/sw.js
git commit -m "fix(pwa): show UMI logo on push notifications (favicon.ico was 404)"
```

---

## Manual device verification (post-merge, cannot be automated)

Not a code task — the acceptance check on real hardware:
1. **Android (Chrome):** open `umteamsbz.com/chatbot`, tap the install banner (or Chrome's prompt) → "UMI-Chat" icon on the home screen → opens fullscreen. Tap 🔔 to enable notifications. Send a test guest message → OS notification arrives with the UMI logo, app closed; tapping opens the chat.
2. **iPhone (Safari, iOS 16.4+):** open the site → Share → "Zum Home-Bildschirm" → launch UMI-Chat → tap 🔔 to enable notifications → confirm push arrives with the app closed. (On iOS, notifications work ONLY after install.)

## Self-Review

**Spec coverage:**
- Icons from umi-logo.png (192/512/maskable/apple) → Task 1. ✅
- manifest.webmanifest served, whitelisted, name "UMI-Chat", scope /chatbot/, #7B2332 → Task 2. ✅
- Head tags in base + login → Task 3. ✅
- Platform-aware install prompt (Android native + iOS hint, hidden when installed) → Task 4. ✅
- Notifications reachable / verify: the 🔔 bell + app.js WebPush already exist → covered by the manual device verification (no build needed, per spec §5). ✅
- SW update hygiene: sw.js already has skipWaiting/claim and no asset cache → no change needed (spec §6); the only sw.js edit is the broken-icon fix → Task 5. ✅
- Out of scope (offline cache, settings UI) → not planned. ✅

**Placeholder scan:** none — every code step has full content.

**Type/name consistency:** manifest route endpoint `chatbot.manifest` used by the whitelist (Task 2) and the head-tag `url_for('chatbot.manifest')` (Task 3). Icon paths `/chatbot/static/img/pwa/icon-{192,512}.png`, `icon-maskable-{192,512}.png`, `apple-touch-icon.png` are identical across the generator (Task 1), manifest (Task 2), head tags (Task 3), and sw.js (Task 5). Name "UMI-Chat" consistent.
