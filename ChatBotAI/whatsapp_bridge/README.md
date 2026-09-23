# UMI WhatsApp bridge

Links this machine to a WhatsApp account as an **extra device** (the same
pairing WhatsApp Web uses) and mirrors messages into UMI's unified inbox.

## Read this first

Baileys is an unofficial client. Connecting violates WhatsApp's Terms of
Service and **the phone number can be banned** — including accounts that had
run clean for years (see Baileys issue #1869, Oct 2025). Test with a spare SIM
before pointing it at the business number.

The official alternative is WhatsApp Cloud API **Coexistence** (Business app
and API on the same number, EU-supported since Oct 2025). No ban risk. Its
catch is the 24-hour window: outside 24h of the guest's last message you may
only send pre-approved templates.

## Setup

```bash
cd whatsapp_bridge
npm install

# same value as WHATSAPP_BRIDGE_SECRET in ../.env
export WHATSAPP_BRIDGE_SECRET=<a-long-random-string>
export FLASK_URL=http://127.0.0.1

node index.js          # scan the QR in WhatsApp > Linked devices
```

The session persists in `whatsapp_bridge/auth/` — scan once. **Back that
folder up**; losing it means re-pairing. It is credentials, never commit it.

In production it starts with everything else: `start_server.bat` (in the Windows
Startup folder) launches `ChatBotAI\start_whatsapp_bridge.bat` in a minimized
window, so the bridge also comes back after a Windows Update restart. Only one
bridge can run: it takes port 3001 before connecting to WhatsApp, and a second
copy exits. Two copies on the same `auth/` would keep kicking each other off.

`node selfcheck.js` checks which incoming messages are forwarded to UMI.

## How it fits

```
WhatsApp  ──► bridge ──► POST /chatbot/webhook/whatsapp ──► MessageRouter ──► inbox
WhatsApp  ◄── bridge ◄── POST /send ◄── /api/whatsapp/reply/<id> ◄── composer
```

- Groups, status broadcasts and channels are ignored. Replies typed on the
  phone (`fromMe`) are stored as owner messages.
- Messages that arrive while the bridge is down are delivered when it reconnects,
  as `append` upserts, and are forwarded too (up to 14 days old), with their real
  timestamps. UMI's own sends also echo back as `append`; the bridge sets their
  message id itself and skips exactly those ids. UMI dedups on the id as well.
- Webhooks go out in order per chat, so a burst of missed messages can't create
  the same chat twice.
- Media without a caption is skipped (nothing to show yet).
- Outbound is queued at ~1 msg/sec — bursty sending is the pattern that looks
  automated, and this is the only defence against it.
- Presence and read receipts are off: reading a chat in UMI does not mark it
  read on the guest's phone.
- UMI never auto-answers WhatsApp (`auto_respond=False` in the webhook). The
  channel exists to put the chat in the inbox; a human writes the reply.

## Health

**From UMI:** Einstellungen → Plattform-Integrationen → WhatsApp shows the
status, has a "Bridge starten" button (`POST /chatbot/api/whatsapp/start`) and
shows the pairing QR (`GET /chatbot/api/whatsapp/pairing`). Both routes are
admin-only. A bridge started there runs detached and logs to
`whatsapp_bridge/bridge.log`.

`GET /chatbot/api/whatsapp/status` (logged in) reports whether the bridge is
linked. It never includes the QR. If `connection closed (logged out)` appears in the bridge log, the
device was unlinked or the number was banned — it deliberately does not
reconnect in a loop.
