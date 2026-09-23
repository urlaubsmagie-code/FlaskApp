# Design — Booking email matching via apartment concept names

**Date:** 2026-07-01
**Branch:** `feat/notion-knowledge-sync`
**Status:** approved, pre-implementation

## Problem

Booking guest-message notification emails (`@guest.booking.com`) name the
apartment in the body's `Unterkunftsname:` field using the **new concept name**,
e.g.:

```
Unterkunftsname:
Urlaubsmagie - Ferienwohnung Biberburg - mit Balkon
```

"Biberburg" is apartment **B7**. But our DB stores properties by **code**
(`Property.name` values are `"B7"`, `"LH - W2"`, `"Seb3 - H1"`, `"F0 - Seb (27)"`,
…). The matcher's `_property_overlap` compares the parsed email property string
against `Property.name` by shared word tokens. `"…Biberburg…"` and `"B7"` share
no token, and `"b7"` is 2 chars so it is filtered out anyway.

**Consequence:** the property component of `score_conversation_match` contributes
**0.0 for every Booking email today.** The observed 0.80 confidence cluster is
purely `name (0.5) + check_in (0.15) + check_out (0.15)` — property is dead
weight. The concept↔code mapping is not derivable by rule (e.g. Lichtenhain
`H1→Tagpfauenauge`, `H4→Tagtraum`), so it must be supplied explicitly.

## Goal

Make apartment identity a real, reliable signal in Booking email matching by
resolving both sides to a canonical apartment **code** and comparing them:

- **Match** → boost confidence (revives the +0.3 property signal).
- **Mismatch** → soft veto: cannot auto-insert, but still queues for human review
  (disambiguates repeat guests / same-date collisions).

Airbnb behavior is unchanged in scope (Airbnb subjects also carry concept names,
but Airbnb never auto-inserts today; this design targets Booking, with the helper
written generically so Airbnb can adopt it later).

## Non-goals

- No schema/migration change (config file + existing AISettings only).
- No change to the auto-insert gate. Booking auto-insert stays behind
  `email_autoinsert_booking` (currently `false`, shadow mode). This design only
  changes **scores and queue routing**; nothing new auto-inserts until the user
  flips that flag.
- No live Notion dependency at runtime.

## Design

### 1. Mapping data — `apartment_config.json`

Add one optional field, `concept_name`, to each apartment entry (already keyed by
`smoobu_apartment_id`):

```json
"1234047782495519188": {
  "code": "B7",
  "name": "B7 - Ferienwohnung",
  "concept_name": "Biberburg",
  "description": "Apartamento B7 en Sebnitz"
}
```

- **Value source:** pull the authoritative concept names **once** from the Notion
  page (the screenshotted table), then write them statically into
  `apartment_config.json`. Sourcing from Notion (not hand-transcription from the
  image) avoids a single wrong entry mis-routing matches.
- Apartments absent from the Notion table (e.g. `L1`) get **no** `concept_name`
  and fall back to today's behavior. No entry is fabricated.

### 2. Code resolution helper — `services/apartment_names.py`

Loads `apartment_config.json` once (module-level cache) and builds:

- `concept_to_codes: dict[str, set[str]]` — lowercased concept name → set of codes
  (a set because `F1F/F1 → Felsenpfad` maps one name to two codes).
- `smoobu_id_to_code: dict[str, str]` — `smoobu_apartment_id` → code.

Public functions:

- `code_from_smoobu_id(smoobu_apartment_id) -> str | None`
- `codes_from_property_text(text) -> set[str]` — scans `text` for any known
  concept name as a **whole word** (regex word boundaries, longest-match-first to
  avoid a shorter name masking a longer one), returns the union of matched code
  sets. Case-insensitive. Returns empty set if none found.

Concept names are single distinctive German nouns (Felsenfreund, Biberburg,
Sandsteinidyll), so whole-word matching has negligible false-hit risk. Config path
resolves relative to the FlaskApp root (same location `app.py` reads it from).

### 3. Wiring into `email_reconcile.py`

**`_candidate_views`** — add resolved code per conversation:

```python
'apartment_code': code_from_smoobu_id(prop.smoobu_apartment_id) if prop else None,
```

**`score_conversation_match`** — after the existing name/date scoring, replace the
Booking property contribution with code-aware logic:

```python
email_codes = codes_from_property_text(notif.property_name)   # set, may be empty
conv_code = conv.get('apartment_code')                        # str or None

if notif.platform == 'booking' and email_codes and conv_code:
    if conv_code in email_codes:
        score += 0.30            # match: revive the property signal
    else:
        score = max(0.0, score - 0.50)   # soft veto: below 0.80 threshold, still queueable
else:
    # one side (or neither) resolved → existing loose token overlap, unchanged
    if _property_overlap(notif.property_name, conv.get('property_name')):
        score += 0.30
```

Notes:
- The `-0.50` soft veto is chosen so a full-strength `name+dates = 0.80` match
  drops to `0.30` — well under the 0.80 auto-insert threshold, so it queues for
  review rather than auto-inserting or disappearing.
- For Airbnb, the `else` branch runs (existing behavior) — no regression.
- The final `min(score, 1.0)` cap is retained.

### 4. Data flow

```
Booking email → parse Unterkunftsname → codes_from_property_text() → email_codes {B7}
Conversation  → Property.smoobu_apartment_id → code_from_smoobu_id() → conv_code "B7"
score_conversation_match(): B7 ∈ {B7} → +0.30  (or mismatch → soft veto)
```

## Edge cases

- **Concept name not found in email text** → `email_codes` empty → fall back to
  token overlap. (Guards against Booking body-format drift.)
- **Conversation has no Property / no smoobu_apartment_id** → `conv_code` None →
  fall back. (Smoobu "Reservation N" convs.)
- **One name → multiple codes** (`Felsenpfad → {F1, F1F}`) → match if `conv_code`
  is in the set.
- **Multiple concept names in one string** → union of code sets (rare; safe).
- **Config lacks `concept_name` for an apartment** → that apartment never
  contributes an email-side code; falls back.

## Testing

Unit tests (`tests/`, no DB migration needed):
- `codes_from_property_text` on the real Biberburg `Unterkunftsname` string → `{B7}`.
- One-name-two-codes resolution (`Felsenpfad → {F1, F1F}`).
- Whole-word matching does not partial-match (e.g. a substring collision case).
- Code match → `+0.30` boost; end-to-end Booking notif+conv reaching ≥0.95.
- Code mismatch → soft veto drops a would-be 0.80 to below threshold (queued, not
  auto-inserted, not dropped).
- Both-unresolved path preserves existing `_property_overlap` behavior.

Full suite must stay green.

## Rollout / safety

- Shadow mode unaffected: `email_autoinsert_booking=false` means nothing
  auto-inserts; this only re-scores and re-routes queue candidates.
- Reversible: removing `concept_name` fields (or the helper import) reverts to
  current behavior with no data loss.

## Files touched

- `apartment_config.json` — add `concept_name` per apartment (from Notion).
- `ChatBotAI/services/apartment_names.py` — **new** helper module.
- `ChatBotAI/services/email_reconcile.py` — `_candidate_views` + `score_conversation_match`.
- `ChatBotAI/tests/test_apartment_names.py` (+ additions to email-reconcile tests) — **new**.
