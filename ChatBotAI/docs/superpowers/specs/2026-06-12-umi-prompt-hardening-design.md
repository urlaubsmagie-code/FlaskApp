# UMI Prompt Hardening — Design Spec

**Date:** 2026-06-12
**Status:** Awaiting user review
**Goal milestone:** Make UMI safe enough to *trust with auto-respond* — answer routine documented questions on its own, reliably hand everything else to a human.

---

## Problem

During Playtest, UMI invented nearby restaurants/places that don't exist. Investigation found the real issue is broader than one bad answer:

1. **Wrong-model assumption corrected.** Live model is `gpt-oss:120b-cloud` (set in `AISettings.ollama_model`, applied at `app.py:538`) → routes to the **rich** prompt (`prompts/rich/guest_reply.txt`). An earlier fix to the *compact* prompt targeted a path not in use.
2. **Silent escalation dead-ends.** Escalation only fires when the reply literally contains `kollegen`/`kollegin`/`colleague` (`MessageRouter._is_escalation_response`). The rich prompt tells the model to say "Team"/"melde mich zurück" — which does *not* match — so the model says "I'll get back to you" and **no human is ever notified**, auto-respond stays on. International guests (Spanish/Italian) can never trigger it.
3. **No grounding.** `knowledge_entry` table is empty, and the property address is never even injected into the prompt (`_build_guest_reply_prompt`, ai_service.py:780, doesn't take `property_info`). So the model has nothing to stand on and fills gaps by invention.
4. **Helpful-by-default invention.** A smart model reasons "most apartments have X, so yes" — fabricating property facts.

## Goal & non-goals

**Goal:** Prompt-level hardening + a reliable handoff signal, targeting the live rich path. Trust the (capable) model to self-police, with escalation as the backstop.

**Non-goals (deferred to "Real Safety Layer," decided after a live chat test):**
- Code-level grounding gate that blocks an unbacked answer from auto-sending.
- Deterministic high-stakes topic classifier in code.
- KB population (separate content task — see Dependency).
- Multilingual escalation *phrase* list (superseded by the structured marker below).

## Dependency (must be said out loud)

"Trusted auto-respond" is only as useful as the knowledge base is full. With the KB empty, UMI will correctly **escalate almost every factual question**. That is safe but not yet time-saving. UMI becomes a time-saver exactly as fast as the KB is populated (WiFi, check-in/out, parking, amenities, house rules, prices, nearby basics, per property). The prompt hardening is the engine; the KB is the fuel.

---

## Behavior model (the core of the prompt)

UMI sorts every guest message into one of three buckets.

### ① Answer on its own — no human needed
- **General truth / logic / common sense**, true regardless of which property: "is water wet?", "is Germany in the EU?", "is summer warmer than winter?".
- **Social chat**: greetings, thanks, "we're excited".
- **Documented facts**: the specific answer is present in the knowledge base / reservation / guest profile — including documented prices, fees, check-in/out, parking, amenities, house rules. *If it's written down, UMI says it.*

### ② Escalate — property/booking/area-specific question with NO matching DB entry
The host is the only source of truth. Examples: "are the beds blue?", "do you have a hairdryer?", "how far is the train station?". UMI **never guesses, never affirms, never reasons "most places have X."**

### ③ Escalate — always, regardless of DB (judgment / relationship / urgency)
- **Complaints / reclamations** — apartment problems, dissatisfaction, damage claims.
- **Disputes / arguments.**
- **Money problems / requests** — refunds, discounts, "too expensive", cancellations, payment disputes. *Even if a cancellation policy is documented*, a refund/cancellation **request** goes to a human; UMI does not negotiate or quote-then-proceed.
- **Safety / emergencies** — gas leak, lockout, medical, urgent situations. Always, urgently.

### Hard anti-invention guard (explicit prompt text)
> Never answer a question about our property, booking, prices, or area by reasoning from what is "usual" or "typical." "Most apartments have X" is not knowledge about ours. If you don't have the specific fact, escalate — do not reason your way to "probably yes."

### Boundary reference table

| Guest asks | Bucket | UMI |
|---|---|---|
| "Is the tap water safe to drink?" | ① general | Answers |
| "Is Sebnitz in Germany?" | ① general | Answers |
| "What's the WiFi password?" (in DB) | ① documented | Answers |
| "How much is an extra night?" (in DB) | ① documented | Answers |
| "Are the beds blue?" (not in DB) | ② | Escalate |
| "Do you have a hairdryer?" (not in DB) | ② | Escalate |
| "How far is the station?" (not in DB) | ② | Escalate |
| "Can I get a refund?" (even if policy in DB) | ③ money/reclamation | Escalate |
| "The apartment is dirty." | ③ complaint | Escalate |
| "I'm locked out at midnight!" | ③ safety | Escalate (urgent) |

---

## Mechanism: reliable handoff via a structured marker

Decouple **what the guest sees** from **the machine trigger**.

- When UMI decides to escalate, it:
  1. Writes a short, natural holding message to the guest *in the guest's language* (e.g. "Das kläre ich kurz mit dem Team und melde mich gleich bei dir.").
  2. Emits a hidden marker on the final line: `[[ESCALATE: <reason>]]` where `<reason>` is one of `ungrounded | complaint | dispute | money | safety | approval`.
- Code (in the response-cleaning step, before the approval-vs-send branch):
  1. Detects the `[[ESCALATE: ...]]` marker (language-independent, unambiguous).
  2. **Strips it** so the guest never sees it.
  3. Fires the existing escalation flow: set `conversation.escalated`, `escalated_at`, pause `auto_respond`, push-notify the team. Persist the reason for triage.
- **Back-compat:** keep the existing `kollegen/kollegin/colleague` phrase detection as a fallback so nothing regresses if the marker is ever missing.

This fixes silent dead-ends and makes escalation language-independent without a brittle phrase list.

---

## Scope of changes

**Prompts**
- `prompts/rich/guest_reply.txt` — rewrite the knowledge-boundary section to the three-bucket model above, add the anti-invention guard, and define the `[[ESCALATE: reason]]` contract. (Primary — live path.)
- `prompts/compact/guest_reply.txt` — keep in parity (same rules, terser) so a future local-model swap doesn't regress. Supersedes the interim compact edit already made this session.

**Code (light plumbing)**
- `services/ai_service.py` — in `_clean_ai_response` (or adjacent), detect + strip the marker and surface an `escalate`/`reason` signal to the router.
- `services/message_router.py` — act on the marker signal to drive the existing escalation flow; keep phrase-based detection as fallback; ensure the marker is stripped on **all** paths (pending-draft and auto-send) so it never leaks to a guest.

**Tests**
- Prompt render tests: rich + compact contain the three-bucket rules, the anti-invention guard, and the marker contract.
- Marker plumbing unit tests: a reply containing `[[ESCALATE: money]]` → marker stripped from stored/sent text, `escalated` set, reason persisted; a reply without a marker → unchanged; phrase fallback still works.
- Behavioral smoke (real `gpt-oss:120b-cloud`, manual/optional): bucket ① answers; ②/③ escalate with a clean holding message + marker; controls (greeting, KB-backed WiFi) don't over-escalate.

## Verification

Primary acceptance is the **Playtest chat**: documented question → answered; undocumented property question, complaint, refund, or emergency → clean holding message to the guest *and* the conversation shows as escalated with auto-respond paused. The marker must never appear in guest-visible text.

## Risks / limitations

- Relies on the model's judgment (no code guarantee yet — that's the deferred Real Safety Layer).
- With an empty KB, escalation rate will be high until the KB is filled (expected, safe).
- Non-determinism: the model may occasionally misclassify; the marker + fallback limit the blast radius but don't eliminate it. The live chat test will tell us whether prompt-only is "good enough" or whether we proceed to the Real Safety Layer.
