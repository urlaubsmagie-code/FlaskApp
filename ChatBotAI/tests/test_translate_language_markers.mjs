// The translate button must only appear on messages the reader can't already
// read. This pins the marker heuristic in conversation.js against real guest
// messages from the inbox.
//
// The functions are lifted out of the real file at runtime (not mirrored), so
// this test fails if the regex there changes behaviour.
//   Run: node ChatBotAI/tests/test_translate_language_markers.mjs
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const src = readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), '..', 'static', 'js', 'conversation.js'),
    'utf8');

const block = src.slice(src.indexOf('const _LANG_MARKERS'),
                        src.indexOf('// Show the button only on messages'));
assert.ok(block.includes('looksLikeUiLanguage'), 'could not lift the heuristic out of conversation.js');

const i18n = { currentLanguage: 'de' };
const looksLikeUiLanguage = new Function('i18n', block + '; return looksLikeUiLanguage;')(i18n);

// Real German guest messages — no button.
const GERMAN = [
    'Einen schönen guten Tag, ich habe heute gelesen das ein Unwetter Schaden angerichtet hat, meine Frage dazu ist unsere Reise dadurch beeinträchtigt? MFG Frau Siebmann',
    'Und noch eine bescheidene Frage, kochen kann ich dort nicht?',
    'Wann können wir einchecken?',
    'Vielen Dank für die schnelle Antwort!',
    'Gibt es einen Parkplatz in der Nähe?',
];

// Foreign messages — button shown.
const FOREIGN = [
    'Bonjour, à quelle heure pouvons-nous arriver ?',
    'Hello, is there a supermarket nearby?',
    'Buenos días, ¿podemos llegar más tarde?',
    'Dzień dobry, czy jest parking?',
    'Goedemiddag, kunnen we later inchecken?',
];

for (const t of GERMAN) {
    assert.strictEqual(looksLikeUiLanguage(t), true, `should read as German: ${t}`);
}
for (const t of FOREIGN) {
    assert.strictEqual(looksLikeUiLanguage(t), false, `should read as foreign: ${t}`);
}

// With the UI in English the mirror image must hold: German messages become
// the foreign ones.
i18n.currentLanguage = 'en';
assert.strictEqual(looksLikeUiLanguage('Hello, is there a supermarket nearby?'), true);
assert.strictEqual(looksLikeUiLanguage('Wann können wir einchecken?'), false);

console.log('translate language markers: all cases pass');
