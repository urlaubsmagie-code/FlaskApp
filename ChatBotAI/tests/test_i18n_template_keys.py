"""Every data-i18n key used in a template must exist in i18n.js.

A missing key used to render the key itself into the page — the Gmail button
in the inbox read "inbox.syncGmail" instead of a label. updatePage() now keeps
the markup's own text when a key is missing, so this is no longer visible
garbage, but a missing key still means an untranslated string for EN users.

Pure file reading: no app, no node, no DB.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / 'templates' / 'chatbot'
I18N = ROOT / 'static' / 'js' / 'i18n.js'

KEY_RE = re.compile(r'data-i18n(?:-placeholder|-title)?="([^"]+)"')


def _defined_keys():
    src = I18N.read_text(encoding='utf-8')
    return set(re.findall(r"^\s*'([^']+)':", src, re.MULTILINE))


@pytest.mark.parametrize('template', sorted(TEMPLATES.glob('*.html')),
                         ids=lambda p: p.name)
def test_template_i18n_keys_are_defined(template):
    defined = _defined_keys()
    used = set(KEY_RE.findall(template.read_text(encoding='utf-8')))
    missing = sorted(used - defined)
    assert not missing, (
        f'{template.name} uses i18n keys that i18n.js does not define: {missing}'
    )


def test_german_and_english_cover_the_same_keys():
    """A key defined in only one language silently falls back to German."""
    src = I18N.read_text(encoding='utf-8')
    # The file holds one dict per language; split on the language markers.
    blocks = re.split(r'^\s{4}(de|en):\s*\{', src, flags=re.MULTILINE)
    langs = {}
    for i in range(1, len(blocks) - 1, 2):
        langs[blocks[i]] = set(re.findall(r"^\s*'([^']+)':", blocks[i + 1],
                                          re.MULTILINE))
    if len(langs) != 2:
        pytest.skip('i18n.js layout changed — update this test')
    only_de = sorted(langs['de'] - langs['en'])
    only_en = sorted(langs['en'] - langs['de'])
    assert not only_de and not only_en, (
        f'keys only in DE: {only_de}\nkeys only in EN: {only_en}'
    )
