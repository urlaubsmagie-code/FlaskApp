"""Notion sync safety scrubber — defense-in-depth so door codes / passwords in
the team's Notion can never reach a guest via UMI.

Pure functions only (no I/O). See
docs/superpowers/specs/2026-06-17-notion-knowledge-sync-design.md §4.
"""
import re

DEFAULT_BLOCK_KEYWORDS = [
    'schlüsselcode', 'schlüsselbox codes', 'code', 'passwör', 'passwort',
    'password', 'pin', 'wlan-passwort', 'intern', '🔑', '🔒',
]

# A "code-shaped" token near an access label (Code/Haustür/Schlüssel/PIN/Tür
# followed by a 3-6 digit run). Drives the density heuristic. Prices (10€) and
# times (16 Uhr) are NOT matched because they lack such a label prefix.
_CODE_NEAR_LABEL = re.compile(
    r'(?:code|haustür|schlüssel|pin|tür)\s*[:\-]?\s*\d{3,6}', re.IGNORECASE)

# Apartment-label-adjacent code: "B5 - 162333", "W2 - 162392", "UT - 1623",
# "HW13 - 7913". This is the DOMINANT real format on the key-code page, and it
# has no label keyword — so it must be caught explicitly. Requires uppercase
# apartment labels (1-2 letters + 0-2 digits) so lowercase prose, prices
# ("2,50 €") and dates ("01.11 - 31.03") do not match. NOT IGNORECASE on purpose.
_APT_CODE = re.compile(r'\b[A-Z]{1,2}\d{0,2}\s*[-:]\s*\d{3,6}\b')

# Layer-2 redaction patterns (order matters; specific first).
_SCRUB_PATTERNS = [
    re.compile(r'haustür\s*[:\-]?\s*\d{3,6}', re.IGNORECASE),
    re.compile(r'\bcode\s*[:\-]?\s*\d{3,6}', re.IGNORECASE),
    re.compile(r'\b(?:pin|wlan[- ]?passwort|passwort)\b\s*[:\-]?\s*\S+', re.IGNORECASE),
    _APT_CODE,
]


def parse_csv_setting(value, default):
    """Split a CSV AISettings string into lowercased, stripped terms."""
    if not value or not value.strip():
        return default
    return [t.strip().lower() for t in value.split(',') if t.strip()]


def is_blocked_page(title, text, block_keywords):
    """Layer 1: True if this whole page must be withheld from UMI."""
    hay = f"{title}\n{text}".lower()
    for kw in block_keywords:
        if kw and kw in hay:
            return True
    # Code-density heuristic: >=3 codes that sit next to access labels OR
    # apartment labels (so a page of bare "W2 - 162392" lines is blocked too).
    if len(_CODE_NEAR_LABEL.findall(text)) + len(_APT_CODE.findall(text)) >= 3:
        return True
    return False


def scrub_value(value):
    """Layer 2: redact code/password substrings from a single entry value."""
    if not value:
        return value
    out = value
    for pat in _SCRUB_PATTERNS:
        out = pat.sub('[redacted]', out)
    return out
