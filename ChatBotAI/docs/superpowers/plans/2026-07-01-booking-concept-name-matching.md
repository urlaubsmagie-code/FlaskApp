# Booking Concept-Name Apartment Matching — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make apartment identity a real signal in Booking email matching by resolving both the email (concept name in `Unterkunftsname`) and the conversation (`smoobu_apartment_id`) to a canonical apartment code and comparing them — boosting confidence on a match, soft-vetoing on a mismatch.

**Architecture:** A new pure-function helper module (`services/apartment_names.py`) loads `apartment_config.json` and builds two lookups (concept-name→codes, smoobu-id→code). `email_reconcile._candidate_views` attaches each conversation's resolved code; `score_conversation_match` compares it against codes detected in the email's property text. No DB migration, no schema change.

**Tech Stack:** Python 3, Flask/SQLAlchemy (existing), pytest. Data in `apartment_config.json` (FlaskApp root).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-01-booking-concept-name-matching-design.md`.
- **Booking only** for code-aware logic. Airbnb and unresolved cases fall back to existing `_property_overlap`. No regression to Airbnb.
- Match boost = **+0.30**. Mismatch soft-veto = **`score = max(0.0, score - 0.50)`** (drops name+dates 0.80 → 0.30, below the 0.80 auto-insert threshold, still queueable).
- Code comparison is **uppercase-normalized** on both sides.
- No new dependencies. No migration. No change to the `email_autoinsert_booking` gate (stays `false`, shadow mode).
- Nested repo is source of truth: branch `feat/notion-knowledge-sync`. **Do NOT `git add -A`** — this working tree carries unrelated dirty files (PKCE OAuth, base.html, i18n.js, routes.py). Stage only the exact files each task names.
- Run tests from the FlaskApp root: `cd C:\Users\admin\Documents\FlaskApp`, and `set PYTHONIOENCODING=utf-8` on Windows for German output. Test invocation: `python -m pytest ChatBotAI/tests/<file> -v`.

---

### Task 1: `apartment_names.py` helper (pure functions)

Pure, DB-free code resolution. Unit-tested with small fixture dicts so the logic is independent of the real config file's contents.

**Files:**
- Create: `ChatBotAI/services/apartment_names.py`
- Test: `ChatBotAI/tests/test_apartment_names.py`

**Interfaces:**
- Produces:
  - `build_lookups(config: dict) -> tuple[dict, dict]` → `(concept_to_codes, smoobu_id_to_code)` where `concept_to_codes: dict[str, set[str]]` (lowercased concept → set of UPPERCASE codes) and `smoobu_id_to_code: dict[str, str]` (smoobu id → UPPERCASE code).
  - `codes_in_text(text: str, concept_to_codes: dict) -> set[str]` — whole-word, longest-first concept detection; returns UPPERCASE codes.
  - `code_from_smoobu_id(smoobu_apartment_id) -> str | None` — uses the real config.
  - `codes_from_property_text(text: str) -> set[str]` — uses the real config.

- [ ] **Step 1: Write the failing tests**

Create `ChatBotAI/tests/test_apartment_names.py`:

```python
from ChatBotAI.services.apartment_names import (
    build_lookups, codes_in_text,
)

FIXTURE = {
    "apartments": {
        "111": {"code": "B7", "name": "B7 - Ferienwohnung", "concept_name": "Biberburg"},
        "222": {"code": "F1", "name": "F1 - Ferienwohnung", "concept_name": "Felsenpfad"},
        "333": {"code": "F1F", "name": "F1F - Ferienwohnung", "concept_name": "Felsenpfad"},
        "444": {"code": "L4", "name": "L4 - Ferienwohnung", "concept_name": "Lichtung"},
        "555": {"code": "L8", "name": "L8 - Ferienwohnung", "concept_name": "Lichtblick"},
        "666": {"code": "L1", "name": "L1 - Ferienwohnung"},  # no concept_name
    },
    "default_apartment": {"code": "UNK", "name": "Unbekannt"},
}


def test_build_lookups_maps_concept_to_uppercase_codes():
    concept_to_codes, smoobu_id_to_code = build_lookups(FIXTURE)
    assert concept_to_codes["biberburg"] == {"B7"}
    assert smoobu_id_to_code["111"] == "B7"


def test_build_lookups_one_name_two_codes():
    concept_to_codes, _ = build_lookups(FIXTURE)
    assert concept_to_codes["felsenpfad"] == {"F1", "F1F"}


def test_build_lookups_skips_apartments_without_concept_name():
    concept_to_codes, smoobu_id_to_code = build_lookups(FIXTURE)
    assert "L1" not in {c for codes in concept_to_codes.values() for c in codes}
    assert smoobu_id_to_code["666"] == "L1"  # still resolvable by id


def test_codes_in_text_detects_concept_from_unterkunftsname():
    concept_to_codes, _ = build_lookups(FIXTURE)
    text = "Urlaubsmagie - Ferienwohnung Biberburg - mit Balkon"
    assert codes_in_text(text, concept_to_codes) == {"B7"}


def test_codes_in_text_distinguishes_similar_names():
    # "Lichtung" (L4) must not match "Lichtblick" (L8) and vice versa.
    concept_to_codes, _ = build_lookups(FIXTURE)
    assert codes_in_text("... Ferienwohnung Lichtung ...", concept_to_codes) == {"L4"}
    assert codes_in_text("... Ferienwohnung Lichtblick ...", concept_to_codes) == {"L8"}


def test_codes_in_text_no_partial_word_match():
    # "Licht" alone is not a concept name → no match.
    concept_to_codes, _ = build_lookups(FIXTURE)
    assert codes_in_text("nur Licht hier", concept_to_codes) == set()


def test_codes_in_text_empty_or_none():
    concept_to_codes, _ = build_lookups(FIXTURE)
    assert codes_in_text("", concept_to_codes) == set()
    assert codes_in_text(None, concept_to_codes) == set()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:\Users\admin\Documents\FlaskApp && python -m pytest ChatBotAI/tests/test_apartment_names.py -v`
Expected: FAIL — `ModuleNotFoundError` / `ImportError` (module not created yet).

- [ ] **Step 3: Write the helper module**

Create `ChatBotAI/services/apartment_names.py`:

```python
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


def _load_config():
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_lookups():
    global _lookups
    if _lookups is None:
        try:
            _lookups = build_lookups(_load_config())
        except Exception as e:  # missing/corrupt config must not break matching
            logger.warning("apartment_names: could not load config (%s); using empty lookups", e)
            _lookups = ({}, {})
    return _lookups


def code_from_smoobu_id(smoobu_apartment_id):
    """UPPERCASE code for a Smoobu apartment id, or None."""
    if not smoobu_apartment_id:
        return None
    return _get_lookups()[1].get(str(smoobu_apartment_id))


def codes_from_property_text(text: str):
    """UPPERCASE codes whose concept name appears as a whole word in `text`."""
    return codes_in_text(text, _get_lookups()[0])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:\Users\admin\Documents\FlaskApp && python -m pytest ChatBotAI/tests/test_apartment_names.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
cd C:\Users\admin\Documents\FlaskApp\ChatBotAI
git add services/apartment_names.py tests/test_apartment_names.py
git commit -m "feat(email-backfill): apartment code<->concept-name resolver

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Populate `concept_name` in `apartment_config.json`

Add the concept names (authoritative source: the Notion "Neuer Name" table). Written by a one-off script keyed on `code` to avoid hand-edit errors across 50+ entries. B7→Biberburg is verified against a live Booking email.

**Files:**
- Modify: `apartment_config.json` (FlaskApp root)
- Create (throwaway, committed for reproducibility): `ChatBotAI/scripts/add_concept_names.py`
- Test: `ChatBotAI/tests/test_apartment_names.py` (add real-config assertions)

**Interfaces:**
- Consumes: `build_lookups`, `code_from_smoobu_id`, `codes_from_property_text` from Task 1.
- Produces: `apartment_config.json` entries gain `"concept_name"` where a mapping exists.

- [ ] **Step 1: Write the populate script**

Create `ChatBotAI/scripts/add_concept_names.py`:

```python
"""One-off: add `concept_name` to apartment_config.json from the Notion table.

Keyed on UPPERCASE code. Idempotent. Run from anywhere:
    python -m ChatBotAI.scripts.add_concept_names
Prints which codes were set and which config apartments had no mapping.
"""
import json
import os

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "apartment_config.json",
)

# UPPERCASE code -> concept name (Notion "Neuer Name" table, 2026-07-01).
# NOTE: config code "fO" uppercases to "FO"; it is the F0 unit -> Felsenfreund.
CONCEPT_BY_CODE = {
    "F0": "Felsenfreund", "FO": "Felsenfreund",
    "F1": "Felsenpfad", "F1F": "Felsenpfad",
    "F1B": "Fledermaus", "F2": "Forellensprung", "F3": "Frischluft", "F4": "Farngrün",
    "UT": "Moosgrund", "FAMZI": "Morgenlicht", "ZI1": "Malerblick", "ZI2": "Mühlrad",
    "UO0": "Unterholz", "UO1": "Uferhang", "UO3": "Uhunest",
    "HW1": "Höhenzug", "HW2": "Honigfels", "HW3": "Haselmaus", "HW1B": "Hirschkäfer",
    "HW2B": "Himmelblau", "HW3B": "Heidelbeere", "HW4B": "Hochgefühl", "HW13": "Himmelsleiter",
    "GK2": "Gipfelpfad", "GK3": "Glühwürmchen", "BA2": "Bachrauschen",
    "W2": "Wasseramsel", "W3": "Wanderfalke", "W4": "Wildblume", "W5": "Waldweg", "W6": "Wiesengrün",
    "L4": "Lichtung", "L5": "Libelle", "L6": "Luchs", "L7": "Lerchenlied", "L8": "Lichtblick", "L9": "Laubfrosch",
    "H1": "Tagpfauenauge", "H2": "Tautropfen", "H4": "Tagtraum", "H5": "Talruhe", "H6": "Turmfalke",
    "S1": "Sandsteinidyll", "S2": "Sonnenfels", "S3": "Steinpfad",
    "B1": "Blattwerk", "B2": "Blütenmeer", "B3": "Buntspecht", "B5": "Brombeere",
    "B6": "Butterblume", "B7": "Biberburg", "B8": "Bergsteigersuite",
    "R1": "Rotmilan", "R2": "Ruheort", "R3": "Rothirsch",
}


def main():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    set_codes, unmapped = [], []
    for entry in config.get("apartments", {}).values():
        code = (entry.get("code") or "").strip().upper()
        if code in CONCEPT_BY_CODE:
            entry["concept_name"] = CONCEPT_BY_CODE[code]
            set_codes.append(code)
        else:
            unmapped.append(entry.get("code"))

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)
        f.write("\n")

    print(f"Set concept_name on {len(set_codes)} apartments: {sorted(set_codes)}")
    print(f"No mapping for {len(unmapped)} config apartments: {sorted(c for c in unmapped if c)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the script**

Run: `cd C:\Users\admin\Documents\FlaskApp && set PYTHONIOENCODING=utf-8 && python -m ChatBotAI.scripts.add_concept_names`
Expected: prints "Set concept_name on ~52 apartments: [...]" and lists any unmapped codes (e.g. `L1`). Confirm B7, L4, F1 appear in the set list.

- [ ] **Step 3: Verify the diff is clean (only concept_name added)**

Run: `cd C:\Users\admin\Documents\FlaskApp && git -C . diff --stat apartment_config.json`
Expected: only `apartment_config.json` changed; inspect `git diff apartment_config.json` shows only added `"concept_name": "..."` lines (indent preserved at 4 spaces, umlauts intact, not escaped). If the whole file reformatted, STOP and fix the dump settings.

- [ ] **Step 4: Add real-config assertions to the test file**

Append to `ChatBotAI/tests/test_apartment_names.py`:

```python
from ChatBotAI.services.apartment_names import (
    codes_from_property_text, code_from_smoobu_id,
)


def test_real_config_resolves_biberburg_to_b7():
    # Verified against a live Booking Unterkunftsname string.
    assert "B7" in codes_from_property_text(
        "Urlaubsmagie - Ferienwohnung Biberburg - mit Balkon"
    )


def test_real_config_resolves_lichtung_to_l4():
    assert "L4" in codes_from_property_text("... Ferienwohnung Lichtung ...")


def test_real_config_smoobu_id_resolves_to_code():
    # 1234047782495519188 is B7 in apartment_config.json.
    assert code_from_smoobu_id("1234047782495519188") == "B7"
    assert code_from_smoobu_id("does-not-exist") is None
    assert code_from_smoobu_id(None) is None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd C:\Users\admin\Documents\FlaskApp && python -m pytest ChatBotAI/tests/test_apartment_names.py -v`
Expected: PASS (all, including the 3 new real-config tests).

- [ ] **Step 6: Commit**

```bash
cd C:\Users\admin\Documents\FlaskApp
git add apartment_config.json
git -C ChatBotAI add scripts/add_concept_names.py tests/test_apartment_names.py
git -C ChatBotAI commit -m "feat(email-backfill): populate apartment concept_name from Notion table

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

Note: `apartment_config.json` is at the FlaskApp root, tracked by the **parent** repo, while the script/tests are in the **nested** ChatBotAI repo. Stage `apartment_config.json` in the parent (`git add apartment_config.json`) and commit it there separately, or commit both — but the concept_name data belongs with the parent's config. Confirm with the user which repo should carry the config change before pushing; committing locally in both trees is safe.

---

### Task 3: Wire code-aware matching into `email_reconcile.py`

Attach each conversation's resolved code, then use it in scoring: boost on match, soft-veto on mismatch, fall back otherwise.

**Files:**
- Modify: `ChatBotAI/services/email_reconcile.py` (import; `_candidate_views` ~line 547-556; `score_conversation_match` ~line 398-399)
- Test: `ChatBotAI/tests/test_email_reconcile.py` (add scoring tests)

**Interfaces:**
- Consumes: `code_from_smoobu_id`, `codes_from_property_text` from Task 1.
- Produces: `conv["apartment_code"]` key in `_candidate_views` dicts; updated `score_conversation_match` behavior.

- [ ] **Step 1: Write the failing scoring tests**

Append to `ChatBotAI/tests/test_email_reconcile.py`:

```python
from ChatBotAI.services.email_reconcile import (
    ParsedNotification, score_conversation_match,
)


def _booking_notif(name="Franziska Wandelmaier",
                   prop="Urlaubsmagie - Ferienwohnung Biberburg - mit Balkon",
                   check_in="2026-07-05", check_out="2026-07-10"):
    import datetime
    return ParsedNotification(
        platform="booking", gmail_id="g1", thread_id="t1", guest_name=name,
        message_text="Hallo", sent_at=None, property_name=prop,
        check_in=datetime.date.fromisoformat(check_in),
        check_out=datetime.date.fromisoformat(check_out), booking_ref="123",
    )


def _conv(name="Franziska Wandelmaier", apartment_code="B7",
          property_name="B7", check_in="2026-07-05", check_out="2026-07-10"):
    return {
        "channel": "booking", "guest_name": name, "apartment_code": apartment_code,
        "property_name": property_name, "check_in": check_in, "check_out": check_out,
    }


def test_booking_code_match_boosts_to_auto_insert():
    # name(0.5) + check_in(0.15) + check_out(0.15) + code match(0.3) -> capped 1.0
    score = score_conversation_match(_booking_notif(), _conv())
    assert score >= 0.95


def test_booking_code_mismatch_soft_vetoes():
    # Email is Biberburg (B7); conversation is Lichtung (L4). Same name+dates.
    score = score_conversation_match(_booking_notif(), _conv(apartment_code="L4"))
    assert score < 0.8          # cannot auto-insert
    assert score == 0.30        # 0.80 - 0.50 soft veto


def test_booking_falls_back_when_conv_has_no_code():
    # No apartment_code on conv -> old token-overlap path. "Biberburg" vs "B7"
    # share no token, so property adds nothing; name+dates = 0.80.
    conv = _conv(apartment_code=None, property_name="B7")
    score = score_conversation_match(_booking_notif(), conv)
    assert abs(score - 0.80) < 1e-9


def test_booking_falls_back_when_email_concept_absent():
    # Property text has no known concept name -> fall back; name+dates = 0.80.
    notif = _booking_notif(prop="Urlaubsmagie - Ferienwohnung - mit Balkon")
    score = score_conversation_match(notif, _conv())
    assert abs(score - 0.80) < 1e-9
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:\Users\admin\Documents\FlaskApp && python -m pytest ChatBotAI/tests/test_email_reconcile.py -k "code_match or soft_veto or falls_back" -v`
Expected: FAIL — `test_booking_code_match_boosts_to_auto_insert` and `test_booking_code_mismatch_soft_vetoes` fail (current code ignores `apartment_code`, so match gives 0.80 not ≥0.95, and mismatch gives 0.80 not 0.30). Fall-back tests may already pass.

- [ ] **Step 3: Add the import**

In `ChatBotAI/services/email_reconcile.py`, after the existing `from .guest_matching import normalize_name` (line 17), add:

```python
from .apartment_names import code_from_smoobu_id, codes_from_property_text
```

- [ ] **Step 4: Attach `apartment_code` in `_candidate_views`**

In `_candidate_views` (~line 547), add the `apartment_code` key to the appended dict:

```python
        views.append({
            'conversation_id': conv.id,
            'channel': channel,
            'guest_name': guest.name if guest else None,
            # Smoobu conversation subjects are generic ("Reservation 12345"), which
            # would never overlap a real property name — fall back to None instead.
            'property_name': prop.name if prop else None,
            'apartment_code': code_from_smoobu_id(prop.smoobu_apartment_id) if prop else None,
            'check_in': conv.check_in,
            'check_out': conv.check_out,
        })
```

- [ ] **Step 5: Replace the property scoring block in `score_conversation_match`**

Replace the existing two lines (~398-399):

```python
    if _property_overlap(notif.property_name, conv.get('property_name')):
        score += 0.3
```

with:

```python
    # Property signal. For Booking, prefer exact apartment-code matching: the
    # email's Unterkunftsname carries the concept name ("Biberburg" = B7) while our
    # Property stores the code, so the loose token overlap is always 0 for Booking.
    # Match boosts; mismatch soft-vetoes (queues for review, blocks auto-insert).
    email_codes = codes_from_property_text(notif.property_name) if notif.platform == 'booking' else set()
    conv_code = conv.get('apartment_code')
    if email_codes and conv_code:
        if conv_code.upper() in email_codes:
            score += 0.30
        else:
            score = max(0.0, score - 0.50)
    elif _property_overlap(notif.property_name, conv.get('property_name')):
        score += 0.30
```

- [ ] **Step 6: Run the new scoring tests to verify they pass**

Run: `cd C:\Users\admin\Documents\FlaskApp && python -m pytest ChatBotAI/tests/test_email_reconcile.py -k "code_match or soft_veto or falls_back" -v`
Expected: PASS (4 passed).

- [ ] **Step 7: Run the FULL suite to verify no regression**

Run: `cd C:\Users\admin\Documents\FlaskApp && set PYTHONIOENCODING=utf-8 && python -m pytest ChatBotAI/tests -v`
Expected: PASS — all prior tests still green (209+ from prior sessions) plus the new ones. If any existing `score_conversation_match` test breaks, it likely relied on `_property_overlap` for a Booking case; re-check against the spec and fix the test only if it asserted the now-dead behavior.

- [ ] **Step 8: Commit**

```bash
cd C:\Users\admin\Documents\FlaskApp\ChatBotAI
git add services/email_reconcile.py tests/test_email_reconcile.py
git commit -m "feat(email-backfill): code-aware Booking property matching (boost + soft-veto)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Mapping in `apartment_config.json` → Task 2. ✓
- Helper module with `concept_to_codes` / `smoobu_id_to_code`, whole-word longest-first detection → Task 1. ✓
- `_candidate_views` attaches `apartment_code` → Task 3 Step 4. ✓
- Scoring: booking-only, both-resolve boost/veto, fallback → Task 3 Step 5. ✓
- Soft-veto −0.50 → Task 3 (constant matches spec). ✓
- One-name-two-codes, similar-name distinction, missing config field, no-Property fallback → Task 1 & Task 3 tests. ✓
- No migration / shadow-mode safety → Global Constraints; no DB code touched. ✓

**Placeholder scan:** No TBD/TODO. Every code step has full code. The one judgment call (`fO`→F0) is made explicit with both `F0` and `FO` keys in the mapping and a note.

**Type consistency:** `build_lookups` returns `(concept_to_codes: dict[str,set], smoobu_id_to_code: dict[str,str])`; consumed as `[0]`/`[1]` in wrappers. `codes_from_property_text`/`code_from_smoobu_id` names match between Task 1 (definition), Task 3 (import + use). `conv['apartment_code']` produced in Task 3 Step 4, consumed in Step 5 and in tests. Codes uppercase on both sides (`code.upper()` in build_lookups, `conv_code.upper()` in scoring). Consistent.

**Open item for the user (Task 2 Step 6):** which repo carries `apartment_config.json` (parent FlaskApp vs the config's natural home) — confirm before push. Committing locally in the parent tree is safe and reversible.
