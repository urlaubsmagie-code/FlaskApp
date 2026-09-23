"""Google translation without deep-translator.

deep-translator scrapes translate.google.com. Google now serves an error page to
requests that carry no browser User-Agent, and the library scraped THAT page and
returned its text as the translation:

    "Error 500 (Server Error)!!1500.That's an error.There was an error..."

No exception, HTTP 200 — so callers stored it and showed it as a real
translation. deep-translator calls requests.get(url, params, proxies) with no
header hook (still true in 1.11.4, the latest), so the User-Agent cannot be
injected. This module hits the same endpoint with the header it won't send.

Deliberately raises rather than returning something dubious: a wrong translation
silently replaces the author's own words, which is worse than no translation.
Shared by the ChatBotAI message translator and the review portal.
"""
import html
import re

import requests

# Google's lightweight endpoint — same one deep-translator uses.
_URL = 'https://translate.google.com/m'
# Without a browser UA, Google answers with its error page. That IS the bug.
_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
# Google rejects payloads over 5000 chars.
_MAX_CHARS = 4900

_RESULT_RE = re.compile(r'class="result-container">(.*?)</div>', re.S)
_TAG_RE = re.compile(r'<[^>]+>')


class TranslationFailed(RuntimeError):
    """Google did not return a usable translation."""


def translate_text(text: str, target: str = 'de', timeout: int = 15) -> str:
    """Translate `text` into `target`. Raises TranslationFailed on any doubt."""
    try:
        resp = requests.get(
            _URL,
            params={'tl': target, 'sl': 'auto', 'q': text[:_MAX_CHARS]},
            headers={'User-Agent': _UA},
            timeout=timeout,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise TranslationFailed(f'request failed: {exc}') from exc

    match = _RESULT_RE.search(resp.text)
    if not match:
        raise TranslationFailed('no result-container in response')

    translated = html.unescape(_TAG_RE.sub('', match.group(1))).strip()
    if not translated:
        # The error page HAS the container but leaves it empty — the exact shape
        # that used to slip through as a successful translation.
        raise TranslationFailed('empty result (Google served an error page)')
    return translated
