// Regression test for inbox date-group ordering.
//
// Bug: the inbox is server-sorted by `last_message_at` (routes.py) but the client
// grouped/displayed by `updated_at` (inbox.js). `updated_at` bumps on any row touch
// (Smoobu sync, read-state, AI summary), so ~1/3 of conversations had the two on
// different days -> GESTERN/HEUTE headers interleaved (see the screenshot report).
//
// Fix: group + display by `last_message_at` so the header boundaries match the sort
// order. This test proves that grouping a last_message_at-sorted list by
// last_message_at is monotonic, while grouping the SAME list by updated_at is not.
//
// No JS test harness exists in this repo and inbox.js has top-level DOM side effects
// (can't be required in node), so getDateGroup/ensureUTC are mirrored here — keep
// them in sync with ChatBotAI/static/js/inbox.js.  Run: node ChatBotAI/tests/test_inbox_date_grouping.mjs
import assert from 'node:assert';

const ensureUTC = s => !s ? s : (s.endsWith('Z') || s.includes('+')) ? s : s + 'Z';
function getDateGroup(s) {
    if (!s) return 'older';
    const d = new Date(ensureUTC(s));
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const cd = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    const diff = Math.round((today - cd) / 86400000);
    if (diff === 0) return 'today';
    if (diff === 1) return 'yesterday';
    if (diff < 7) return 'thisWeek';
    if (diff < 30) return 'thisMonth';
    return 'older';
}

const RANK = { today: 0, yesterday: 1, thisWeek: 2, thisMonth: 3, older: 4 };
const iso = msAgo => new Date(Date.now() - msAgo).toISOString();
const HOUR = 3600e3, DAY = 24 * HOUR;

// Conversations as the server delivers them: sorted by last_message_at DESC.
// updated_at is always >= last_message_at (any row touch bumps it). The bug appears
// when yesterday-messaged chats get touched "today" (sync/read) and sit interspersed
// with ones not touched today — grouping by updated_at then flips today/yesterday.
// Columns:  last_message_at group  /  updated_at group
const rows = [
    { id: 1, last_message_at: iso(2 * HOUR),          updated_at: iso(1 * HOUR) },        // today     / today
    { id: 2, last_message_at: iso(1 * DAY + 1 * HOUR), updated_at: iso(1 * HOUR) },        // yesterday / today      <- touched today
    { id: 3, last_message_at: iso(1 * DAY + 3 * HOUR), updated_at: iso(1 * DAY + 2 * HOUR) },// yesterday / yesterday  <- not touched today
    { id: 4, last_message_at: iso(1 * DAY + 5 * HOUR), updated_at: iso(2 * HOUR) },        // yesterday / today      <- touched today
    { id: 5, last_message_at: iso(10 * DAY),           updated_at: iso(9 * DAY) },         // thisMonth / thisMonth
];

function isMonotonic(field) {
    let prev = -1;
    for (const r of rows) {
        const k = RANK[getDateGroup(r[field])];
        if (k < prev) return false;   // jumped back to a MORE-recent group => interleaved
        prev = Math.max(prev, k);
    }
    return true;
}

// The fix: grouping by last_message_at (the sort key) never interleaves.
assert.strictEqual(isMonotonic('last_message_at'), true,
    'grouping by last_message_at must be monotonic (no interleaved headers)');

// Guard the reason the fix matters: the SAME list grouped by updated_at DOES interleave.
assert.strictEqual(isMonotonic('updated_at'), false,
    'fixture must reproduce the bug: grouping by updated_at interleaves');

// Spot-check boundary semantics of getDateGroup itself.
assert.strictEqual(getDateGroup(iso(2 * HOUR)), 'today');
assert.strictEqual(getDateGroup(iso(1 * DAY + 2 * HOUR)), 'yesterday');
assert.strictEqual(getDateGroup(iso(3 * DAY)), 'thisWeek');
assert.strictEqual(getDateGroup(iso(10 * DAY)), 'thisMonth');
assert.strictEqual(getDateGroup(iso(60 * DAY)), 'older');
assert.strictEqual(getDateGroup(null), 'older');

console.log('PASS: inbox date-group ordering (fix monotonic, updated_at interleaves)');
