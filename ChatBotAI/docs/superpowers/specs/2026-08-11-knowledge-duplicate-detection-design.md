# Duplicate detection for Wissensdatenbank entries

**Date:** 2026-08-11
**Status:** design approved, not yet implemented

## Problem

Neither knowledge save path checks whether the fact is already stored:

- `routes.py` `api_create_knowledge` — the manual form, saves blind.
- `routes.py` `api_extract_knowledge_from_message` — the 🎓 per-message button,
  saves **several entries per click**, blind.

The 🎓 path is the risk. The team is encouraged to use it, it produces multiple
rows per click, and it gives no feedback about what it wrote. Clicking it on two
messages that mention the same fact silently produces two rows.

### Measured state (2026-08-11, live DB)

- 53 entries total — 39 `source='manual'`, 14 `source='notion'`.
- **Zero exact duplicates.**
- One near-duplicate: `Gästekarte` and `Gästekarte in RD`, same category, same
  scope.

So this is preventative, not a cleanup. The KB is small enough today that the
problem is invisible; the mechanism that creates it is wide open.

### Secondary finding

`api_extract_knowledge_from_message` never sets `source`, so AI-extracted rows
fall back to the `'manual'` default. All 39 non-Notion entries claim to be
hand-typed. The provenance column currently cannot distinguish them.

## Design

### Matching rule

Exact match on a **normalised label within the same scope**. Chosen over fuzzy
and AI-semantic matching: it is instant, free, and has no false positives. The
🎓 button is already the slowest thing in the app and must not gain an AI call.

Normalisation runs in **Python, not SQL**: `casefold()`, collapsed internal
whitespace, stripped trailing punctuation. SQLite's `LOWER()` is ASCII-only and
would let `Gästekarte` and `gästekarte` both through. At 53 rows a full scan of
the candidate scope costs nothing.

"Same scope" means the `(property_id, street)` pair matches exactly. A fact
stored for one room does not block the same fact stored globally — those are
deliberately different entries. Category must also match.

Note on `street`: the manual create and update routes never read or write it,
so entries from the form always have `street = NULL`. Only the 🎓 path sets it
(`scope='street'`). The helper takes `street` as a parameter anyway so the two
callers share one comparison; the manual callers pass `None`. **Do not add
street handling to the form as part of this change** — a street-scoped entry
and a global entry with the same label are different scopes and should both be
allowed to exist.

### Shared helper

```python
def _find_duplicate_knowledge(category, label, property_id, street, exclude_id=None):
    """Return an existing KnowledgeEntry with the same normalised label in the
    same scope, or None."""
```

One helper, three call sites. Putting the guard in each caller instead would
leave whichever caller is added next unprotected.

### Call site 1 — manual create (`POST /api/knowledge`)

On a hit, return `409` with the existing entry:

```json
{"error": "...", "existing": {"id": 42, "label": "...", "value": "..."}}
```

The form shows a warning naming the existing entry and a button to open it for
editing. The save is refused; nothing is overwritten without a decision. The
team can still deliberately create a second entry by choosing a different label.

### Call site 2 — update (`PUT /api/knowledge/<id>`)

Same check with `exclude_id=<id>`. Without it, renaming entry A to entry B's
label creates the duplicate through the back door.

### Call site 3 — 🎓 extraction (`POST /api/messages/<id>/extract-knowledge`)

Filter the AI's proposed entries against the KB **and against each other** — a
single extraction can emit the same fact twice. Save the remainder.

Response gains a `skipped` count:

```json
{"saved": 2, "skipped": 1, "entries": [...]}
```

The toast reports both: `"2 gespeichert, 1 bereits bekannt"`. No dialog, no
picker — the button keeps behaving the way the team already knows.

Also set `source='ai'` on entries created here.

## Error handling

Duplicate detection is a validation result, not an error condition: the `409`
carries the existing entry so the UI can act on it. The 🎓 path never fails on a
duplicate — skipping is the normal outcome and is reported in the counts.

If `label` is empty or whitespace-only the existing `400` validation fires
first; the duplicate check never sees it.

## Testing

One file, `tests/test_knowledge_duplicates.py`:

1. Exact duplicate blocked on create (409, existing entry returned).
2. Case and whitespace variants caught (`" gästekarte "` vs `"Gästekarte"`).
3. Same label in a different scope allowed (room vs global vs street).
4. Same label in a different category allowed.
5. Update excluding self: saving an entry unchanged succeeds; renaming it onto
   another entry's label is blocked.
6. 🎓 batch skips entries already in the KB, and de-duplicates within one batch.
7. 🎓 sets `source='ai'`.

## Out of scope

- Fuzzy or embedding-based matching. Revisit only if the team reports missed
  duplicates in practice.
- AI semantic comparison — costs a call per save on the path that is already
  timing out (see the "Wissensextraktion fehlgeschlagen" reports).
- Retroactive cleanup of the existing 53 entries. The single near-duplicate is a
  manual decision, and the two entries may be deliberately distinct.
- Backfilling `source='ai'` on historical rows — unknowable after the fact.
