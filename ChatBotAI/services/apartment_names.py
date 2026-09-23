"""Resolve apartment codes from concept names and Smoobu ids.

Pure functions (build_lookups / codes_in_text) are unit-tested with fixture
dicts. The real-config wrappers (code_from_smoobu_id / codes_from_property_text)
read apartment_config.json at the FlaskApp root, cached at module level.

Booking notification emails name the apartment in `Unterkunftsname` by its new
concept name (e.g. "Biberburg" = B7), but our DB stores properties by code, so a
concept<->code bridge is needed. See
docs/superpowers/specs/2026-07-01-booking-concept-name-matching-design.md.
"""
import json
import os
import re
import logging
import threading

logger = logging.getLogger(__name__)

# apartment_config.json lives at the FlaskApp root (this file is
# FlaskApp/ChatBotAI/services/apartment_names.py -> up two dirs).
_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "apartment_config.json",
)


def build_lookups(config: dict):
    """Return (concept_to_codes, smoobu_id_to_code) from an apartment_config dict.

    concept_to_codes: lowercased concept name -> set of UPPERCASE codes.
    smoobu_id_to_code: smoobu apartment id -> UPPERCASE code.
    """
    apartments = (config or {}).get("apartments", {})
    concept_to_codes = {}
    smoobu_id_to_code = {}
    for smoobu_id, entry in apartments.items():
        code = (entry.get("code") or "").strip().upper()
        if not code:
            continue
        smoobu_id_to_code[str(smoobu_id)] = code
        concept = (entry.get("concept_name") or "").strip().lower()
        if concept:
            concept_to_codes.setdefault(concept, set()).add(code)
    return concept_to_codes, smoobu_id_to_code


def codes_in_text(text: str, concept_to_codes: dict):
    """Whole-word, longest-match-first concept detection. Returns UPPERCASE codes."""
    if not text:
        return set()
    lowered = text.lower()
    found = set()
    for concept in sorted(concept_to_codes, key=len, reverse=True):
        # (?<!\w)...(?!\w) = unicode-aware word boundary (handles ä/ö/ü/ß).
        if re.search(r"(?<!\w)" + re.escape(concept) + r"(?!\w)", lowered):
            found |= concept_to_codes[concept]
    return found


_lookups = None
_lookups_lock = threading.Lock()


def _load_config():
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_lookups():
    global _lookups
    if _lookups is None:
        with _lookups_lock:
            if _lookups is None:  # double-checked: another thread may have loaded
                try:
                    _lookups = build_lookups(_load_config())
                except Exception as e:  # missing/corrupt config must not break matching
                    logger.warning("apartment_names: could not load config (%s); using empty lookups", e)
                    _lookups = ({}, {})
    return _lookups


def reset_lookups():
    """Clear the cached lookups (for tests, or to recover after a config fix)."""
    global _lookups
    _lookups = None


def code_from_smoobu_id(smoobu_apartment_id):
    """UPPERCASE code for a Smoobu apartment id, or None."""
    if not smoobu_apartment_id:
        return None
    return _get_lookups()[1].get(str(smoobu_apartment_id))


def codes_from_property_text(text: str):
    """UPPERCASE codes whose concept name appears as a whole word in `text`."""
    return codes_in_text(text, _get_lookups()[0])
