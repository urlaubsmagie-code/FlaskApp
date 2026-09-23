import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

test('connection notice tracks offline state and independent polling failures', async () => {
    const nodes = new Map(), events = {};
    const context = vm.createContext({
        document: {
            visibilityState: 'visible',
            getElementById: id => nodes.get(id),
            createElement: () => ({setAttribute() {}}),
            body: {appendChild: el => nodes.set(el.id, el)},
            addEventListener() {}, removeEventListener() {},
        },
        window: {addEventListener: (event, callback) => {events[event] = callback;}},
        navigator: {onLine: true}, i18n: {t: key => key}, AbortController,
        setTimeout: () => 1, clearTimeout() {}, console: {error() {}},
    });
    vm.runInContext(readFileSync(new URL('../static/js/polling.js', import.meta.url), 'utf8'), context);
    const PollingManager = vm.runInContext('PollingManager', context);
    const banner = nodes.get('connectionNotice');
    assert.equal(banner.hidden, true);
    context.navigator.onLine = false;
    events.offline();
    assert.equal(banner.textContent, 'ux.offline');
    context.navigator.onLine = true;
    events.online();
    assert.equal(banner.textContent, 'ux.reconnecting');
    const a = new PollingManager({fetchFn: async () => {throw new Error('network');}, onUpdate() {}});
    const b = new PollingManager({fetchFn: async () => [], onUpdate() {}});
    a.isPolling = b.isPolling = true;
    await a._poll();
    assert.equal(banner.textContent, 'ux.refreshFailed');
    await b._poll();
    assert.equal(banner.hidden, false, 'another service succeeding must not hide this failure');
    a.fetchFn = async () => [];
    await a._poll();
    assert.equal(banner.hidden, true);
    a.fetchFn = async () => {const error = new Error(); error.name = 'AbortError'; throw error;};
    await a._poll();
    assert.equal(banner.hidden, true, 'normal cancellation is not a connection failure');
});
