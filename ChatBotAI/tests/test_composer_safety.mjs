import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../static/js/conversation.js', import.meta.url), 'utf8');
const block = source.slice(source.indexOf('let sendInProgress = false;'), source.indexOf('// Active AbortControllers'));
function setup(overrides = {}) {
    const elements = {
        messageInput: {value: 'My reply', readOnly: false, focus() {}},
        sendStatus: {}, suggestAiBtn: {}, generateAiBtn: {},
    };
    const button = {disabled: false};
    const stored = new Map();
    const calls = [], bubbles = [];
    function element() {
        return {dataset: {}, setAttribute(k, v) {this[k] = v;},
            replaceChildren(...children) {this.children = children;},
            appendChild(child) {this.status = child;}};
    }
    const context = vm.createContext({
        document: {getElementById: id => elements[id], createElement: element,
            querySelector: selector => selector.startsWith('#messageForm') ? button
                : bubbles.find(b => String(b.dataset.messageId) === selector.match(/"(.*?)"/)?.[1]) || null},
        localStorage: {getItem: k => stored.get(k), setItem: (k,v) => stored.set(k,v), removeItem: k => stored.delete(k)},
        navigator: {onLine: true}, i18n: {t: k => k}, confirm: () => false,
        conversationPlatform: 'smoobu', gmailConnected: true, smoobuConnected: true, whatsappConnected: true,
        conversationId: 7, draftKey: 'draft', draftTimeout: null, pendingCorrectionOriginal: null,
        knownMessageIds: new Set(), autoResizeTextarea() {}, scrollToBottom() {}, showNotification() {},
        addMessageToUI: msg => {
            const bubble = element();
            bubble.dataset.messageId = msg.id;
            bubble.querySelector = selector => selector === '.message-header' ? bubble : bubble.status;
            bubble.remove = () => bubbles.splice(bubbles.indexOf(bubble), 1);
            bubbles.push(bubble);
            return bubble;
        },
        setTimeout: () => 1, clearTimeout() {}, AbortController,
        console: {error() {}, log() {}, debug() {}}, aiEnabled: true, showAiError() {},
        fetch: async (...args) => {calls.push(args); return {ok: true, json: async () => ({message_id: 18})};},
        ...overrides,
    });
    vm.runInContext(block, context);
    vm.runInContext('let activeAiController = null;\n' + source.slice(source.indexOf('function suggestAIResponse()'), source.indexOf('function suggestForMessage(')), context);
    return {elements, button, stored, calls, bubbles, context, send: () => context.sendMessage({preventDefault() {}})};
}

test('acknowledgement replaces the spinner with a check and uses the correct channel', async () => {
    const h = setup();
    await h.send();
    assert.match(h.calls[0][0], /smoobu\/reply\/7$/);
    assert.deepEqual(JSON.parse(h.calls[0][1].body), {message: 'My reply'});
    assert.equal(h.elements.messageInput.value, '');
    assert.equal(h.stored.size, 0);
    assert.equal(h.bubbles[0].dataset.messageId, 18);
    assert.equal(h.bubbles[0].status.className, 'message-send-state accepted');
    assert.equal(h.elements.sendStatus.textContent, '');
});

test('lost response keeps text, records uncertainty, and never falls back to a second request', async () => {
    let requests = 0;
    const h = setup({fetch: async () => {requests++; throw new Error('connection lost');}});
    await h.send();
    assert.equal(requests, 1);
    assert.equal(h.elements.messageInput.value, 'My reply');
    assert.equal(h.stored.get('draft'), 'My reply');
    assert.equal(h.stored.get('draft_uncertain'), 'My reply');
    assert.equal(h.elements.sendStatus.textContent, 'ux.uncertain');
    assert.equal(h.button.disabled, false);
    assert.equal(h.elements.messageInput.readOnly, false);
    await h.send(); // User declines the explicit resend confirmation.
    assert.equal(requests, 1);
});

test('HTTP errors and malformed acknowledgements never look successful', async () => {
    for (const response of [
        {ok: false, json: async () => ({error: 'Session expired'})},
        {ok: true, json: async () => ({})},
        {ok: true, json: async () => {throw new Error('invalid JSON');}},
    ]) {
        const h = setup({fetch: async () => response});
        await h.send();
        assert.equal(h.elements.messageInput.value, 'My reply');
        assert.equal(h.bubbles[0].status.className, 'message-send-state uncertain');
        assert.equal(h.elements.sendStatus.textContent, 'ux.uncertain');
    }
});

test('send stays locked until the outstanding request resolves', async () => {
    let finish, count = 0;
    const h = setup({fetch: () => {count++; return new Promise(resolve => {finish = resolve;});}});
    const pending = h.send();
    assert.equal(h.elements.messageInput.value, '');
    assert.equal(h.elements.messageInput.readOnly, false);
    assert.equal(h.bubbles[0].status.className, 'message-send-state pending');
    assert.equal(h.stored.get('draft_uncertain'), 'My reply');
    await h.send();
    assert.equal(count, 1);
    finish({ok: true, json: async () => ({message_id: 21})});
    await pending;
    assert.equal(h.button.disabled, false);
});

test('offline and disconnected channels preserve drafts without a local fallback', async () => {
    for (const overrides of [{navigator: {onLine: false}}, {smoobuConnected: false}]) {
        const h = setup(overrides);
        await h.send();
        assert.equal(h.calls.length, 0);
        assert.equal(h.elements.messageInput.value, 'My reply');
    }
});

test('local-only chats explicitly distinguish storage from delivery', async () => {
    const h = setup({conversationPlatform: 'manual', fetch: async () => ({ok: true, json: async () => ({id: 19})})});
    await h.send();
    assert.equal(h.bubbles[0].status.title, 'ux.localOnly');
    assert.equal(h.bubbles[0].status.className, 'message-send-state local');
});

test('duplicate acknowledgement does not add a second bubble', async () => {
    const h = setup({fetch: async () => ({ok: true, json: async () => ({duplicate_skipped: true})})});
    await h.send();
    assert.equal(h.bubbles.length, 0);
    assert.equal(h.elements.sendStatus.textContent, 'ux.duplicate');
});

test('AI text goes directly into the composer and changes the button to New variant', () => {
    const h = setup();
    h.elements.messageInput.value = 'Typed while AI was working';
    h.context.insertDraft('<b>Suggestion</b>', null, true);
    assert.equal(h.elements.messageInput.value, '<b>Suggestion</b>');
    assert.match(h.elements.suggestAiBtn.innerHTML, /conversation.ai.regenerate/);
    assert.equal(h.stored.get('draft'), '<b>Suggestion</b>');
    assert.equal(h.context.undoDraft, undefined);
});

test('late success preserves a new draft typed while sending', async () => {
    let finish;
    const h = setup({fetch: () => new Promise(resolve => {finish = resolve;})});
    const pending = h.send();
    h.elements.messageInput.value = 'Next reply';
    finish({ok: true, json: async () => ({message_id: 21})});
    await pending;
    assert.equal(h.elements.messageInput.value, 'Next reply');
    assert.equal(h.stored.get('draft'), 'Next reply');
    assert.equal(h.stored.has('draft_uncertain'), false);
    assert.equal(h.bubbles.length, 1);
});

test('late failure preserves the new draft and keeps the outgoing recovery copy', async () => {
    let fail;
    const h = setup({fetch: () => new Promise((resolve, reject) => {fail = reject;})});
    const pending = h.send();
    h.elements.messageInput.value = 'Next reply';
    fail(new Error('connection lost'));
    await pending;
    assert.equal(h.elements.messageInput.value, 'Next reply');
    assert.equal(h.stored.get('draft_uncertain'), 'My reply');
    assert.equal(h.bubbles[0].status.className, 'message-send-state uncertain');
});

test('a bubble adopted by polling receives confirmation without duplication', async () => {
    let finish;
    const h = setup({fetch: () => new Promise(resolve => {finish = resolve;})});
    const pending = h.send();
    h.bubbles[0].dataset.messageId = 21;
    h.context.knownMessageIds.add(21);
    finish({ok: true, json: async () => ({message_id: 21})});
    await pending;
    assert.equal(h.bubbles.length, 1);
    assert.equal(h.bubbles[0].status.className, 'message-send-state accepted');
});

test('inserting a template offers enhancement', () => {
    const h = setup();
    h.context.insertDraft('Suggested reply', null, true);
    h.context.insertDraft('Template text');
    assert.match(h.elements.suggestAiBtn.innerHTML, /conversation.ai.enhance/);
});

test('regeneration makes a new request, keeps the draft while waiting, and preserves it on error', async () => {
    let requests = 0, finish;
    const h = setup({fetch: async () => {
        requests++;
        if (requests === 1) return {json: async () => ({suggestion: 'First reply'})};
        if (requests === 2) return new Promise(resolve => {finish = resolve;});
        throw new Error('AI unavailable');
    }});
    await h.context.suggestAIResponse();
    assert.equal(h.elements.messageInput.value, 'First reply');
    assert.match(h.elements.suggestAiBtn.innerHTML, /conversation.ai.regenerate/);
    const pending = h.context.suggestAIResponse();
    assert.equal(h.elements.messageInput.value, 'First reply');
    await h.context.suggestAIResponse();
    assert.equal(requests, 2, 'double clicks must not start another request');
    finish({json: async () => ({suggestion: 'Second reply'})});
    await pending;
    assert.equal(h.elements.messageInput.value, 'Second reply');
    await h.context.suggestAIResponse();
    assert.equal(requests, 3);
    assert.equal(h.elements.messageInput.value, 'Second reply');
    assert.equal(h.elements.suggestAiBtn.disabled, false);
    assert.match(h.elements.suggestAiBtn.innerHTML, /conversation.ai.regenerate/);
});

test('storage failure releases the composer and prevents a send without a recovery copy', async () => {
    const h = setup({localStorage: {getItem() {}, setItem() {throw new Error('quota');}}});
    await h.send();
    assert.equal(h.calls.length, 0);
    assert.equal(h.elements.messageInput.readOnly, false);
    assert.equal(h.button.disabled, false);
});

test('adaptive button compares text and enhancement variants reuse the original staff draft', async () => {
    const bodies = [];
    const h = setup({fetch: async (url, options) => {
        bodies.push(JSON.parse(options.body));
        return {json: async () => ({suggestion: 'Improved ' + bodies.length})};
    }});
    h.elements.messageInput.value = '';
    h.context.updateSuggestionButton();
    assert.equal(h.context.suggestionMode(), 'suggest');
    h.elements.messageInput.value = 'parking behind house';
    h.context.updateSuggestionButton();
    assert.equal(h.context.suggestionMode(), 'enhance');
    await h.context.suggestAIResponse();
    assert.equal(bodies[0].enhance_draft, 'parking behind house');
    assert.equal(h.context.suggestionMode(), 'variant');
    await h.context.suggestAIResponse();
    assert.equal(bodies[1].enhance_draft, 'parking behind house');
    h.elements.messageInput.value += ' after 6pm';
    assert.equal(h.context.suggestionMode(), 'enhance');
    await h.context.suggestAIResponse();
    assert.equal(bodies[2].enhance_draft, 'Improved 2 after 6pm');
});

test('typing during enhancement is not overwritten by the late response', async () => {
    let finish;
    const h = setup({fetch: () => new Promise(resolve => {finish = resolve;})});
    const pending = h.context.suggestAIResponse();
    h.elements.messageInput.value = 'New details typed while waiting';
    finish({json: async () => ({suggestion: 'Outdated enhancement'})});
    await pending;
    assert.equal(h.elements.messageInput.value, 'New details typed while waiting');
    assert.equal(h.context.suggestionMode(), 'enhance');
});
