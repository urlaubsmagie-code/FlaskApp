# UMI-Chat — Installable Web App (PWA) — Design

**Date:** 2026-07-28
**Status:** Approved (pending spec review)
**Area:** ChatBotAI (Urlaubsmagie Messenger) — make it installable + confirm push works on phones

## Goal

Let staff install the messenger to their phone's home screen ("UMI-Chat") on both
Android and iPhone, running fullscreen like a native app, and make sure the
already-wired Web Push notifications actually reach the device for new guest
messages. No separate codebase — the PWA *is* the existing site; installing only
adds a home-screen icon and a standalone window.

## Starting point (already built — do NOT rebuild)

- **HTTPS**: served at `umteamsbz.com` via Cloudflare tunnel (PWA prerequisite met).
- **Service worker**: `ChatBotAI/static/sw.js` (handles `push` + `notificationclick`),
  served by the `service_worker()` route (`routes.py:2942`), registered from
  `app.js` (`navigator.serviceWorker.register('/chatbot/sw.js', {scope:'/chatbot/'})`).
- **Web Push stack**: `PushSubscription` model, VAPID keys auto-generated and stored
  in `AISettings`, `pywebpush`, subscribe/unsubscribe/vapid-key routes, and
  `push_service.notify_new_guest_message()` — **already called** from
  `message_router.py:180` and `smoobu_service.py:891,1349`, and
  `notify_escalation()` from `message_router.py:558`. So push fires on real events.
- **Icons source**: `static/img/umi-logo.png`, 1080×1080 RGBA (clean square).
- **Brand color**: `--primary-color: #7B2332` (burgundy).

**The only missing piece is installability** (a manifest + icons + head tags +
install UI). That is also what unlocks Web Push on iOS (Apple requires the app be
added to the Home Screen, iOS 16.4+).

## What we build

### 1. App icons (generated from `umi-logo.png`)
A one-off build script (Pillow, already available) writes into `static/img/pwa/`:
- `icon-192.png`, `icon-512.png` — standard `"purpose": "any"`.
- `icon-maskable-192.png`, `icon-maskable-512.png` — logo centered on a `#7B2332`
  background with ~20% safe-zone padding so Android adaptive/round masks don't crop.
- `apple-touch-icon.png` (180×180) — iPhone home-screen icon (no transparency;
  burgundy background, since iOS doesn't mask).
The script is idempotent and committed alongside the generated PNGs.

### 2. `manifest.webmanifest`
Served by a small Flask route (mirroring `sw.js`) so the MIME type is
`application/manifest+json` and the URL sits under `/chatbot/`:
```json
{
  "name": "UMI-Chat",
  "short_name": "UMI-Chat",
  "start_url": "/chatbot/",
  "scope": "/chatbot/",
  "display": "standalone",
  "orientation": "portrait",
  "theme_color": "#7B2332",
  "background_color": "#7B2332",
  "icons": [
    {"src": "/chatbot/static/img/pwa/icon-192.png", "sizes":"192x192","type":"image/png","purpose":"any"},
    {"src": "/chatbot/static/img/pwa/icon-512.png", "sizes":"512x512","type":"image/png","purpose":"any"},
    {"src": "/chatbot/static/img/pwa/icon-maskable-192.png","sizes":"192x192","type":"image/png","purpose":"maskable"},
    {"src": "/chatbot/static/img/pwa/icon-maskable-512.png","sizes":"512x512","type":"image/png","purpose":"maskable"}
  ]
}
```
The route is added to the `before_request` whitelist (like `service_worker`) so it
loads before login.

### 3. Head tags (`base.html` + `login.html`)
Add to the `<head>` of both (so the app is installable from login and from the app):
- `<link rel="manifest" href="{{ url_for('chatbot.manifest') }}">`
- `<meta name="theme-color" content="#7B2332">`
- `<link rel="apple-touch-icon" href="/chatbot/static/img/pwa/apple-touch-icon.png">`
- `<meta name="apple-mobile-web-app-capable" content="yes">`
- `<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">`
- `<meta name="apple-mobile-web-app-title" content="UMI-Chat">`

### 4. Platform-aware install prompt (`static/js/pwa-install.js`, loaded on base)
- Hide entirely when already installed: `window.matchMedia('(display-mode: standalone)').matches`
  or `navigator.standalone`.
- **Android/Chromium**: listen for `beforeinstallprompt`, prevent default, stash the
  event, show an **"App installieren"** button; on click call `evt.prompt()`.
- **iOS Safari** (no `beforeinstallprompt`): detect iOS + not-standalone → show a
  dismissible hint: *"Installieren: Teilen-Symbol → 'Zum Home-Bildschirm'"* with the
  share glyph. Remember dismissal in `localStorage` so it doesn't nag.
- Placement: a small unobtrusive banner/button in the inbox header area.

### 5. Notifications reachable after install (mostly verify — already built)
The enable flow ALREADY exists: a **🔔 bell icon** in the top bar (documented in
`help.html:477`) and the `WebPush` module in `app.js` that requests
`Notification.requestPermission()`, registers the SW, and subscribes via
`/api/push/vapid-key` + `/api/push/subscribe`. So this task is primarily:
- Verify the bell/enable flow works when the app is launched installed (standalone).
- Ensure the bell is visible/reachable in the mobile/standalone layout.
- iOS specifics: Web Push needs iOS 16.4+ AND the app installed to the Home Screen —
  when on iOS Safari and not yet standalone, surface a short "install first, then
  enable notifications" hint instead of a permission prompt that would silently fail.
No new backend and no new subscribe logic — reuse what exists.

### 6. Service-worker update hygiene (verify — no change expected)
`sw.js` already calls `self.skipWaiting()` (install) and `clients.claim()` (activate),
and it is **push-only — it has no fetch handler / no asset cache**. So app code
(HTML/JS/CSS) is always served fresh from the server and updates propagate on next
open with nothing to invalidate. This task is just a no-regression check: confirm we
did not introduce any caching, and that a changed `sw.js` (if we touch it) still
activates immediately. We are NOT adding offline shell caching in this version.

## Out of scope (deliberate, per approved scope)

- Offline caching of the app shell / offline state screen.
- Notification settings UI (per-user toggles, quiet hours, test button beyond the
  minimal enable action).
- App-store packaging (PWAs install from the browser; no store needed).

## Verification

**Automated** (Playwright + curl against the running server):
- `GET /chatbot/manifest.webmanifest` returns 200 with `application/manifest+json`
  and the expected JSON (name "UMI-Chat", scope `/chatbot/`, 4 icons).
- Each icon URL returns 200 image/png with correct dimensions.
- `base.html`-rendered inbox `<head>` contains the manifest link + theme-color +
  apple-touch-icon + apple meta tags.
- Service worker still registers (`/chatbot/sw.js` 200) and contains `push` +
  `notificationclick` handlers.
- With a Chromium UA, the install affordance code path runs (button element present);
  with an iOS UA, the iOS hint path renders.

**Manual** (real devices — documented steps, cannot be automated):
- Install on one Android (Chrome "Install app") and one iPhone (Safari "Zum
  Home-Bildschirm"); confirm the UMI-Chat icon + fullscreen standalone launch.
- Enable notifications; send a test guest message (or trigger `notify_new_guest_message`);
  confirm the OS notification arrives with the app closed, and tapping it opens the
  right conversation. Verify iPhone is on iOS 16.4+.

## Rollout note

This is server-side + static assets only. Deploy = restart the Flask server; the SW
version bump makes installed apps pick up the change on next open. No migration.
