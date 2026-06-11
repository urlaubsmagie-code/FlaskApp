# Tiered Prompts — Design Spec

**Date:** 2026-05-06
**Status:** Approved (pending user spec review)
**Phase 1 scope:** Guest reply prompt only (compact + rich tiers)

## 1. Problem & Motivation

ChatBotAI's main guest-reply prompt (`_build_compact_prompt` in `services/ai_service.py`) is intentionally squeezed to ~400–600 tokens because it must run on small local models (`gemma2:9b`, `qwen3:8b`). The user has upgraded to an Ollama Pro account and wants to use cloud models (`gpt-oss:120b-cloud`, etc.) which bring:

- 128K-token context windows (vs. ~8K on local models)
- Stronger instruction-following (handle long, structured prompts with examples)
- Better German fluency

The compact prompt cannot exploit any of these capabilities. Rewriting it for the 120B model would degrade quality on local models. Solution: keep tier-specific prompt variants, auto-selected at request time based on the active model.

## 2. Goals

- Two prompt tiers (`compact`, `rich`) co-exist; the right one is chosen automatically at runtime.
- Rich tier encodes the user's operational rules with precision instead of compressing them.
- Adding a third tier later (or a third prompt — e.g., for memory extraction) is a small extension, not a redesign.
- Zero behavior change in production when the main model stays at `gemma2:9b`.

## 3. Non-Goals (Phase 1)

- Reasoning prompts (memory extraction, conversation summary, knowledge extraction, corrections) stay on their current code paths. They get the same treatment in Phase 2.
- The "lightbulb" full-prompt path (`target_message_override` set) and the closing-message minimal prompt stay inline as Python strings.
- No UI for switching tiers manually. Detection is automatic.
- No automated eval harness. Phase 1 verification is by eyeballing real conversations.

## 4. Architecture

### 4.1 File layout

```
ChatBotAI/prompts/
├── shared/
│   ├── core_identity.txt        # UMI bio, role, never-invent rule
│   ├── language_rule.txt        # Language detection + German quality
│   └── tone/
│       ├── friendly_professional.txt
│       ├── friendly_casual.txt
│       └── … (one file per existing tone)
├── compact/
│   └── guest_reply.txt          # Phase 1: refactor of today's _build_compact_prompt
└── rich/
    └── guest_reply.txt          # Phase 1: new file, ~2,000–3,000 tokens
```

Every prompt file is a Jinja2 template. Shared blocks are pulled in via `{% include 'shared/…' %}`.

### 4.2 Templating engine

**Jinja2** (already a Flask dependency). Standalone `Environment` (not Flask's app-bound env) so prompts work in background sync threads as well as HTTP requests.

```python
from jinja2 import Environment, FileSystemLoader

PROMPT_DIR = Path(__file__).resolve().parent.parent / 'prompts'

env = Environment(
    loader=FileSystemLoader(str(PROMPT_DIR)),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=False,
    auto_reload=Config.PROMPT_DEV_AUTO_RELOAD,  # True in dev, False in prod
)
```

Compiled templates are cached in memory by Jinja2. First render parses the file; subsequent renders use cached bytecode. No per-request file I/O on hot paths.

### 4.3 Tier detection

`services/prompt_tier.py`:

```python
RICH_SIZE_THRESHOLD_B = 70

def detect_tier(model_name: str) -> str:
    """Returns 'rich' for big or cloud models, 'compact' otherwise."""
    if not model_name:
        return 'compact'
    name = model_name.lower()
    if name.endswith('-cloud'):
        return 'rich'
    match = re.search(r':(\d+)b', name)
    if match and int(match.group(1)) >= RICH_SIZE_THRESHOLD_B:
        return 'rich'
    return 'compact'
```

Examples:
- `gemma2:9b` → `compact`
- `qwen3:14b` → `compact`
- `gpt-oss:120b-cloud` → `rich` (cloud suffix wins)
- `kimi-k2:1t-cloud` → `rich`
- Unknown / empty → `compact` (safe default)

Override hook: an env var `FORCE_PROMPT_TIER=compact|rich`, when set, bypasses detection. Used only for debugging; not documented in user-facing settings.

The detected tier is logged at INFO level once per request:
`Prompt tier: rich (model=gpt-oss:120b-cloud)`

### 4.4 Prompt loader

`services/prompt_loader.py`:

```python
def load_prompt(name: str, tier: str, **context) -> str:
    template = env.get_template(f'{tier}/{name}.txt')
    return template.render(**context)
```

### 4.5 Integration in `ai_service.py`

- `_build_compact_prompt()` is replaced by `_build_guest_reply_prompt()`. Same signature, same return type.
- The new method:
  1. Calls `detect_tier(self.model)`.
  2. Builds the context dict (same variables as today, plus `guest_profile`, `conversation_summary`, `corrections`, `resolved_topics`, `property_info` for use in the rich template — the compact template ignores extras).
  3. Calls `load_prompt('guest_reply', tier=tier, **context)`.
  4. Returns the rendered string.
- All four current callers of `_build_compact_prompt` swap to the new method.

### 4.6 Configuration

Add to `config.py`:

```python
PROMPT_DEV_AUTO_RELOAD = os.environ.get('PROMPT_DEV_AUTO_RELOAD', 'false').lower() == 'true'
```

`DevelopmentConfig` overrides this to `True`. Production stays `False` for performance.

## 5. Compact tier — Phase 1 behavior

The compact prompt's rendered output must be **byte-equivalent** to today's `_build_compact_prompt` for the same inputs. This is a refactor, not a behavior change. Verified by snapshot diff during implementation.

## 6. Rich tier — content & rules

The rich prompt has the **same information shape** as compact (identity, rules, tone, guest, reservation, host instructions, KB, history, task) but every instruction is rewritten for precision, with no open-ended phrasing. Plus rules from the workshop with the user.

### 6.1 Tone — "Real friendly hoster, not robotic"

**Avoid (explicit anti-patterns):**

- Overly formal openings (*"Vielen Dank für Ihre Nachricht, sehr geehrter…"*)
- Reflexive apologies when nothing has gone wrong
- Mirroring the question back (*"Sie fragen, wann der Check-in ist. Der Check-in ist…"*)
- Customer-service list templates (*"Zur Beantwortung… 1)… 2)… 3)…"*)
- Corporate boilerplate closers (*"Bei weiteren Fragen stehen wir Ihnen jederzeit zur Verfügung"*) on every reply
- Repeating the guest's name unnaturally throughout the message

**Encourage:**

- Match the guest's register (length, formality, mood)
- Lead with the answer; context comes after if needed
- Casual transitional phrases used naturally, not as templates
- One-line replies for one-line questions
- Small warmth (*"Schön zu hören!"*) and small empathy (*"Oh, das ist ärgerlich"*) where natural

### 6.2 Du always

UMI uses **du** with all guests, regardless of whether the guest writes du or Sie. Vacation rental brand voice — Urlaubsmagie has chosen casual address as a brand decision. The "match the guest's register" guidance in §6.1 applies to length, formality of *vocabulary*, and mood — but not to the du/Sie axis, which is fixed.

### 6.3 Greeting

Greet once at the top of the first reply in a conversation. Do **not** greet again on subsequent replies. **Exception:** if the guest sends a fresh greeting (*"Hallo nochmal!"*, *"Guten Morgen!"*), UMI greets back. Mirror the guest.

### 6.4 Length matching

Reply length should roughly match guest message length. A one-line guest question gets a one-line answer. Don't pad short answers with greeting + answer + closer.

### 6.5 Emojis

Allowed and encouraged for warmth — 1–2 per reply when natural. Don't spam. Don't refuse to use emojis just because the guest didn't.

### 6.6 No specific timeframes

Don't promise specific response windows ("we'll respond within the hour"). Vague reassurance is fine ("wir melden uns kurz", "shortly").

### 6.7 Knowledge boundary — KB as sacred bible (tiered)

Knowledge sources are tiered:

- **Property / operational facts** (check-in/check-out times, wifi, prices, addresses, distances *to/from the apartment*, amenities, house rules) → answer **only** from the Wissensdatenbank. Never invent. If the fact isn't in the KB, tell the guest you'll forward the question to a superior.
- **Local-area / time-sensitive information** (restaurant recommendations, current shop hours, neighborhood facts, current weather, news, events) → escalate to the team. The team knows the neighborhood; UMI does not have internet access and does not know current state.
- **Static general knowledge** (time zones, climate norms, basic geography, common cultural facts UMI was trained on) → answer if confident. Hedge or escalate if unsure.
- **Time-sensitive non-property info** → escalate or hedge with vague reassurance.

UMI's training cutoff is early 2025; UMI has **no internet access**. UMI must not confidently state any fact that depends on current real-world state.

### 6.8 Anti-hallucination — never invent

Never invent any detail not present in the provided context (KB, guest profile, reservation info, conversation history). Specifically: never invent the guest's family composition, pets, allergies, prior stays, or preferences. The triggering incident: UMI mentioned the guest's children when no information about children was anywhere in the conversation. This is a hard rule, not a soft preference.

### 6.9 Sign-off rule

Sign-offs apply **only** at conversation close (despedida moments — guest is saying goodbye, conversation is fully resolved, no pending topics). Never mid-conversation.

When applied:

- **Mirror the team's recent style.** If the conversation log contains a prior sign-off from the team, copy that pattern (same names, same format).
- **Default if no precedent in history:** `Liebe Grüße, Elena, Imke, Anna-Lena, und Sebastian - Team Urlaubsmagie`
- **~15–20% of closing replies**, use a UMI-mentioning variant instead, picked at random from:
  - `UMI und dein Urlaubsmagie Team`
  - `UMI, Elena, Anna-Lena, Sebastian - Urlaubsmagie Team`
  - `UMI von Urlaubsmagie`

### 6.10 Goodbye phrasing — never apartment-specific

When closing a conversation, never reference a specific apartment, room, or property code. Always use general phrasing referring to Urlaubsmagie as a whole (*"bei Urlaubsmagie"*, *"in einer unserer Unterkünfte"*). Reason: reservations are confirmed days or weeks in advance, and UMI cannot guarantee the same apartment will be available on a future stay.

### 6.11 Future expansion via KB

The Digital Team adds new operational rules and edge-case knowledge by editing the **Wissensdatenbank**, not the prompt. This is the architecture's dynamic layer: prompt holds static rules and behavior; KB holds growing operational knowledge. A new situation arises → KB entry → next request behaves correctly. No code changes, no restart.

## 7. Code changes

### Files added

- `ChatBotAI/services/prompt_tier.py` — `detect_tier()`
- `ChatBotAI/services/prompt_loader.py` — Jinja2 environment + `load_prompt()`
- `ChatBotAI/prompts/shared/core_identity.txt`
- `ChatBotAI/prompts/shared/language_rule.txt`
- `ChatBotAI/prompts/shared/tone/*.txt` — one file per tone in today's `TONE_INSTRUCTIONS` dict
- `ChatBotAI/prompts/compact/guest_reply.txt` — refactor of today's `_build_compact_prompt` output
- `ChatBotAI/prompts/rich/guest_reply.txt` — new

### Files modified

- `ChatBotAI/services/ai_service.py` — replace `_build_compact_prompt` with `_build_guest_reply_prompt`; swap the four callers; remove the `TONE_INSTRUCTIONS` dict (content migrates to tone files)
- `ChatBotAI/config.py` — add `PROMPT_DEV_AUTO_RELOAD` flag

### Files unchanged in Phase 1

- The "lightbulb" full-prompt path (`target_message_override` set) — stays inline
- The closing-message minimal prompt — stays inline
- All reasoning prompts (memory extraction, summary, knowledge extraction, corrections) — Phase 2

## 8. Verification & rollout

### 8.1 Side-by-side smoke tests

A dev-only debug endpoint `/chatbot/debug/prompt-compare?conversation_id=N`:

- Renders both compact and rich `guest_reply.txt` with the same context
- Calls `gemma2:9b` with compact and `gpt-oss:120b-cloud` with rich
- Returns both rendered prompts (the actual text sent to Ollama) and both AI responses for visual comparison

### 8.2 Test scenarios

Validate in the existing **Playtest V2 sandbox** (debug → playtest launcher). Run scenarios:

1. Long thread with a clear closing → verify sign-off rule fires correctly (and the variant rate over multiple runs)
2. Guest asks something not in KB → verify escalation phrasing ("ich kläre das mit dem Team")
3. Casual du-message vs. a formal Sie-message → verify tone mirroring while keeping du as default
4. Multi-question guest message → verify all questions addressed, length matches
5. Goodbye where the legacy prompt would say "come back to W3 apartment" → verify open phrasing
6. Guest brings up children/family without prior info → verify no fabrication

Plus 5 real conversations from the live inbox (read-only — never send) run through the comparison endpoint.

### 8.3 Acceptance criteria

- [ ] All four callers of `_build_compact_prompt` switched to `_build_guest_reply_prompt`. No behavior change when running on `gemma2:9b` (compact tier renders byte-equivalent prompt to today's output, verified by diff snapshot test).
- [ ] Auto-detection picks correct tier for `gemma2:9b`, `qwen3:8b`, `qwen3:14b`, `gpt-oss:120b-cloud`, `kimi-k2:1t-cloud`. Detection result is logged once per request.
- [ ] Rich prompt encodes every rule in §6 (tone, du, greeting, length, emojis, timeframes, knowledge boundary, anti-hallucination, sign-off, goodbye phrasing).
- [ ] Side-by-side comparison endpoint works on at least 5 real conversations.
- [ ] Dev `auto_reload` confirmed: editing a `.txt` file is reflected on the next request without a Flask restart.
- [ ] All 6 Playtest V2 scenarios pass eyeball review.

### 8.4 Ship behavior

- Default config keeps `gemma2:9b` as the main model. Rich prompt **never fires in production** until the model is switched. Zero risk to existing flow.
- Switching the main model to `gpt-oss:120b-cloud` in Settings activates the rich prompt automatically via auto-detection.

### 8.5 Rollback

1. **Fast:** revert main model to `gemma2:9b` in Settings → reverts to compact prompt without code changes.
2. **Forced:** set `FORCE_PROMPT_TIER=compact` env var to keep cloud model + compact prompt for a debug session.

## 9. Phase 2 (out of scope, documented for context)

Same architecture extended to:
- Memory extraction prompt
- Conversation summary prompt
- Knowledge extraction prompt
- Corrections feedback prompt
- "Lightbulb" full-prompt path (per-message suggest)
- Closing-message minimal prompt

Each becomes a `compact/<name>.txt` + `rich/<name>.txt` pair. The detection rule, loader, and shared blocks are reused unchanged.
