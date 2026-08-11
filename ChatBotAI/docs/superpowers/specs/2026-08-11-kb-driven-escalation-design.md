# KB-Driven Escalation Topics — Design

**Date:** 2026-08-11
**Status:** Approved (design), pending implementation plan

## Problem

The Eskalation area of the Wissensdatenbank (`esc_maintenance`, `esc_cleanliness`,
`esc_noise`, `esc_payment`, `esc_access`, `esc_emergency`, `esc_other`) looks like it
configures what UMI escalates. It does not. Nothing reads those rows for that purpose:

- Escalation is triggered in exactly three places today, none of them the KB:
  1. `MessageRouter._URGENT_KEYWORDS` (`services/message_router.py:563`) — a hardcoded
     tuple of ~90 DE/EN phrases, substring-matched on **every** incoming guest message.
     This is the only detector that works while `master_ai_enabled=false`, which is the
     current production state.
  2. The `[[ESCALATE: reason]]` marker the model emits, driven by CASE 2/CASE 3 rules
     hardcoded in `prompts/rich/guest_reply.txt:53-61`. Only fires when UMI answers.
  3. The manual ⋮ button / `POST /api/conversations/<id>/escalate`.
- `esc_*` entries are additionally **stripped out of the AI prompt** at
  `services/ai_service.py:857` (`[e for e in knowledge_entries if not (e.get('category')
  or '').startswith('esc')]`), so they don't even inform UMI's answers.

Net effect: the team can add, edit and delete Eskalation entries all day and nothing
about the system's behaviour changes. The category is a silently inert UI.

**And it is worse than inert — an Eskalation entry cannot be saved at all.**
`updateCategoryOptions` (`static/js/knowledge.js:326-327`) hides the Information field
on the escalation tab ("category + label is enough"), but that textarea carries
`required` in `templates/chatbot/knowledge.html:121` and the API rejects an empty `value`
(`routes.py:5011`). A hidden `required` control makes the browser block submit outright.
So the reason the Eskalation area is empty is not that nobody filled it in — nobody
*could*. This design fixes that as part of the work.

## Goal

The Eskalation area becomes the single source of truth for what gets escalated, editable
by the team, and honoured on both detection paths:

- **Always-on path** — a matching guest message escalates the chat whether UMI is
  answering, a human is answering, or the master AI switch is off.
- **UMI path** — when UMI is chatting, she also escalates on those topics when the guest
  phrases it in a way no trigger word catches.

## Non-Goals

Explicitly out of scope, agreed during design:

- No AI classifier call per incoming message (cost, latency, and it fails exactly when
  Ollama/cloud is down — the moment escalation matters most).
- No fuzzy/typo/stemming matching. Case-insensitive substring only, as today.
- No per-topic "UMI soll hier nicht mehr antworten" checkbox.
- No `escalation_reason` DB column (still only logged, as today).
- No Notion property mapping for trigger words (see Known Limitations).

## Design

### 1. Data model

One new column on `knowledge_entry`:

```python
trigger_words = db.Column(db.Text, nullable=True)
```

Migration **p23** (`p23_knowledge_trigger_words.py`), following p22.

Field meanings for `esc_*` rows:

| Column | Meaning | Reaches the AI? |
|---|---|---|
| `label` | Topic name, e.g. `Aussperrung` | **Yes** — names only |
| `trigger_words` | Comma-separated phrases, e.g. `ausgesperrt, locked out, komme nicht rein` | No |
| `value` | Internal team note, e.g. `Hausmeister 0171… anrufen` | **Never** |

`trigger_words` is ignored for non-escalation categories. Scope (`property_id`, `street`)
keeps its existing meaning and selector.

`value` becomes **optional for `esc` categories only** (a topic may have no internal note);
it stays required everywhere else. This is what unblocks saving escalation entries.

Matching semantics, unchanged from the current code so behaviour is identical for the
seeded data: split on comma, strip, lowercase, drop empties, then substring-match against
the lowercased message body. First match wins.

### 2. Detector — always-on path

`MessageRouter._URGENT_KEYWORDS` and the classmethod `_urgent_keyword(text)` are replaced
by a lookup against the DB:

- New classmethod `KnowledgeEntry.load_escalation_topics(conversation)` in `models.py`,
  reusing the scope branches already implemented in `load_for_conversation_context`
  (global rows with `property_id IS NULL AND street IS NULL`, plus this conversation's
  property, plus that property's street). Filtered to categories starting with `esc` and
  `trigger_words` non-empty. Returns `[(label, [words…]), …]`.
- `MessageRouter._match_escalation_topic(conversation, text)` returns `(label, word)` or
  `None`.
- Call site stays where it is — Step 6.6 in `process_incoming_message`
  (`services/message_router.py:216-232`), **inside** the existing 48h recency gate and the
  `not conversation.escalated` guard. The recency gate is load-bearing: without it a full
  Smoobu historical sync replays years of messages and would flag and push-notify
  thousands of closed stays.
- Escalation reason string becomes `topic:<label> (<word>)` instead of `keyword:<word>`.
- `_apply_escalation(..., pause_ai=False)` for this path is unchanged: a false-positive
  trigger word must never silently switch a chat's auto-respond off permanently.

One extra `SELECT` per recent incoming message. At ~150 messages/day this needs no cache;
a `ponytail:` comment records that a cache is the upgrade path if volume grows.

### 3. Detector — UMI path

`_build_guest_reply_prompt` (`services/ai_service.py:825`) gains an `escalation_topics`
parameter: a deduplicated list of **labels only**, no words, no notes. Rendered in both
`prompts/rich/guest_reply.txt` and `prompts/compact/guest_reply.txt` as an addition to
CASE 3, e.g.:

```
Diese Themen immer eskalieren: Aussperrung, Wasserschaden, Zahlung/Erstattung, Lärm
```

The existing hardcoded CASE 3 rules (complaints, disputes, money, safety) stay as a floor;
topics add to them, never replace them. No extra AI call and no added latency — this is
text in a system prompt that is already being built.

The `esc`-stripping filter at `ai_service.py:857` **stays exactly as it is**, so `value`
(the internal note) still cannot reach the model — only the labels are rendered.

The labels are derived from the `knowledge_entries` list already being passed in
(`load_for_conversation_context` returns `esc_*` rows today; only the prompt builder drops
them), so **no call site changes** — not `message_router._generate_ai_response`, not the
three suggest endpoints in `routes.py`. One supporting change is needed:
`ContextFilter._filter_knowledge_entries` must always retain `esc` rows instead of
subjecting them to keyword scoring and the 5-entry cap, otherwise the topic list would
silently vary from message to message.

### 4. UI

`static/js/knowledge.js` + `templates/chatbot/knowledge.html`:

- New "Auslöser-Wörter" input, rendered **only** when the selected category starts with
  `esc` (the same prefix test used everywhere else, so the legacy `escalation` category is
  covered too). Helper text: comma-separated, matched anywhere in the message, case-insensitive.
- The Information field is **shown again** on the escalation tab (it is hidden today) and
  relabelled for `esc` categories: *Interne Notiz — nur fürs Team, UMI sieht das nie.*
  Its `required` attribute is dropped; the API keeps enforcing it for non-`esc` categories.
- `CATEGORY_DESCRIPTIONS` for the seven `esc_*` categories reworded from "content bucket"
  to "what gets escalated".
- Trigger words shown on the entry card so the list is readable at a glance.
- i18n keys added for DE and EN in `static/js/i18n.js`.
- Cache-buster version bumped in `templates/chatbot/knowledge.html` (read the current
  value there — it changes often).

Add / edit / delete already work through the existing knowledge CRUD. No new page.

### 5. API

`routes.py` knowledge create + update endpoints accept and persist `trigger_words`
(max 2000 chars, empty string stored as `NULL`), and stop requiring `value` when the
category starts with `esc`. `KnowledgeEntry.to_dict()` includes `trigger_words`.
No new routes.

### 6. Seed

Migration p23 also inserts the current hardcoded keywords as **9 global topic rows**
(one more than the 8 mentioned during design: the noisy generic-defect words get their own
row precisely so the team can delete them without losing the specific ones):

| Label | Category | Trigger words |
|---|---|---|
| Notfall | `esc_emergency` | notfall, notarzt, feuer, brennt, polizei, rettungsdienst, einbruch, unfall, verletzt, gasgeruch, emergency, urgent, asap, fire, police, ambulance, injured |
| Wasserschaden / Schimmel | `esc_maintenance` | wasserschaden, überschwemmt, überflutet, rohrbruch, schimmel, flood, flooded, water damage, leak, mold |
| Kein Wasser / Strom / Heizung | `esc_maintenance` | kein warmwasser, kein wasser, kein strom, stromausfall, heizung defekt, heizung geht nicht, heizung kaputt, no hot water, no water, no power, no electricity, heating not working |
| Defekt / kaputt | `esc_maintenance` | kaputt, funktioniert nicht, defekt, broken, not working |
| Aussperrung / Zugang | `esc_access` | ausgesperrt, eingesperrt, komme nicht rein, schlüssel verloren, code funktioniert nicht, türe geht nicht, tür geht nicht, locked out, lost the key, lost my key, code does not work, code doesn't work |
| Zahlung / Erstattung | `esc_payment` | rückerstattung, geld zurück, stornieren, storno, abbrechen, refund, money back, cancel my booking |
| Beschwerde / Rechtliches | `esc_other` | anwalt, rechtsanwalt, beschwerde, beschweren, lawyer, complaint |
| Lärm | `esc_noise` | lärm, laut, polizei gerufen |
| Sauberkeit / Ungeziefer | `esc_cleanliness` | dreckig, schmutzig, ungeziefer, bettwanzen, kakerlaken, bed bugs, cockroach, filthy, dirty |

All rows: `property_id=NULL`, `street=NULL`, `source='manual'`, `value=''`.

The seed is idempotent — it skips insertion if any `esc_*` row with non-empty
`trigger_words` already exists — so a re-run cannot duplicate the topics.

After the seed, `_URGENT_KEYWORDS` is deleted from `services/message_router.py`.

### 7. Tests

Extend `tests/test_urgency_triage.py` (existing keyword-list assertions are rewritten
against seeded rows):

1. A topic row with a matching trigger word escalates an incoming message.
2. Deleting that row stops the escalation.
3. An apartment-scoped topic does not fire for a conversation on another property.
4. An empty Eskalation table escalates nothing (no crash, no fallback).
5. Topic **labels** appear in the built guest-reply prompt.
6. **The `value` note never appears in the built prompt** — the safety-critical assertion.
7. The 48h recency gate still suppresses replayed historical messages.

## Consequences / Accepted Risks

- **The team can break escalation.** If every Eskalation row is deleted, nothing escalates
  by trigger word. This was chosen deliberately over a hidden code fallback: behaviour the
  team cannot see on screen produces confusing bug reports ("I deleted it and it still
  escalates"). Visible and breakable beats invisible and safe.
- **Migration touches the live production DB.** Any `flask db upgrade` in this repo runs
  against prod. p23 is additive (one nullable column + 9 inserts) and idempotent, but it
  must be run deliberately, not incidentally.
- **False positives remain possible** — `kaputt`, `broken`, `dirty`, `laut` are broad. The
  difference is the team can now delete them without a code change.

## Known Limitations

- Entries synced from Notion arrive with `trigger_words = NULL` and therefore never fire
  until someone fills the field in UMI. Mapping a Notion property to `trigger_words` is a
  follow-up, not part of this work.
- Escalation still records no reason in the database; `topic:<label>` appears only in the
  log line and the push notification. Persisting it stays deferred, as before.
- Substring matching means `laut` also matches `lautstark` and, less happily, `Laut
  Beschreibung…`. Accepted — same behaviour as today, now removable by the team.
