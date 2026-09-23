// Run: node selfcheck.js — which WhatsApp upserts reach UMI (see skipReason in index.js).
const assert = require('assert');
const { skipReason, reconnectDelay, manualReconnectRefusal } = require('./index.js');

const now = 1800000000;
const none = new Set();
const msg = (key = {}, extra = {}) => ({
    key: { remoteJid: '4915112345678@s.whatsapp.net', id: 'A1', fromMe: false, ...key },
    message: { conversation: 'Hallo, ist das WLAN-Passwort in der Wohnung?' },
    messageTimestamp: now - 60,
    ...extra,
});
const daysAgo = (d) => ({ messageTimestamp: now - d * 86400 });

// Live messages, both directions.
assert.strictEqual(skipReason(msg(), 'notify', none, now), null);
assert.strictEqual(skipReason(msg({ fromMe: true }), 'notify', none, now), null);

// Delivered late after an outage: guest messages and replies typed on the phone.
assert.strictEqual(skipReason(msg(), 'append', none, now), null);
assert.strictEqual(skipReason(msg({ fromMe: true }), 'append', none, now), null);
assert.strictEqual(skipReason(msg({}, daysAgo(13)), 'append', none, now), null);

// UMI's own send echoing back must not come in again.
assert.match(skipReason(msg({ id: 'S1', fromMe: true }), 'append', new Set(['S1']), now), /sent by this bridge/);

// Old late deliveries are history, not missed mail. Live messages have no age limit.
assert.match(skipReason(msg({}, daysAgo(15)), 'append', none, now), /older than 14 days/);
assert.strictEqual(skipReason(msg({}, daysAgo(15)), 'notify', none, now), null);

// Still skipped: groups, channels, empty messages, history-replay types.
assert.match(skipReason(msg({ remoteJid: '12036302@g.us' }), 'notify', none, now), /not a 1:1/);
assert.match(skipReason(msg({ remoteJid: '1203@newsletter' }), 'append', none, now), /not a 1:1/);
assert.match(skipReason(msg({}, { message: {} }), 'append', none, now), /no text/);
assert.match(skipReason(msg(), 'history', none, now), /^type /);

// Photos and voice notes without a caption still come in (UMI shows them to the team).
assert.strictEqual(skipReason(msg({}, { message: { audioMessage: { ptt: true } } }), 'notify', none, now), null);
assert.strictEqual(skipReason(msg({}, { message: { imageMessage: {} } }), 'notify', none, now), null);

// Reconnect: instant only for the post-QR restart and before pairing; a lost link cools down 20 min.
assert.strictEqual(reconnectDelay(515, true), 1000);
assert.strictEqual(reconnectDelay(408, false), 5000);
assert.strictEqual(reconnectDelay(408, true, 0), 20 * 60000);
assert.ok(reconnectDelay(428, true, 0.99) < 21 * 60000);

// Manual reconnect: only for a paired, idle, disconnected bridge, at most every 10 min.
const idle = { connected: false, connecting: false, paired: true, loggedOut: false, sinceLastMs: 11 * 60000 };
assert.strictEqual(manualReconnectRefusal(idle), null);
assert.match(manualReconnectRefusal({ ...idle, connected: true }), /bereits verbunden/);
assert.match(manualReconnectRefusal({ ...idle, connecting: true }), /gerade aufgebaut/);
assert.match(manualReconnectRefusal({ ...idle, loggedOut: true }), /QR-Code/);
assert.match(manualReconnectRefusal({ ...idle, paired: false }), /QR-Code/);
assert.match(manualReconnectRefusal({ ...idle, sinceLastMs: 3 * 60000 }), /in 7 Min/);

console.log('selfcheck ok');
