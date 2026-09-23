# WhatsApp bridge — restriction and repeated drops (2026-09-14 / 15)

Status: **closed for this account (2026-09-15).** User: the team's device was cut too, so the
account is done with. All UMI data for it was deleted; WAHA will be tested with a different account.

Deleted 15.09: 41 WhatsApp conversations, 161 messages, 41 WhatsApp-only guests, 158 guest details
(backup: `D:/UMI_backups/chatbot_before_whatsapp_delete_20260915.db`), both login sessions
(`whatsapp_bridge/auth`, `auth_removed_20260915`), all bridge logs, `WHATSAPP_BRIDGE_URL/SECRET`
cleared in `.env`. WhatsApp code kept in UMI for reuse.

## What happened

| Time (Berlin) | Event |
|---|---|
| 10.09 12:58 → 14.09 | Bridge ran nonstop. In the background: 53 reconnects, 182× code 408 (our ping give-up after 35s), 28× code 428, 122× "failed to decrypt". Invisible to the team: it reconnected after 5s and the badge only polls every 60s. |
| 14.09 23:25:15 | WhatsApp sent `xwa2_notify_account_reachout_timelock` — `enforcement_type: RESTRICT_ALL_COMPANIONS`, active, ends 15.09 05:25 (6h). Same second: `stream:error 401 device_removed`. The linked device was deleted. |
| 15.09 ~09:43 | Old session backed up to `whatsapp_bridge/auth_removed_20260915` (861 files). Fresh `auth/`. |
| 15.09 12:08:09 | QR scanned → device `<old business number>:30` linked and connected. |
| 12:11:08 | Closed by WhatsApp's side: **428** after 179s. |
| 12:32:36 | Auto-reconnect → closed **428** after 58s (ws error 1006, abnormal close). |
| 12:38:55 | Manual start → closed **428 "Connection Terminated", data null** after **116s**. |

Each of the three connections: WhatsApp accepted the login, then did not answer
the startup ("init queries") requests within 60s, then cut the connection. No new
enforcement notice was logged. Only one bridge process was running (a second one
would show 440, not 428).

Reading of the evidence (not proven — WhatsApp gives no reason): the number's
linked devices are still being refused after the 14.09 restriction.

## Later the same day

- 13:02:28 — fourth connection cut, **428 after 59s**.
- ~13:23 — bridge **crashed: `ENOSPC` (C: full, 0 GB free)**. Bridge left off by user's decision
  ("don't reconnect it anymore"); `start_server.bat` autostart line commented out. User freed space (75 GB free).
- **Control test: real WhatsApp Web in a normal browser, linked to the same number, stayed connected
  30+ minutes.** So the number's linked devices are NOT blocked in general any more — WhatsApp is
  refusing our Baileys device specifically. Caveat: when C: filled up is unknown, so a full disk
  (auth key writes failing) cannot be fully ruled out for the 12:08–13:02 drops; the 10.–14.09 drops
  predate it.
- Researched WAHA (github.com/devlikeapro/waha): free self-hosted Docker REST API, engines NOWEB
  (their Baileys fork — same as ours), GOWS (Go websocket), **WEBJS (whatsapp-web.js = real WhatsApp
  Web in Chromium)**. All unofficial, no ban-proof claim. WEBJS is the candidate the control test points to.

## What the codes mean (checked in Baileys source)

| Code | Baileys name | Who ends it |
|---|---|---|
| 408 | connectionLost | Our bridge: no frame for keepAliveIntervalMs + 5s |
| 428 | connectionClosed | The socket was closed from outside (WhatsApp / network) |
| 440 | connectionReplaced | Another client logged in as the same device |
| 401 | loggedOut | Device removed / logged out — needs a new QR |
| 515 | restartRequired | Normal, right after a QR scan |

There is no public documentation of WhatsApp's own idle limit.

## Impact on UMI

- Only **2** WhatsApp messages reached UMI after 14.09 20:00 UTC: an owner reply at
  23:25 and a guest message at 12:39 (during the test window).
- Messages from 14.09 23:25 → 15.09 12:08 are **not in UMI** and won't be
  backfilled: re-pairing created a new device, and WhatsApp doesn't deliver
  pre-link messages to it except as history sync, which the bridge skips.
  Everything is still on the phone.

## Code changed (in the working tree, not committed)

`whatsapp_bridge/index.js` (+ `selfcheck.js`, passes):
- 20-min cooldown after any drop (`reconnectDelay`), 1s after a QR scan (515), 5s before pairing.
- `keepAliveIntervalMs: 60000` (Baileys default 30s). 90s was considered — raise only if 60s proves stable.
- Log lines carry timestamp, uptime and the full close reason.
- `POST /reconnect` for a manual reconnect, refused if connected / connecting / unpaired / <10 min since the last one (`manualReconnectRefusal`).
- `/status` returns `reconnect_at`, `logged_out`.
- Media (photos, voice notes, video, documents ≤200 MB) forwarded to UMI — see OPEN_TASKS §4.

UMI: `/api/whatsapp/reconnect` (admin) + "Jetzt verbinden" button in Einstellungen →
Plattform-Integrationen → WhatsApp. **Needs a Flask restart** to appear. Tests: 508 pass.

## Current state (15.09 ~14:00)

- Bridge **off** (crashed on ENOSPC ~13:23, not restarted by decision). Login kept in `auth/`.
- Autostart in `FlaskApp/start_server.bat` **commented out**. The "Bridge starten" button in
  Einstellungen can still start it — don't.
- WhatsApp Web in a normal browser: connected 30+ min on the same number.

## Options

1. **Keep running** — messages arrive only in the ~2 min windows every ~22 min. ~3 logins/hour
   from a device WhatsApp keeps refusing → ban risk for the business number (no WhatsApp at all,
   not even on the phone).
2. **Pause a few days** — stop the bridge (the `auth/` login survives, no QR needed), team uses
   the phone; then one watched test. Also disable the auto-start in `start_server.bat` meanwhile.
3. **Official WhatsApp Cloud API (coexistence with the Business app on the same number)** — no ban
   or drop risk; more setup; outside the 24h window only approved templates can be sent.

## Next steps (to decide)

- [ ] Choose option 1 / 2 / 3.
- [ ] Check the business phone: WhatsApp → Einstellungen → Verknüpfte Geräte — is the device
      listed, and is there any warning/banner about linked devices or the account?
- [x] Bridge stopped, autostart commented out (15.09).
- [ ] Decide on the browser route (WAHA WEBJS / WhatsApp-Web extension) vs Cloud API.
- [ ] When resuming: restart Flask (button + media + profile fixes) and start the bridge once while
      watching `bridge-test*.log`.
