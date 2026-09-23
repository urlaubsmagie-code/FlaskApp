# UMI Prompt Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make UMI answer only what it truly knows (documented facts + general truths) and reliably hand everything else to a human via a language-independent escalation marker, so it's safe to trust with auto-respond.

**Architecture:** Rewrite the rich + compact guest-reply prompts to a three-bucket answer/escalate policy with a hard anti-invention guard. The model signals escalation by emitting a `[[ESCALATE: reason]]` control marker on the final line; a pure helper strips the marker (so guests never see it) and surfaces the reason; the router fires the existing escalation flow (flag conversation, pause auto-respond, push the team) on that signal, keeping the old phrase detection as a fallback.

**Tech Stack:** Python, Jinja2 prompt templates, pytest, Ollama (`gpt-oss:120b-cloud` live / `gemma2:9b` local).

---

## File structure

- `services/ai_service.py` — add `parse_escalation()` static helper (pure: extract+strip marker → `(clean_text, reason)`).
- `services/message_router.py` — strip marker after generation; factor `_apply_escalation()`; trigger escalation from the marker reason (phrase detection kept as fallback).
- `prompts/rich/guest_reply.txt` — replace the knowledge-boundary + anti-hallucination sections with the three-bucket policy + marker contract (live path).
- `prompts/compact/guest_reply.txt` — same policy, terser (supersedes this session's interim edit).
- `routes.py` — strip the marker from the 3 host-facing suggestion endpoints (1183, 1419, 1520).
- `tests/test_escalation_marker.py` — new: unit tests for `parse_escalation` + phrase fallback.
- `tests/test_compact_prompt_snapshot.py` — update the existing rule test to assert the marker contract.
- `tests/test_prompt_loader.py` — add rich-prompt policy render assertions.

---

### Task 1: `parse_escalation()` helper (pure, TDD)

**Files:**
- Create: `tests/test_escalation_marker.py`
- Modify: `services/ai_service.py` (add static method to `AIService`; `re` already imported)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_escalation_marker.py
"""Unit tests for the [[ESCALATE: reason]] control-marker parser and the
phrase-based escalation fallback."""

from ChatBotAI.services.ai_service import AIService
from ChatBotAI.services.message_router import MessageRouter


def test_extracts_reason_and_strips_marker():
    txt = "Das kläre ich kurz mit dem Team und melde mich gleich.\n[[ESCALATE: money]]"
    clean, reason = AIService.parse_escalation(txt)
    assert reason == "money"
    assert "ESCALATE" not in clean
    assert clean == "Das kläre ich kurz mit dem Team und melde mich gleich."


def test_no_marker_returns_none_and_unchanged_text():
    txt = "Das WLAN-Passwort ist urlaubsmagie2026."
    clean, reason = AIService.parse_escalation(txt)
    assert reason is None
    assert clean == txt


def test_marker_is_case_and_spacing_tolerant():
    for raw in ["[[escalate:safety]]", "[[ ESCALATE : safety ]]", "[[ESCALATE safety]]"]:
        clean, reason = AIService.parse_escalation("Hallo.\n" + raw)
        assert reason == "safety", raw
        assert "[[" not in clean, raw


def test_empty_or_unknown_reason_normalises():
    clean, reason = AIService.parse_escalation("Text.\n[[ESCALATE:]]")
    assert reason == "unspecified"
    assert clean == "Text."


def test_none_input_is_safe():
    assert AIService.parse_escalation(None) == (None, None)


def test_phrase_fallback_still_detects_kollegen():
    assert MessageRouter._is_escalation_response("Ich frage kurz bei meinen Kollegen nach.") is True
    assert MessageRouter._is_escalation_response("Das WLAN-Passwort ist urlaubsmagie2026.") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_escalation_marker.py -q`
Expected: FAIL — `AttributeError: type object 'AIService' has no attribute 'parse_escalation'` (the phrase-fallback test should already pass).

- [ ] **Step 3: Implement `parse_escalation`**

Add to `services/ai_service.py` inside class `AIService` (place it just above `_clean_ai_response`, ~line 1280). `re` is already imported at module top.

```python
    _ESCALATION_MARKER_RE = re.compile(
        r'\[\[\s*ESCALATE\s*[:\s]\s*([a-zA-Z_]*)\s*\]\]', re.IGNORECASE
    )

    @staticmethod
    def parse_escalation(text):
        """Extract and strip the [[ESCALATE: reason]] control marker.

        The model emits this marker on the final line when it decides a message
        must be handled by a human. We remove it so the guest never sees it, and
        return the reason for the router to act on.

        Returns (clean_text, reason) where reason is a lowercase string
        (one of ungrounded|complaint|dispute|money|safety|approval, or
        'unspecified'), or (text, None) when no marker is present.
        """
        if not text:
            return text, None
        m = AIService._ESCALATION_MARKER_RE.search(text)
        if not m:
            return text, None
        reason = (m.group(1) or '').strip().lower() or 'unspecified'
        clean = AIService._ESCALATION_MARKER_RE.sub('', text)
        clean = re.sub(r'\n{3,}', '\n\n', clean).strip()
        return clean, reason
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_escalation_marker.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add tests/test_escalation_marker.py services/ai_service.py
git commit -m "feat(ai): add parse_escalation marker helper"
```

---

### Task 2: Rich prompt — three-bucket policy + marker contract (live path)

**Files:**
- Modify: `prompts/rich/guest_reply.txt:44-60` (replace "Knowledge boundary" + "Anti-hallucination" sections)
- Test: `tests/test_prompt_loader.py` (extend `test_rich_guest_reply_renders`)

- [ ] **Step 1: Write the failing render assertions**

In `tests/test_prompt_loader.py`, add to the end of `test_rich_guest_reply_renders`:

```python
    # Three-bucket policy + escalation marker contract must be present
    assert "[[ESCALATE:" in out
    assert "Most apartments have" in out          # anti-invention guard
    low = out.lower()
    assert "complaint" in low and "refund" in low and "safety" in low
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_prompt_loader.py::test_rich_guest_reply_renders -q`
Expected: FAIL — `assert "[[ESCALATE:" in out`.

- [ ] **Step 3: Replace the rich prompt section**

In `prompts/rich/guest_reply.txt`, replace the whole block from `# Knowledge boundary — Wissensdatenbank as the bible` (line 44) through the end of the Anti-hallucination paragraph (line 60) with:

```
# Knowledge boundary — answer only what you truly know

Sort every guest message into one of three cases.

CASE 1 — Answer yourself. Do this for:
- General truths, logic, and common sense that hold regardless of our property (e.g. "is water wet?", "is Germany in the EU?").
- Social messages: greetings, thanks, well-wishes.
- Questions whose specific answer is present in the Wissensdatenbank, reservation, or guest profile below — including documented prices, fees, check-in/out, parking, amenities, and house rules. If it is written above, just state it.

CASE 2 — Escalate (see "How to escalate"). Any question specific to OUR property, booking, prices, or local area whose answer is NOT in the data above (e.g. "are the beds blue?", "do you have a hairdryer?", "how far is the station?"). Never guess. Never invent places, restaurants, distances, prices, or opening hours.

CASE 3 — Escalate, always, even if data exists:
- Complaints, reclamations, dissatisfaction, damage.
- Disputes or arguments.
- Money matters where the guest wants money back or changed: refunds, discounts, "too expensive", cancellations, payment problems. You may state a documented price as information, but the moment the guest requests or negotiates money, escalate.
- Safety or emergencies: lockout, gas, medical, anything urgent.

Hard rule against guessing: never answer a question about our property, booking, prices, or area by reasoning from what is "usual" or "typical". "Most apartments have X" is NOT knowledge about ours. If you do not have the specific fact, escalate.

# How to escalate

When a message falls into CASE 2 or CASE 3:
1. Write a short, warm holding message to the guest IN THE GUEST'S LANGUAGE, telling them you'll check and come back (e.g. "Das kläre ich kurz mit dem Team und melde mich gleich bei dir.").
2. On the FINAL line, output this control marker exactly, with nothing after it:
[[ESCALATE: <reason>]]
where <reason> is one of: ungrounded, complaint, dispute, money, safety, approval.
The marker is removed automatically before the guest sees the message — never explain it, and never omit it when you escalate.
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_prompt_loader.py::test_rich_guest_reply_renders -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add prompts/rich/guest_reply.txt tests/test_prompt_loader.py
git commit -m "feat(prompt): three-bucket policy + escalate marker in rich prompt"
```

---

### Task 3: Compact prompt parity (supersede interim edit)

**Files:**
- Modify: `prompts/compact/guest_reply.txt` (replace the interim "Facts only: ..." paragraph added earlier this session)
- Test: `tests/test_compact_prompt_snapshot.py` (rewrite `test_compact_prompt_has_anti_invention_and_escalation_rule`)

- [ ] **Step 1: Update the test to assert the marker contract**

In `tests/test_compact_prompt_snapshot.py`, replace the body assertions of `test_compact_prompt_has_anti_invention_and_escalation_rule` (the two `assert any(...)` blocks) with:

```python
    low = out.lower()
    # Compact prompt must carry the escalate marker contract and the anti-guess rule.
    assert "[[escalate:" in low, "compact prompt missing the escalation marker contract"
    assert "most places have" in low or "most apartments have" in low, (
        "compact prompt missing the 'don't reason from typical' anti-invention guard"
    )
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_compact_prompt_snapshot.py::test_compact_prompt_has_anti_invention_and_escalation_rule -q`
Expected: FAIL — `assert "[[escalate:" in low`.

- [ ] **Step 3: Replace the compact prompt rule block**

In `prompts/compact/guest_reply.txt`, replace the paragraph that begins `Facts only: answer ONLY from the facts shown above` (added earlier this session, sits just before `{% if unanswered_count >= 2 %}`) with:

```
# Answer only what you truly know
- Answer yourself: general truths / common sense (water is wet), social chat, and facts present in the Info / reservation / profile above (including documented prices, check-in, parking, amenities, rules).
- Escalate: any question about OUR property / booking / prices / area that is NOT in the Info above (bed colour, "do you have X", distances) — never guess, never reason "most places have X".
- Always escalate, even if data exists: complaints, disputes, money problems (refunds, discounts, cancellations, payment), safety / emergencies.
To escalate: write a short holding line to the guest in their language ("Das kläre ich kurz mit dem Team und melde mich gleich"), then on the FINAL line output exactly: [[ESCALATE: <reason>]] with <reason> one of ungrounded|complaint|dispute|money|safety|approval. The marker is stripped before the guest sees it.
```

- [ ] **Step 4: Run the prompt suite to verify pass + no regression**

Run: `python -m pytest tests/test_compact_prompt_snapshot.py tests/test_prompt_loader.py -q`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add prompts/compact/guest_reply.txt tests/test_compact_prompt_snapshot.py
git commit -m "feat(prompt): compact prompt parity with marker contract"
```

---

### Task 4: Router — strip marker + reason-driven escalation (DRY refactor)

**Files:**
- Modify: `services/message_router.py` (insert strip after generation ~line 718; add `_apply_escalation`; rewrite the auto-send escalation block ~828-851)

- [ ] **Step 1: Insert marker stripping right after generation**

In `services/message_router.py`, immediately after the existing block (the `if not response_text: return None` at ~720), insert:

```python
        # Strip the [[ESCALATE: reason]] control marker so it never reaches the
        # guest, and capture the reason (None when the model did not escalate).
        response_text, escalation_reason = self.ai_service.parse_escalation(response_text)
        if not response_text:
            return None
```

- [ ] **Step 2: Add the `_apply_escalation` helper**

Add this method to `MessageRouter` (next to `_is_escalation_response`, ~line 506):

```python
    def _apply_escalation(self, conversation, reason):
        """Flag a conversation as needing a human: set escalated, pause
        auto-respond, notify the team. Idempotent-safe to call once per reply."""
        conversation.escalated = True
        conversation.escalated_at = datetime.utcnow()
        conversation.auto_respond = False
        db.session.commit()
        logger.info(
            f"[ESCALATION] Conversation {conversation.id} escalated "
            f"(reason={reason or 'phrase'}) — auto-respond paused"
        )
        if conversation.platform == 'playtest':
            playtest_log(conversation.id, 'escalation_check',
                         f'Escalation TRIGGERED (reason={reason or "phrase"}) — auto-respond paused')
        try:
            from .push_service import get_push_service
            push = get_push_service()
            if push:
                guest = conversation.guest
                push.notify_escalation(conversation, guest.name or guest.email or 'Guest')
        except Exception as e:
            logger.warning(f"Escalation push notification failed: {e}")
```

- [ ] **Step 3: Rewrite the auto-send escalation block to use the helper + reason**

Replace the existing block at ~828-851 (from the `# Check for escalation response` comment through the `except Exception as e: logger.warning(...)` of the push) with:

```python
            # Escalation — AFTER platform send, so the holding message reaches the
            # guest first. Driven by the model's [[ESCALATE]] marker (reason), with
            # the legacy Kollegen/colleague phrase kept as a fallback.
            if escalation_reason or self._is_escalation_response(response_text):
                self._apply_escalation(conversation, escalation_reason)
```

- [ ] **Step 4: Run the full suite (no regressions)**

Run: `python -m pytest -q`
Expected: PASS (existing count + Task 1 tests; no failures).

- [ ] **Step 5: Commit**

```bash
git add services/message_router.py
git commit -m "feat(router): reason-driven escalation via marker, phrase fallback retained"
```

**Note (known scope):** escalation flagging stays on the auto-send path (the auto-respond goal). In default approval-queue mode the marker is still stripped (no leak) and the human reviews the pending draft. Flagging the pending-draft path and persisting the reason to a DB column are deferred to the Real Safety Layer.

---

### Task 5: Strip the marker in host-facing suggestion endpoints

**Files:**
- Modify: `routes.py` (after each `generate_guest_response` result: lines ~1183, ~1419, ~1520)

- [ ] **Step 1: Add a strip after each suggestion is generated**

At each of the three call sites, immediately after the `ai_response = ai_service.generate_guest_response(...)` assignment completes, add:

```python
        if ai_response:
            ai_response, _ = ai_service.parse_escalation(ai_response)
```

(Apply identically at all three sites. The `_` discards the reason — suggestion endpoints only display text; they don't auto-escalate.)

- [ ] **Step 2: Verify no marker leaks (grep sanity + suite)**

Run: `python -m pytest -q`
Expected: PASS.
Run: `git grep -n "parse_escalation" routes.py`
Expected: three matches (one per suggestion endpoint).

- [ ] **Step 3: Commit**

```bash
git add routes.py
git commit -m "fix(routes): strip escalate marker from host-facing AI suggestions"
```

---

### Task 6: Behavioral smoke on the live model

**Files:** none (verification script, run manually — requires Ollama reachable with `gpt-oss:120b-cloud`).

- [ ] **Step 1: Run the scenario script**

```bash
cd /c/Users/admin/Documents/FlaskApp && PYTHONIOENCODING=utf-8 python -X utf8 - <<'PY'
from ChatBotAI.services.ai_service import AIService
svc = AIService(model='gpt-oss:120b-cloud')
kb = [{'label':'WLAN-Passwort','value':'urlaubsmagie2026','category':'general'}]
cases = [
    ("WiFi (in KB) -> ANSWER",      "Wie lautet das WLAN-Passwort?", kb),
    ("beds blue (not in KB) -> ESC","Sind die Betten blau?", None),
    ("restaurants (not in KB) -> ESC","Welche Restaurants gibt es in der Naehe?", None),
    ("refund -> ESC",               "Ich moechte mein Geld zurueck, kann ich stornieren?", None),
    ("greeting -> ANSWER",          "Hallo, wir freuen uns!", None),
    ("water wet (general) -> ANSWER","Ist Wasser nass?", None),
]
for label, q, k in cases:
    raw = svc.generate_guest_response(
        guest_profile={'name':'Anna','language':'German'},
        conversation_history=[], latest_message=q, knowledge_entries=k,
        tone='friendly_professional')
    clean, reason = AIService.parse_escalation(raw or '')
    print('='*60); print(label); print('  reply :', clean)
    print('  reason:', reason, '| marker leaked to guest text:', '[[ESCALATE' in (clean or ''))
PY
```

- [ ] **Step 2: Confirm expected behavior**

Expected observations:
- WiFi, greeting, "water wet" → a normal answer, `reason = None`.
- beds-blue, restaurants → holding message + `reason in {ungrounded}`.
- refund → holding message + `reason in {money}`.
- "marker leaked" is `False` in every case.

If a CASE-1 item escalates or a CASE-2/3 item answers with invented specifics, refine the prompt wording (Tasks 2/3) and re-run. Note non-determinism: run twice if a single sample looks off.

---

### Task 7: Playtest acceptance (manual, in the real UI)

**Files:** none.

- [ ] **Step 1:** In the Playtest chat (Debug → launcher), as the guest, send: a documented question (e.g. WiFi if a KB entry exists), an undocumented property question ("do you have a hairdryer?"), a complaint, and a refund request.
- [ ] **Step 2:** Confirm for each escalation: the guest sees a clean holding message with **no** `[[ESCALATE]]` text, and the conversation shows **escalated** with auto-respond paused (and a team push if subscribed).
- [ ] **Step 3:** Confirm the documented question is answered directly without escalation.
- [ ] **Step 4:** Report results; decide whether prompt-only is "good enough" or to proceed to the Real Safety Layer.

---

## Self-review

- **Spec coverage:** three-bucket policy → Tasks 2/3; anti-invention guard → Tasks 2/3; structured marker handoff → Tasks 1/4; no-leak to guests → Tasks 4/5; phrase fallback retained → Task 4; rich+compact parity → Tasks 2/3; Playtest acceptance → Task 7. Deferred items (DB reason column, pending-path flagging, semantic KB retrieval) explicitly noted, consistent with spec non-goals.
- **Placeholders:** none — every code/step is concrete.
- **Type consistency:** `parse_escalation(text) -> (clean_text, reason)` defined in Task 1 and used identically in Tasks 4 and 5; `_apply_escalation(conversation, reason)` defined and called once in Task 4.
