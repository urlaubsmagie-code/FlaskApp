# UMI Voice Match + Latency — Design

**Date:** 2026-07-06
**Branch:** feat/notion-knowledge-sync
**Goal:** Make UMI's replies read like the human team's ("the girls") and cut the 15–30s wait.

## Problem

Team feedback, three complaints:
1. **Response time** — UMI takes 15–30s to produce a reply.
2. **Too many symbols** — messages feel over-decorated.
3. **Message feel** — inconsistent; "still looks like a bot."

## Evidence

**UMI's sent messages** (`sender_type='ai'`, 21 samples): emoji on 20/21, often literal-object (☕️ for kettle, 🔌 plug, 📺 TV); nearly every sentence ends in `!`; canned empathy openers repeated across a thread ("Oh nein, das ist ja blöd!", "Ach du liebe X!"); register swings stiff↔chummy↔gushing.

**The girls' genuine replies** (`sender_type='owner'`, non-template samples): lead with the answer; ~1 emoji, often 0; only warm/social emoji (🤗 😊 👍 ✨ 🙂 ☀️) placed at the end, never on objects; modest exclamation use; understated on bad news ("leider…", `:/`); sign off `Viele Grüße, [Name] / Euer Urlaubsmagie Team ✨` on fuller replies, nothing on one-liners; real and slightly imperfect (lowercase starts, typos).

**Root causes:**
- Latency: live model `gpt-oss:120b-cloud` is a reasoning model — hidden chain-of-thought before every reply, non-streamed.
- Symbols/feel: the prompt *invites* the behavior — `# Emojis` says "encouraged … 1 or 2", and `# Voice` literally suggests the empathy template "Oh, das ist ärgerlich". Temperature 0.5 adds voice variance.

## Changes

All in the **rich** prompt (production path — gpt-oss = rich tier) plus two dials. No new code paths, no new deps.

### 1. `prompts/rich/guest_reply.txt` — `# Emojis`
Rewrite: at most one emoji per message, often none; only warm/social ones (🤗 😊 👍 ✨ 🙂 ☀️); place at the end of a sentence or message; never decorate objects/nouns (no ☕️ 🔌 📺 🔧).

### 2. `prompts/rich/guest_reply.txt` — `# Voice and behavior`
- Lead with the answer.
- No canned emotional openers; remove the "Oh, das ist ärgerlich" template. Empathy stays understated ("das ist ärgerlich"/"leider", once, no theatrics).
- One exclamation mark per message at most; factual info uses periods.
- Keep it real: short, plain, not polished-corporate. Don't gush ("wir sind immer für euch da", "freuen uns riesig").

### 3. Temperature `0.5 → 0.35`
Steadier voice → fixes the inconsistency. `AISettings['ai_temperature']` (DB) + code fallback in `ai_service._call_chat_api`.

### 4. gpt-oss reasoning → `medium`
In `ai_service._call_chat_api`, add top-level `think` to the `/api/chat` payload **only when** `'gpt-oss' in model`. Value from `AISettings['ai_reasoning_effort']`, fallback `'medium'`. Spot-checking showed `low` (~3s) measurably disobeys instructions — answered English guests in German 2/3 times, one false escalation — while `medium` (~5s) obeys them and still beats the old 15–30s. Knob: `low` for max speed, `high` for hard cases.

### 5. `prompts/shared/language_rule.txt` — force language mirroring
Spot-check surfaced a pre-existing bug: because the whole prompt (instructions, KB, reservation) is German, the model sometimes replies to an English guest in German even at `medium`. Strengthened the rule to "ALWAYS reply in the SAME language the guest's latest message is in … overrides the German instructions/KB." Shared include → fixes rich and compact. Verified 5/5 English after.

## Non-goals (deferred)

- **Streaming** the reply into the box (real perceived-speed fix) — endpoint + JS work. Only if `think=low` isn't fast enough.
- Settings-UI toggle for reasoning effort — DB row is enough for now.
- Touching the compact prompt / tone files — production runs rich; not the complaint.

## Verification

- Render the rich prompt template → no Jinja errors.
- Existing prompt tests pass (`tests/` prompt/AI suite).
- Live spot-check: trigger UMI Vorschlag + auto-reply, confirm (a) faster, (b) ≤1 warm emoji, (c) answer-first, no `!`-stacking.

## Rollback

Revert the prompt file and the two settings; `think` gate removal is a one-line diff.
