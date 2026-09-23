/**
 * UMI WhatsApp bridge — links this machine to a WhatsApp account as an extra
 * device (the same pairing WhatsApp Web uses) and mirrors messages into UMI.
 *
 * Inbound:  WhatsApp -> POST {FLASK_URL}/chatbot/webhook/whatsapp
 * Outbound: POST /send {jid, text} -> WhatsApp
 *
 * Run:  npm install && node index.js   (scan the QR once; ./auth persists it)
 *
 * NOTE: Baileys is an unofficial client. It violates WhatsApp's ToS and the
 * number can be banned — see the session notes before pointing this at the
 * main business number.
 */
const baileys = require('@whiskeysockets/baileys');
// v6 ships the socket factory as the default export, v7 as a named one.
const makeWASocket = baileys.makeWASocket || baileys.default;
const { useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion, generateMessageIDV2,
        downloadMediaMessage, normalizeMessageContent } = baileys;
const http = require('http');
const qrcode = require('qrcode-terminal');
const QRImage = require('qrcode');
const pino = require('pino');
const path = require('path');

const FLASK_URL = process.env.FLASK_URL || 'http://127.0.0.1';
const SECRET = process.env.WHATSAPP_BRIDGE_SECRET || '';
const PORT = parseInt(process.env.WHATSAPP_BRIDGE_PORT || '3001', 10);
const AUTH_DIR = process.env.WHATSAPP_AUTH_DIR || path.join(__dirname, 'auth');

const logger = pino({ level: 'warn' });

let sock = null;
let connected = false;
let lastQR = null;

// Cooldown after a lost connection: 20 min (+ up to 1 min jitter) before trying again.
// A fixed 5s retry reconnected 53 times in 5 days before WhatsApp restricted the
// number (2026-09-14); an instant reconnect after every drop is what looks automated.
// Missed messages are not lost — WhatsApp delivers them as 'append' on reconnect.
const COOLDOWN_MS = 20 * 60000;

let reconnectTimer = null;
let reconnectAt = null;      // epoch ms of the scheduled reconnect, shown in UMI
let connecting = false;
let loggedOut = false;
let lastManualReconnect = 0;
let openedAtMs = 0;
const stamp = () => new Date().toLocaleString('de-DE', { timeZone: 'Europe/Berlin' });
const MANUAL_RECONNECT_GAP_MS = 10 * 60000;

/** Why the manual "reconnect now" button is refused, or null. Pure: see selfcheck.js.
 *  The gap keeps a button from rebuilding the reconnect loop the cooldown removed. */
function manualReconnectRefusal({ connected, connecting, paired, loggedOut, sinceLastMs }) {
    if (connected) return 'WhatsApp ist bereits verbunden.';
    if (connecting) return 'Verbindung wird gerade aufgebaut.';
    if (loggedOut || !paired) return 'Nicht gekoppelt – bitte den QR-Code neu scannen.';
    if (sinceLastMs < MANUAL_RECONNECT_GAP_MS) {
        return `Zu früh – manuell nur alle 10 Minuten (wieder möglich in ${Math.ceil((MANUAL_RECONNECT_GAP_MS - sinceLastMs) / 60000)} Min.).`;
    }
    return null;
}

/** ms to wait before reconnecting. Pure: see selfcheck.js. */
function reconnectDelay(code, paired, jitter = Math.random()) {
    // WhatsApp asks for this right after a QR scan — waiting would stall the pairing.
    if (code === DisconnectReason.restartRequired) return 1000;
    // No account linked yet (QR expired): nothing to protect, show a fresh QR.
    if (!paired) return 5000;
    return COOLDOWN_MS + Math.floor(jitter * 60000);
}

// ponytail: one global send queue at ~1 msg/sec. Volume here is ~150 msgs/DAY,
// so a per-chat queue would buy nothing. Bursty sending is the pattern that
// looks automated, and this is the whole defence against it.
let sendChain = Promise.resolve();
const SEND_GAP_MS = 1200;
function queueSend(fn) {
    const run = sendChain.then(fn, fn);
    sendChain = run.catch(() => {}).then(() => new Promise(r => setTimeout(r, SEND_GAP_MS)));
    return run;
}

// Retry an unreachable Flask, because the normal reason it is unreachable is a
// deploy restart — and without this every message sent during those ~20s is
// lost from UMI forever (it stays on the phone, which is how it went unnoticed).
// ponytail: in-memory backoff, not a disk queue. Covers a restart; a bridge
// crash still drops the message. Add persistence if that ever actually happens.
const RETRY_DELAYS_MS = [2000, 5000, 15000, 30000];

async function postToUmi(payload, attempt = 0) {
    try {
        const res = await fetch(`${FLASK_URL}/chatbot/webhook/whatsapp`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Bridge-Secret': SECRET },
            body: JSON.stringify(payload),
        });
        // A rejection is an answer: retrying a 403 (bad secret) or a 400 just
        // repeats the same failure. Only 5xx is worth another go.
        if (res.status >= 500 && attempt < RETRY_DELAYS_MS.length) {
            return scheduleRetry(payload, attempt, `HTTP ${res.status}`);
        }
        if (!res.ok) console.error('UMI webhook rejected:', res.status, await res.text());
    } catch (err) {
        // Never throw back into the socket handler: a dead Flask must not kill
        // the WhatsApp connection, or we silently stop receiving.
        if (attempt < RETRY_DELAYS_MS.length) {
            return scheduleRetry(payload, attempt, err.message);
        }
        console.error(`UMI webhook gave up after ${attempt} retries:`, err.message);
    }
}

function scheduleRetry(payload, attempt, why) {
    const delay = RETRY_DELAYS_MS[attempt];
    console.warn(`UMI webhook unreachable (${why}) — retry ${attempt + 1} in ${delay}ms`);
    setTimeout(() => postToUmi(payload, attempt + 1), delay);
}

// WhatsApp addresses 1:1 chats as either the classic `<phone>@s.whatsapp.net`
// or the newer `<id>@lid`. An allowlist of the classic form silently drops every
// LID-addressed message — which is exactly what happened. Deny what we do not
// want instead, so a future address format arrives rather than vanishing.
const SKIP_SUFFIXES = ['@g.us', '@newsletter', '@broadcast'];
function isDirectChat(jid) {
    if (!jid || jid === 'status@broadcast') return false;
    return !SKIP_SUFFIXES.some(suffix => jid.endsWith(suffix));
}

/** The guest's real phone number, when WhatsApp discloses it.
 *  A `@lid` jid's user part is an opaque id, NOT a phone number — using it
 *  would create a junk guest and break matching against Smoobu guests. */
function senderPhone(msg, jid) {
    // On our own message sender_pn is OUR number — only the chat jid names the guest.
    const pn = msg.key.fromMe ? '' : (msg.key.senderPn || msg.key.participantPn || msg.key.remoteJidAlt || '');
    if (pn.endsWith('@s.whatsapp.net')) return pn.split('@')[0];
    if (jid.endsWith('@s.whatsapp.net')) return jid.split('@')[0];
    return null;   // LID-only: let UMI match on the platform id instead
}

/** Plain text out of the many shapes a WhatsApp message can take. */
function extractText(msg) {
    const m = normalizeMessageContent(msg.message) || {};
    return m.conversation
        || m.extendedTextMessage?.text
        || m.imageMessage?.caption
        || m.videoMessage?.caption
        || m.documentMessage?.caption
        || '';
}

// Media UMI shows to the team (its AI never sees it). Placeholder text must match
// MEDIA_PLACEHOLDER_RE in models.py.
const MEDIA_TYPES = {
    imageMessage: 'Bild', videoMessage: 'Video', stickerMessage: 'Sticker', documentMessage: 'Dokument',
};
// ponytail: base64 inside JSON. V8 strings top out near 512 MB (~380 MB of file), so
// 200 MB is the safe ceiling; stream to a file endpoint if bigger ever matters.
const MAX_MEDIA_BYTES = 200 * 1024 * 1024;   // same cap as routes.py

/** {key, label, node} for a photo/voice note/video/document/sticker, else null. */
function mediaInfo(msg) {
    const m = normalizeMessageContent(msg.message) || {};
    if (m.audioMessage) return { key: 'audioMessage', label: m.audioMessage.ptt ? 'Sprachnachricht' : 'Audio', node: m.audioMessage };
    for (const [key, label] of Object.entries(MEDIA_TYPES)) {
        if (m[key]) return { key, label, node: m[key] };
    }
    return null;
}

/** Download the media, or null when it is too big or WhatsApp won't hand it over.
 *  The placeholder still reaches UMI either way, so the team knows it exists. */
async function fetchMedia(msg, info) {
    const size = Number(info.node.fileLength) || 0;
    if (size > MAX_MEDIA_BYTES) return null;
    try {
        const buf = await downloadMediaMessage(msg, 'buffer', {}, { logger, reuploadRequest: sock.updateMediaMessage });
        if (buf.length > MAX_MEDIA_BYTES) return null;
        return { mimetype: info.node.mimetype || '', data: buf.toString('base64') };
    } catch (err) {
        console.warn(`media download failed for ${msg.key.id}:`, err.message);
        return null;
    }
}

// Ids of messages this bridge sent. Baileys echoes our own sends back as 'append'
// upserts; UMI's reply route already stored those, so they must not come back in.
// ponytail: in-memory and capped. A restart forgets it, which is fine: an echo
// arrives within seconds of the send, and UMI dedups on the id anyway.
const sentByBridge = new Set();
function rememberSent(id) {
    if (!id) return;
    sentByBridge.add(id);
    if (sentByBridge.size > 500) sentByBridge.delete(sentByBridge.values().next().value);
}

const MAX_LATE_AGE_SEC = 14 * 24 * 3600;

/** Why a message is NOT forwarded to UMI, or null to forward it. Pure: see selfcheck.js.
 *  'notify' = arrived live. 'append' = delivered late (sent while the bridge was
 *  down, or our own send echoing back). Other types are history replay. */
function skipReason(msg, type, sent = sentByBridge, nowSec = Math.floor(Date.now() / 1000)) {
    const jid = msg.key?.remoteJid || '';
    if (type !== 'notify' && type !== 'append') return `type ${type}`;
    if (sent.has(msg.key?.id)) return 'sent by this bridge';
    if (!isDirectChat(jid)) return `not a 1:1 chat: ${jid}`;
    if (!extractText(msg).trim() && !mediaInfo(msg)) return `no text: ${jid}`;
    const ts = Number(msg.messageTimestamp) || 0;
    if (type === 'append' && ts && nowSec - ts > MAX_LATE_AGE_SEC) return `late and older than 14 days: ${jid}`;
    return null;
}

// One queue per chat. A reconnect delivers missed messages in a burst, and parallel
// webhooks for a chat UMI has not seen yet could create that chat twice.
const chatQueues = new Map();
function forwardInOrder(jid, payload) {
    const next = (chatQueues.get(jid) || Promise.resolve()).then(() => postToUmi(payload));
    chatQueues.set(jid, next);
    next.then(() => { if (chatQueues.get(jid) === next) chatQueues.delete(jid); });
}

async function start() {
    connecting = true;
    reconnectAt = null;
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    const { version } = await fetchLatestBaileysVersion();

    sock = makeWASocket({
        version,
        auth: state,
        logger,
        // Stay invisible: no "online" presence, no read receipts, no typing.
        // Reading a chat in UMI must not mark it read on the guest's phone,
        // and a device that never announces itself is the quietest shape.
        markOnlineOnConnect: false,
        syncFullHistory: false,
        // Ping every 60s (Baileys default 30s); a link counts as lost after 65s without
        // any frame. A late pong at the old 35s limit cost a reconnect. WhatsApp's own
        // idle limit is undocumented — raise to 90s only if the log shows 60s is stable.
        keepAliveIntervalMs: 60000,
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', (u) => {
        const { connection, lastDisconnect, qr } = u;
        if (qr) {
            lastQR = qr;
            // The terminal QR uses Unicode block characters, which Windows
            // cmd.exe renders as blanks. Always print the browser URL too —
            // that one works everywhere.
            console.log('\nScan this QR in WhatsApp > Linked devices.');
            console.log(`If the QR below is blank, open:  ${qrPageUrl()}\n`);
            qrcode.generate(qr, { small: true });
        }
        if (u.receivedPendingNotifications !== undefined) {
            console.log(`[conn] receivedPendingNotifications=${u.receivedPendingNotifications}`);
        }
        if (connection === 'open') {
            connected = true;
            connecting = false;
            openedAtMs = Date.now();
            lastQR = null;
            console.log(`${stamp()} WhatsApp bridge connected as`, sock.user?.id);
        }
        if (connection === 'close') {
            connected = false;
            connecting = false;
            const code = lastDisconnect?.error?.output?.statusCode;
            loggedOut = code === DisconnectReason.loggedOut;
            // Full reason, not just the code: a bare "428" couldn't tell us who cut the line or why.
            const err = lastDisconnect?.error;
            const upFor = openedAtMs ? `${Math.round((Date.now() - openedAtMs) / 1000)}s` : 'never opened';
            console.error(`${stamp()} Connection closed: ${code} (${loggedOut ? 'logged out' : 'reconnecting'}) after ${upFor}`,
                          '| reason:', err?.message, '| data:', JSON.stringify(err?.data ?? null));
            openedAtMs = 0;
            // Logged out means the device was unlinked (or banned) — reconnecting
            // in a loop would hammer WhatsApp, so stop and wait for a human.
            if (!loggedOut) {
                const delay = reconnectDelay(code, !!sock?.authState?.creds?.me);
                // Timestamped, so drops can be checked for a pattern (nightly, hourly, ...).
                console.error(`${new Date().toLocaleString('de-DE', { timeZone: 'Europe/Berlin' })} reconnect in ${Math.round(delay / 1000)}s`);
                reconnectAt = Date.now() + delay;
                reconnectTimer = setTimeout(start, delay);
            }
        }
    });

    sock.ev.on('messages.upsert', async ({ messages, type }) => {
        for (const msg of messages) {
            const jid = msg.key.remoteJid || '';
            // Skips are logged, not silent: an allowlist that silently dropped every
            // LID-addressed message looked exactly like "nothing arrived". Routine
            // skips (history replay, our own echoes) stay quiet.
            const why = skipReason(msg, type);
            if (why) {
                if (!why.startsWith('type ') && why !== 'sent by this bridge') console.log(`[skip] ${why}`);
                continue;
            }
            // Our own messages DO go through: fromMe is a reply the team typed on
            // the phone. 'append' is a message delivered after a bridge outage.
            if (type === 'append') console.log(`[late] delivered while the bridge was offline: ${jid}`);
            const media = mediaInfo(msg);
            const fileName = media?.node.fileName ? `: ${String(media.node.fileName).replace(/[\]\n]/g, '')}` : '';
            // The caption is the guest's own text; without one, a placeholder names the media.
            const text = extractText(msg).trim() || (media ? `[${media.label}${fileName}]` : '');

            // Not awaited: a message retrying for 50s must not hold up other chats.
            forwardInOrder(jid, {
                jid,
                from_me: !!msg.key.fromMe,
                phone: senderPhone(msg, jid),
                // pushName on our own message is OUR name, not the guest's.
                name: msg.key.fromMe ? null : (msg.pushName || null),
                text,
                media: media ? await fetchMedia(msg, media) : null,
                message_id: msg.key.id,
                timestamp: Number(msg.messageTimestamp) || null,
            });
        }
    });
}

// ponytail: node:http, not express. Two endpoints on loopback do not justify
// a dependency tree — and express 4 drags in a qs with open DoS advisories.
function reply(res, code, body) {
    const payload = JSON.stringify(body);
    res.writeHead(code, { 'Content-Type': 'application/json' });
    res.end(payload);
}

async function readJson(req) {
    const chunks = [];
    let size = 0;
    for await (const chunk of req) {
        size += chunk.length;
        if (size > 1e6) throw new Error('body too large');
        chunks.push(chunk);
    }
    return chunks.length ? JSON.parse(Buffer.concat(chunks).toString('utf8')) : {};
}

function qrPageUrl() {
    return `http://127.0.0.1:${PORT}/qr?t=${encodeURIComponent(SECRET)}`;
}

/** Self-refreshing pairing page. The QR rotates every ~20s, hence the reload. */
async function qrPage() {
    let body;
    if (connected) {
        body = `<p class="ok">Verbunden als ${sock?.user?.id || 'unbekannt'}</p>
                <p class="hint">Dieses Fenster kann geschlossen werden.</p>`;
    } else if (lastQR) {
        const png = await QRImage.toDataURL(lastQR, { margin: 2, width: 320 });
        body = `<img src="${png}" alt="WhatsApp QR" width="320" height="320">
                <p class="hint">WhatsApp &rarr; Einstellungen &rarr; Verkn&uuml;pfte Ger&auml;te &rarr; Ger&auml;t hinzuf&uuml;gen</p>`;
    } else {
        body = '<p class="hint">Warte auf QR-Code&hellip;</p>';
    }
    return `<!doctype html><html lang="de"><head><meta charset="utf-8">
<title>UMI WhatsApp koppeln</title>
<meta http-equiv="refresh" content="5">
<style>
  body{font:14px system-ui,sans-serif;background:#faf8f8;color:#2b2b2b;margin:0;
       min-height:100vh;display:flex;align-items:center;justify-content:center}
  .card{background:#fff;border:1px solid #e6dede;border-radius:12px;padding:28px;
        text-align:center;box-shadow:0 1px 3px #0000000f}
  h1{font-size:16px;margin:0 0 18px;color:#7B2332}
  .hint{color:#6b6b6b;margin:14px 0 0}
  .ok{color:#1c7c3f;font-weight:600;font-size:15px}
  img{display:block}
</style></head><body><div class="card"><h1>UMI &middot; WhatsApp koppeln</h1>${body}</div></body></html>`;
}

const server = http.createServer(async (req, res) => {
    const url = (req.url || '').split('?')[0];

    // Opened by a browser, which cannot set a custom header — so the secret
    // travels in the query string instead. Still gated: a QR is a login
    // credential, and anyone who scans it links their own device.
    if (req.method === 'GET' && url === '/qr') {
        const token = new URLSearchParams((req.url || '').split('?')[1] || '').get('t');
        if (SECRET && token !== SECRET) {
            res.writeHead(403, { 'Content-Type': 'text/plain' });
            return res.end('forbidden');
        }
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        return res.end(await qrPage());
    }

    if (SECRET && req.headers['x-bridge-secret'] !== SECRET) {
        return reply(res, 403, { error: 'forbidden' });
    }

    if (req.method === 'GET' && url === '/status') {
        // The QR rides along so UMI's Settings page can show it to admins. It is a
        // login credential — this endpoint is secret-gated, and UMI strips it from
        // every non-admin route.
        const qr = !connected && lastQR ? await QRImage.toDataURL(lastQR, { margin: 2, width: 320 }) : null;
        return reply(res, 200, { connected, user: sock?.user?.id || null, qr_pending: !!lastQR, qr,
                                 reconnect_at: reconnectAt, logged_out: loggedOut });
    }

    if (req.method === 'POST' && url === '/reconnect') {
        const refusal = manualReconnectRefusal({
            connected, connecting, loggedOut,
            paired: !!sock?.authState?.creds?.me,
            sinceLastMs: Date.now() - lastManualReconnect,
        });
        if (refusal) return reply(res, 409, { error: refusal });
        lastManualReconnect = Date.now();
        clearTimeout(reconnectTimer);
        console.log(`${new Date().toLocaleString('de-DE', { timeZone: 'Europe/Berlin' })} manual reconnect from UMI`);
        start().catch(err => console.error('manual reconnect failed:', err));
        return reply(res, 200, { reconnecting: true });
    }

    if (req.method === 'POST' && url === '/send') {
        let body;
        try {
            body = await readJson(req);
        } catch (err) {
            return reply(res, 400, { error: `bad body: ${err.message}` });
        }
        const { jid, text } = body;
        if (!jid || !text) return reply(res, 400, { error: 'jid and text are required' });
        if (!connected) return reply(res, 503, { error: 'bridge not connected' });
        try {
            // Our own id, remembered BEFORE sending: the 'append' echo can beat the
            // send's promise. The id Baileys reports is remembered too, in case they differ.
            const messageId = generateMessageIDV2(sock.user?.id);
            rememberSent(messageId);
            const sent = await queueSend(() => sock.sendMessage(jid, { text }, { messageId }));
            rememberSent(sent?.key?.id);
            return reply(res, 200, { success: true, message_id: sent?.key?.id || null });
        } catch (err) {
            console.error('send failed:', err.message);
            return reply(res, 502, { error: err.message });
        }
    }

    reply(res, 404, { error: 'not found' });
});

// The port is the single-instance lock. Two bridges on the same auth folder log in
// as the same device, and WhatsApp keeps kicking one off ("connection replaced"),
// so the WhatsApp socket only starts after this process owns the port. A second
// copy (Start_Server.bat and the UMI Settings button can both start one) exits.
if (require.main === module) {
    server.on('error', (err) => {
        if (err.code === 'EADDRINUSE') {
            console.log(`Port ${PORT} is busy - a bridge is already running. This copy exits.`);
            process.exit(0);
        }
        console.error('bridge HTTP server failed:', err);
        process.exit(1);
    });
    server.listen(PORT, '127.0.0.1', () => {
        console.log(`Bridge HTTP on 127.0.0.1:${PORT}`);
        console.log(`Pairing page: ${qrPageUrl()}`);
        start().catch(err => { console.error('bridge failed to start:', err); process.exit(1); });
    });
}

module.exports = { skipReason, reconnectDelay, manualReconnectRefusal };
