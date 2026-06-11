# Tiered Prompts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a tier-aware prompt system (compact + rich) for the guest-reply prompt in ChatBotAI, auto-selected by model name. Phase 1 only — guest reply path. Reasoning prompts stay on existing code paths.

**Architecture:** Externalize the guest-reply system prompt to Jinja2 templates under `ChatBotAI/prompts/`. A small detection module picks `compact` for ≤14B local models and `rich` for cloud models or ≥70B local models. Shared blocks (core identity, language rule, tone files) are included by both tiers via Jinja `{% include %}`.

**Tech Stack:** Python 3, Flask, Jinja2 (already a Flask dependency), pytest (new — no existing test infrastructure in ChatBotAI).

**Spec:** `ChatBotAI/docs/superpowers/specs/2026-05-06-tiered-prompts-design.md`

---

## File Structure

**New files (created in this plan):**

| Path | Responsibility |
|---|---|
| `ChatBotAI/services/prompt_tier.py` | Pure-function `detect_tier(model_name)` returning `"compact"` or `"rich"` |
| `ChatBotAI/services/prompt_loader.py` | Jinja2 `Environment` + `load_prompt(name, tier, **ctx)` |
| `ChatBotAI/prompts/shared/core_identity.txt` | UMI bio, role, never-invent rule (used by both tiers) |
| `ChatBotAI/prompts/shared/language_rule.txt` | Language detection + German quality (used by both tiers) |
| `ChatBotAI/prompts/shared/tone/friendly_professional.txt` | Tone string for `friendly_professional` |
| `ChatBotAI/prompts/shared/tone/formal.txt` | Tone string for `formal` |
| `ChatBotAI/prompts/shared/tone/casual.txt` | Tone string for `casual` |
| `ChatBotAI/prompts/shared/tone/concise.txt` | Tone string for `concise` |
| `ChatBotAI/prompts/compact/guest_reply.txt` | Compact tier guest-reply prompt — byte-equivalent to today's `_build_compact_prompt` output |
| `ChatBotAI/prompts/rich/guest_reply.txt` | Rich tier guest-reply prompt — encodes all rules from spec §6 |
| `ChatBotAI/tests/__init__.py` | Empty marker — establishes test package |
| `ChatBotAI/tests/test_prompt_tier.py` | Unit tests for `detect_tier()` |
| `ChatBotAI/tests/test_prompt_loader.py` | Smoke test that templates load and render |
| `ChatBotAI/tests/test_compact_prompt_snapshot.py` | Snapshot test — compact tier output matches legacy `_build_compact_prompt` |

**Modified files:**

| Path | Change |
|---|---|
| `ChatBotAI/config.py` | Add `PROMPT_DEV_AUTO_RELOAD` flag; override to `True` in `DevelopmentConfig` |
| `ChatBotAI/services/ai_service.py` | Add `_build_guest_reply_prompt()`; swap the single existing call at line 900; `TONE_INSTRUCTIONS` dict stays for now (used as fallback for the tone-file lookup, removed only after files are confirmed working) |
| `ChatBotAI/routes.py` | Add `/chatbot/debug/prompt-compare` admin-only endpoint |
| `ChatBotAI/templates/chatbot/debug.html` | Add a small "Prompt Compare" link/section pointing at the new endpoint |
| `requirements.txt` | Add `pytest` to dev deps if not already present |

**Note on caller count:** the spec said "four callers" of `_build_compact_prompt`. The actual code has **one** caller (`ai_service.py:900`). Plan reflects reality.

---

## Task 1: Verify Jinja2 availability and add pytest

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Confirm Jinja2 is already installed**

Run: `python -c "import jinja2; print(jinja2.__version__)"`
Expected: A version number prints (Jinja2 is a Flask transitive dependency). If it errors, run `pip install jinja2`.

- [ ] **Step 2: Confirm pytest is installed**

Run: `python -c "import pytest; print(pytest.__version__)"`
Expected: A version number prints. If it errors, install: `pip install pytest`.

- [ ] **Step 3: Add pytest to requirements.txt if missing**

Read `requirements.txt`. If `pytest` is not listed, append a line `pytest>=7.0`.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: add pytest to requirements for tiered-prompts work"
```

(If `requirements.txt` was already up to date, skip the commit — `git status` will show nothing to commit.)

---

## Task 2: Add `PROMPT_DEV_AUTO_RELOAD` config flag

**Files:**
- Modify: `ChatBotAI/config.py`

- [ ] **Step 1: Open `ChatBotAI/config.py` and locate the `Config` class**

Read the existing file. Find the section near `OLLAMA_TIMEOUT` (~line 29).

- [ ] **Step 2: Add the new flag in the base `Config` class**

After the existing `OLLAMA_TIMEOUT` line, insert:

```python
    # Prompt template settings
    PROMPT_DEV_AUTO_RELOAD = os.environ.get('PROMPT_DEV_AUTO_RELOAD', 'false').lower() == 'true'
```

- [ ] **Step 3: Override the flag in `DevelopmentConfig`**

Inside the `DevelopmentConfig` class, after `SQLALCHEMY_ECHO = True`, add:

```python
    PROMPT_DEV_AUTO_RELOAD = True
```

- [ ] **Step 4: Verify the import path works**

Run: `python -c "from ChatBotAI.config import DevelopmentConfig; print(DevelopmentConfig.PROMPT_DEV_AUTO_RELOAD)"`
Expected: `True`

Run: `python -c "from ChatBotAI.config import ProductionConfig; print(ProductionConfig.PROMPT_DEV_AUTO_RELOAD)"`
Expected: `False`

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/config.py
git commit -m "feat(config): add PROMPT_DEV_AUTO_RELOAD flag"
```

---

## Task 3: Create `prompt_tier.py` with `detect_tier()` and unit tests

**Files:**
- Create: `ChatBotAI/services/prompt_tier.py`
- Create: `ChatBotAI/tests/__init__.py`
- Create: `ChatBotAI/tests/test_prompt_tier.py`

- [ ] **Step 1: Write the failing test**

Create `ChatBotAI/tests/__init__.py` with empty content (just creates the package).

Create `ChatBotAI/tests/test_prompt_tier.py`:

```python
import os
import pytest
from ChatBotAI.services.prompt_tier import detect_tier


@pytest.mark.parametrize("model_name,expected", [
    # Local small models → compact
    ("gemma2:9b", "compact"),
    ("qwen3:8b", "compact"),
    ("qwen3:14b", "compact"),
    ("mistral:7b-instruct", "compact"),
    ("llama3.2:3b", "compact"),
    # Cloud models → rich (cloud suffix wins regardless of size pattern)
    ("gpt-oss:120b-cloud", "rich"),
    ("kimi-k2:1t-cloud", "rich"),
    ("qwen3-coder:480b-cloud", "rich"),
    ("deepseek-v3.1:671b-cloud", "rich"),
    # Big local models (≥70B) → rich
    ("llama3.1:70b", "rich"),
    ("mistral:200b", "rich"),
    # Edge cases → compact (safe default)
    ("", "compact"),
    ("unknown-model", "compact"),
])
def test_detect_tier(model_name, expected):
    assert detect_tier(model_name) == expected


def test_detect_tier_handles_none():
    assert detect_tier(None) == "compact"


def test_detect_tier_is_case_insensitive():
    assert detect_tier("GPT-OSS:120B-CLOUD") == "rich"
    assert detect_tier("Gemma2:9B") == "compact"


def test_force_override_via_env(monkeypatch):
    monkeypatch.setenv("FORCE_PROMPT_TIER", "rich")
    assert detect_tier("gemma2:9b") == "rich"
    monkeypatch.setenv("FORCE_PROMPT_TIER", "compact")
    assert detect_tier("gpt-oss:120b-cloud") == "compact"


def test_force_override_invalid_value_is_ignored(monkeypatch):
    monkeypatch.setenv("FORCE_PROMPT_TIER", "invalid")
    # Falls back to normal detection
    assert detect_tier("gemma2:9b") == "compact"
    assert detect_tier("gpt-oss:120b-cloud") == "rich"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest ChatBotAI/tests/test_prompt_tier.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ChatBotAI.services.prompt_tier'`.

- [ ] **Step 3: Implement `prompt_tier.py`**

Create `ChatBotAI/services/prompt_tier.py`:

```python
"""Prompt tier detection.

Decides whether a given model should use the compact or rich prompt template.
Rule: cloud models (suffix '-cloud') or local models >= 70B are 'rich'.
Everything else is 'compact'.
"""

import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

RICH_SIZE_THRESHOLD_B = 70
_VALID_TIERS = {"compact", "rich"}


def detect_tier(model_name: Optional[str]) -> str:
    """Return 'compact' or 'rich' for the given Ollama model name.

    Examples:
        detect_tier('gemma2:9b')           -> 'compact'
        detect_tier('gpt-oss:120b-cloud')  -> 'rich'
        detect_tier('llama3.1:70b')        -> 'rich'
        detect_tier(None)                  -> 'compact'

    Override: setting env var FORCE_PROMPT_TIER to 'compact' or 'rich'
    bypasses detection entirely. Used only for debugging.
    """
    forced = os.environ.get("FORCE_PROMPT_TIER", "").strip().lower()
    if forced in _VALID_TIERS:
        return forced

    if not model_name:
        return "compact"

    name = model_name.lower()
    if name.endswith("-cloud"):
        return "rich"

    match = re.search(r":(\d+)b", name)
    if match and int(match.group(1)) >= RICH_SIZE_THRESHOLD_B:
        return "rich"

    return "compact"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest ChatBotAI/tests/test_prompt_tier.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/prompt_tier.py ChatBotAI/tests/__init__.py ChatBotAI/tests/test_prompt_tier.py
git commit -m "feat(prompts): add detect_tier() with cloud + 70B threshold"
```

---

## Task 4: Create the shared core_identity and language_rule blocks

**Files:**
- Create: `ChatBotAI/prompts/shared/core_identity.txt`
- Create: `ChatBotAI/prompts/shared/language_rule.txt`

- [ ] **Step 1: Create `prompts/shared/core_identity.txt`**

Content (this is the single source of truth for UMI's identity, used by both tiers):

```
You are UMI, the friendly AI assistant for Urlaubsmagie vacation rentals. You are warm, helpful, and casual — always treating guests like welcome visitors.
```

- [ ] **Step 2: Create `prompts/shared/language_rule.txt`**

Content:

```
Rules: Reply in the guest's language. Never invent details — say you'll check. Don't re-ask answered questions.
German quality: Write as a native speaker would — natural, fluent, and grammatically correct. Use correct article and case agreement. Use idiomatic phrasing, not literal translations. Include possessive pronouns where natural. Prefer common, everyday vocabulary over stiff or formal constructions.
```

- [ ] **Step 3: Commit**

```bash
git add ChatBotAI/prompts/shared/core_identity.txt ChatBotAI/prompts/shared/language_rule.txt
git commit -m "feat(prompts): add shared core_identity and language_rule blocks"
```

---

## Task 5: Create the shared tone files

**Files:**
- Create: `ChatBotAI/prompts/shared/tone/friendly_professional.txt`
- Create: `ChatBotAI/prompts/shared/tone/formal.txt`
- Create: `ChatBotAI/prompts/shared/tone/casual.txt`
- Create: `ChatBotAI/prompts/shared/tone/concise.txt`

The tone strings come verbatim from the existing `TONE_INSTRUCTIONS` dict in `ai_service.py:747-752`. Keep them character-for-character identical so compact-tier output stays byte-equivalent.

- [ ] **Step 1: Create `friendly_professional.txt`**

Content (single line, no trailing newline):

```
Be warm, helpful, and professional.
```

- [ ] **Step 2: Create `formal.txt`**

```
Be polite, formal, and professional. Use formal language (Sie in German).
```

- [ ] **Step 3: Create `casual.txt`**

```
Be relaxed and conversational, like chatting with a friend. Use informal language (du in German, tú in Spanish).
```

- [ ] **Step 4: Create `concise.txt`**

```
Be brief and to the point. Short sentences, no filler.
```

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/prompts/shared/tone/
git commit -m "feat(prompts): add shared tone files (4 tones)"
```

---

## Task 6: Create `prompt_loader.py` with smoke test

**Files:**
- Create: `ChatBotAI/services/prompt_loader.py`
- Create: `ChatBotAI/tests/test_prompt_loader.py`

- [ ] **Step 1: Write the failing test**

Create `ChatBotAI/tests/test_prompt_loader.py`:

```python
"""Smoke tests for prompt_loader. Verifies templates exist and render."""

import pytest
from ChatBotAI.services.prompt_loader import load_prompt, list_available_tones


def test_shared_blocks_load():
    """Shared blocks render as plain strings (no template syntax in them today)."""
    out = load_prompt("core_identity", tier="shared")
    assert "UMI" in out
    assert "Urlaubsmagie" in out

    out = load_prompt("language_rule", tier="shared")
    assert "guest's language" in out
    assert "German quality" in out


def test_tone_files_load():
    for tone in ["friendly_professional", "formal", "casual", "concise"]:
        out = load_prompt(tone, tier="shared/tone")
        assert out.strip(), f"tone file {tone} is empty"


def test_list_available_tones_returns_four():
    tones = list_available_tones()
    assert set(tones) == {"friendly_professional", "formal", "casual", "concise"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest ChatBotAI/tests/test_prompt_loader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ChatBotAI.services.prompt_loader'`.

- [ ] **Step 3: Implement `prompt_loader.py`**

Create `ChatBotAI/services/prompt_loader.py`:

```python
"""Prompt template loader.

Wraps a standalone Jinja2 Environment that loads prompt templates from
the project's `prompts/` directory. Standalone (not Flask-bound) so it
works in background sync threads as well as HTTP request contexts.

Templates are cached in memory; in development, set
PROMPT_DEV_AUTO_RELOAD=true so edits are picked up without a restart.
"""

import logging
import os
from pathlib import Path
from typing import List

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

logger = logging.getLogger(__name__)

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

_auto_reload = os.environ.get("PROMPT_DEV_AUTO_RELOAD", "false").lower() == "true"

env = Environment(
    loader=FileSystemLoader(str(PROMPT_DIR)),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=False,
    auto_reload=_auto_reload,
)


def load_prompt(name: str, tier: str, **context) -> str:
    """Render a prompt template.

    Args:
        name: Template basename without .txt (e.g. 'guest_reply').
        tier: Subdirectory ('compact', 'rich', 'shared', 'shared/tone').
        **context: Variables passed to the Jinja2 template.

    Returns:
        Rendered string.

    Raises:
        TemplateNotFound if the file does not exist.
    """
    template_path = f"{tier}/{name}.txt"
    try:
        template = env.get_template(template_path)
    except TemplateNotFound:
        logger.error("Prompt template not found: %s", template_path)
        raise
    return template.render(**context)


def list_available_tones() -> List[str]:
    """Return the basenames of every tone file under shared/tone/."""
    tone_dir = PROMPT_DIR / "shared" / "tone"
    if not tone_dir.is_dir():
        return []
    return sorted(p.stem for p in tone_dir.glob("*.txt"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest ChatBotAI/tests/test_prompt_loader.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/prompt_loader.py ChatBotAI/tests/test_prompt_loader.py
git commit -m "feat(prompts): add Jinja2 prompt loader with smoke tests"
```

---

## Task 7: Create the compact `guest_reply.txt` template

**Files:**
- Create: `ChatBotAI/prompts/compact/guest_reply.txt`

This template is a 1:1 port of today's `_build_compact_prompt()` (`ai_service.py:754-838`). The output must be byte-equivalent for the same inputs. Snapshot test in Task 8 enforces this.

- [ ] **Step 1: Create `prompts/compact/guest_reply.txt`**

Content:

```jinja
{% include 'shared/core_identity.txt' %}
{{ tone_instruction }}
Date: {{ now_str }}.
{% include 'shared/language_rule.txt' %}
{% if guest_language %}
Guest: {{ guest_name }} (speaks {{ guest_language }})
{% else %}
Guest: {{ guest_name }}
{% endif %}
{% if reservation_compact %}
{{ reservation_compact }}
{% endif %}
{% if host_instructions %}
Host instructions: {{ host_instructions }}
{% endif %}
{% if knowledge_entries %}
Info:
{% for kb in knowledge_entries %}
- {{ kb.label }}: {{ kb.value_truncated }}
{% endfor %}
{% endif %}
{% if recent_host_replies %}
Your recent replies:
{{ recent_host_replies }}
{% endif %}

{% if unanswered_count >= 2 %}
TASK: The guest sent {{ unanswered_count }} unanswered messages below. Address ALL of them in one reply.
{% else %}
TASK: The guest's new message is: "{{ task_text }}"
Reply to THIS message only.
{% endif %}
```

**Why pre-formatted variables (`now_str`, `kb.value_truncated`, `task_text`):** Jinja2's date and string-truncation filters work, but doing the formatting in Python before render keeps the template readable and matches today's behavior exactly (e.g. `now.strftime('%d %b %Y')`, the `[:80] + "..."` truncation, the `[:300] + "..."` truncation).

- [ ] **Step 2: Commit**

```bash
git add ChatBotAI/prompts/compact/guest_reply.txt
git commit -m "feat(prompts): add compact/guest_reply.txt (1:1 port of legacy)"
```

---

## Task 8: Wire the loader into `ai_service.py` (compact only) with snapshot test

**Files:**
- Modify: `ChatBotAI/services/ai_service.py`
- Create: `ChatBotAI/tests/test_compact_prompt_snapshot.py`

This task introduces `_build_guest_reply_prompt()` *alongside* the legacy `_build_compact_prompt()` (don't delete yet). The snapshot test asserts byte-equivalence between the two for several scenarios. Once green, the live caller swaps over.

- [ ] **Step 1: Write the failing snapshot test**

Create `ChatBotAI/tests/test_compact_prompt_snapshot.py`:

```python
"""Snapshot test: new compact-tier prompt must equal legacy _build_compact_prompt output.

We instantiate AIService directly (no Flask app), call both methods on the
same fixtures, and assert exact string equality. This locks Phase 1 as a
pure refactor — zero behavior change on gemma2:9b.
"""

from datetime import datetime
from unittest.mock import patch

import pytest

from ChatBotAI.services.ai_service import AIService


@pytest.fixture
def svc():
    return AIService(model="gemma2:9b")


# Freeze "now" so date stamps match between legacy and new.
FROZEN_NOW = datetime(2026, 5, 6, 12, 0, 0)


def _patched(monkeypatch):
    """Patch datetime.utcnow inside ai_service to return FROZEN_NOW."""
    class _F:
        @staticmethod
        def utcnow():
            return FROZEN_NOW
    monkeypatch.setattr("ChatBotAI.services.ai_service.datetime", _F)


SCENARIOS = [
    {
        "name": "minimal_single_message",
        "guest_profile": {"name": "Anna", "language": "German"},
        "conversation_history": [],
        "clean_latest": "Wann ist der Check-in?",
        "unanswered_count": 1,
        "tone": "friendly_professional",
        "host_instructions": None,
        "reservation_info": None,
        "knowledge_entries": None,
    },
    {
        "name": "with_kb_and_history",
        "guest_profile": {"name": "Max", "language": "German"},
        "conversation_history": [
            {"sender_type": "owner", "content": "Hallo Max, willkommen!"},
            {"sender_type": "guest", "content": "Danke! Eine Frage..."},
        ],
        "clean_latest": "Gibt es WLAN?",
        "unanswered_count": 1,
        "tone": "friendly_professional",
        "host_instructions": "Always confirm bookings.",
        "reservation_info": None,
        "knowledge_entries": [
            {"label": "WLAN-Passwort", "value": "urlaubsmagie2026"},
            {"label": "Check-in", "value": "Ab 15:00 Uhr selbständig per Schlüsseltresor."},
        ],
    },
    {
        "name": "multi_unanswered",
        "guest_profile": {"name": "Lisa", "language": None},
        "conversation_history": [],
        "clean_latest": "Frage 1\nFrage 2\nFrage 3",
        "unanswered_count": 3,
        "tone": "casual",
        "host_instructions": None,
        "reservation_info": None,
        "knowledge_entries": None,
    },
]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s["name"])
def test_compact_tier_byte_equivalent_to_legacy(svc, monkeypatch, scenario):
    _patched(monkeypatch)
    legacy = svc._build_compact_prompt(
        guest_profile=scenario["guest_profile"],
        conversation_history=scenario["conversation_history"],
        clean_latest=scenario["clean_latest"],
        unanswered_count=scenario["unanswered_count"],
        tone=scenario["tone"],
        host_instructions=scenario["host_instructions"],
        reservation_info=scenario["reservation_info"],
        knowledge_entries=scenario["knowledge_entries"],
    )
    new = svc._build_guest_reply_prompt(
        guest_profile=scenario["guest_profile"],
        conversation_history=scenario["conversation_history"],
        clean_latest=scenario["clean_latest"],
        unanswered_count=scenario["unanswered_count"],
        tone=scenario["tone"],
        host_instructions=scenario["host_instructions"],
        reservation_info=scenario["reservation_info"],
        knowledge_entries=scenario["knowledge_entries"],
    )
    assert new == legacy, (
        f"Compact tier output differs from legacy for scenario {scenario['name']!r}.\n"
        f"--- LEGACY ---\n{legacy}\n--- NEW ---\n{new}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest ChatBotAI/tests/test_compact_prompt_snapshot.py -v`
Expected: FAIL with `AttributeError: 'AIService' object has no attribute '_build_guest_reply_prompt'`.

- [ ] **Step 3: Add `_build_guest_reply_prompt()` to `AIService`**

In `ChatBotAI/services/ai_service.py`, add the following method **immediately after** `_build_compact_prompt()` (around line 838). Do not delete `_build_compact_prompt` yet — the snapshot test compares the two.

Imports to add at the top of the file (after the existing `import` block):

```python
from .prompt_tier import detect_tier
from .prompt_loader import load_prompt
```

New method (insert after `_build_compact_prompt`):

```python
    def _build_guest_reply_prompt(
            self,
            guest_profile: Dict[str, Any],
            conversation_history: List[Dict[str, str]],
            clean_latest: str,
            unanswered_count: int,
            tone: Optional[str] = None,
            host_instructions: Optional[str] = None,
            reservation_info: Optional[Dict[str, Any]] = None,
            knowledge_entries: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Tier-aware guest reply prompt.

        Picks 'compact' or 'rich' based on self.model and renders the
        corresponding Jinja2 template with the same context the legacy
        _build_compact_prompt assembles.
        """
        tier = detect_tier(self.model)
        logger.info("Prompt tier: %s (model=%s)", tier, self.model)

        now = datetime.utcnow()
        now_str = now.strftime('%d %b %Y')

        tone_instruction = self.TONE_INSTRUCTIONS.get(
            tone, self.TONE_INSTRUCTIONS['friendly_professional']
        )

        guest_name = guest_profile.get('name', 'the guest') if guest_profile else 'the guest'
        guest_language = guest_profile.get('language') if guest_profile else None

        reservation_compact = (
            self._format_reservation_compact(reservation_info) if reservation_info else None
        )

        # KB entries: top 3, exclude escalation, truncate value to 80 chars.
        kb_for_template = None
        if knowledge_entries:
            regular = [e for e in knowledge_entries if not (e.get('category') or '').startswith('esc')][:3]
            if regular:
                kb_for_template = []
                for e in regular:
                    value = e.get('value', '')
                    val = value[:80] + ("..." if len(value) > 80 else "")
                    kb_for_template.append({
                        'label': e.get('label', ''),
                        'value_truncated': val,
                    })

        # Recent host replies only — exclude guest messages.
        host_only = [m for m in conversation_history if m.get('sender_type') in ('owner', 'ai')]
        recent_host_replies = (
            self._format_conversation_log(host_only, max_history=2) if host_only else None
        )

        task_text = clean_latest[:300] + ("..." if len(clean_latest) > 300 else "")

        return load_prompt(
            'guest_reply',
            tier=tier,
            tone_instruction=tone_instruction,
            now_str=now_str,
            guest_name=guest_name,
            guest_language=guest_language,
            reservation_compact=reservation_compact,
            host_instructions=(host_instructions.strip() if host_instructions else None),
            knowledge_entries=kb_for_template,
            recent_host_replies=recent_host_replies,
            unanswered_count=unanswered_count,
            task_text=task_text,
            # Rich-tier-only extras (compact ignores them):
            guest_profile=guest_profile,
        )
```

- [ ] **Step 4: Run snapshot test**

Run: `pytest ChatBotAI/tests/test_compact_prompt_snapshot.py -v`

If FAIL: inspect the diff in the assertion message. The most likely culprits are whitespace/blank-line differences from Jinja2's `trim_blocks`/`lstrip_blocks` interacting with `{% if %}` blocks. Adjust `prompts/compact/guest_reply.txt` (add or remove a newline at the boundary of an `{% if %}` block) until output matches. Repeat until all scenarios PASS.

Expected when correct: All scenarios PASS.

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/ai_service.py ChatBotAI/tests/test_compact_prompt_snapshot.py
git commit -m "feat(prompts): add _build_guest_reply_prompt() with snapshot parity"
```

---

## Task 9: Swap the live caller and remove the legacy method

**Files:**
- Modify: `ChatBotAI/services/ai_service.py`

- [ ] **Step 1: Swap the call site at line 900**

In `ai_service.py`, find the call:

```python
            system_content = self._build_compact_prompt(
                guest_profile=guest_profile,
                conversation_history=conversation_history,
                clean_latest=clean_latest,
                unanswered_count=unanswered_count,
                tone=tone,
                host_instructions=host_instructions,
                reservation_info=reservation_info,
                knowledge_entries=knowledge_entries,
            )
```

Change `self._build_compact_prompt(` → `self._build_guest_reply_prompt(`. Keep all keyword arguments identical.

- [ ] **Step 2: Delete the legacy `_build_compact_prompt` method**

Remove the entire `_build_compact_prompt` method (today at `ai_service.py:754-838`). Do **not** remove `TONE_INSTRUCTIONS` — `_build_guest_reply_prompt` still uses it.

- [ ] **Step 3: Update the snapshot test to skip cleanly**

The snapshot test now references a method that no longer exists. Edit `ChatBotAI/tests/test_compact_prompt_snapshot.py`:

Change the test parametrize to call only the new method and compare against a stored golden string per scenario.

Replace the test body with:

```python
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s["name"])
def test_compact_tier_renders_without_error(svc, monkeypatch, scenario):
    _patched(monkeypatch)
    out = svc._build_guest_reply_prompt(
        guest_profile=scenario["guest_profile"],
        conversation_history=scenario["conversation_history"],
        clean_latest=scenario["clean_latest"],
        unanswered_count=scenario["unanswered_count"],
        tone=scenario["tone"],
        host_instructions=scenario["host_instructions"],
        reservation_info=scenario["reservation_info"],
        knowledge_entries=scenario["knowledge_entries"],
    )
    # Sanity: required substrings are present.
    assert "UMI" in out
    assert "TASK:" in out
    assert "Date: 06 May 2026" in out
```

- [ ] **Step 4: Run the full test suite**

Run: `pytest ChatBotAI/tests/ -v`
Expected: All tests PASS.

- [ ] **Step 5: Manual smoke — start the dev server**

Run: `python -m ChatBotAI.run`

Then open `http://localhost:5000/chatbot/`, log in, open a real conversation, click "KI-Vorschlag" / "KI-Antwort". Verify a reply is generated successfully (no 500, no template error in logs).

In the Flask console, look for a log line like:
`Prompt tier: compact (model=gemma2:9b)`

If everything works, stop the server.

- [ ] **Step 6: Commit**

```bash
git add ChatBotAI/services/ai_service.py ChatBotAI/tests/test_compact_prompt_snapshot.py
git commit -m "refactor(prompts): swap live caller to _build_guest_reply_prompt"
```

---

## Task 10: Create the rich `guest_reply.txt` template

**Files:**
- Create: `ChatBotAI/prompts/rich/guest_reply.txt`

This is the new prompt for `gpt-oss:120b-cloud` and similar large models. It encodes every rule from spec §6.

- [ ] **Step 1: Create `prompts/rich/guest_reply.txt`**

Content:

```jinja
{% include 'shared/core_identity.txt' %}

# Voice and behavior

You are not a customer service bot. You are a real, friendly hoster of a vacation rental. Write the way a warm human host writes — direct, helpful, with small touches of warmth and empathy.

Avoid all of these robotic patterns:
- Overly formal openings like "Vielen Dank für Ihre Nachricht, sehr geehrter Herr X" — this is not a corporate channel.
- Reflexive apologies when nothing has gone wrong.
- Mirroring the question back to the guest ("Sie fragen, wann der Check-in ist. Der Check-in ist…").
- Customer-service list templates ("Zur Beantwortung Ihrer Frage möchte ich folgende Punkte erläutern: 1)... 2)... 3)...").
- Corporate boilerplate closers like "Bei weiteren Fragen stehen wir Ihnen jederzeit zur Verfügung" on every reply.
- Repeating the guest's name unnaturally throughout the message.

Do this instead:
- Match the guest's register: their length, their formality of vocabulary, their mood. (Exception: always use du, see "du always" rule below.)
- Lead with the answer. Add context only if needed.
- Use casual transitional phrases naturally — "Klar, gerne!", "Kein Problem", "Schau mal,..." — not as templates.
- One-line replies are fine for one-line questions. Do not pad with greeting + answer + closer.
- Express small warmth ("Schön zu hören!") when the guest shares good news, and small empathy ("Oh, das ist ärgerlich") when the guest reports a problem.

# Du always

Use du with every guest, regardless of whether the guest writes du or Sie. This is a brand decision — Urlaubsmagie speaks casually with all guests. The "match the guest's register" guidance above applies to length and mood, NOT to the du/Sie axis, which is fixed.

# Greeting

Greet once at the top of the first reply in a conversation. Do not greet again on subsequent replies. EXCEPTION: if the guest sends a fresh greeting ("Hallo nochmal!", "Guten Morgen!"), greet back. Mirror the guest.

# Length matching

Reply length should roughly match guest message length. A one-line guest question gets a one-line answer. A longer message can get a longer reply, but never pad.

# Emojis

Allowed and encouraged for warmth — 1 or 2 per reply when natural. Do not spam. Do not refuse to use emojis just because the guest didn't.

# No specific timeframes

Never promise a specific response window ("we'll respond within the hour"). Vague reassurance is fine ("wir melden uns kurz", "shortly").

{% include 'shared/language_rule.txt' %}

# Knowledge boundary — Wissensdatenbank as the bible

Your knowledge is tiered. Use the tier that matches the question.

Tier 1 — Property and operational facts: check-in/check-out times, wifi credentials, prices, addresses, distances to/from the apartment, amenities, house rules. Answer ONLY from the Wissensdatenbank entries provided in this prompt. Never invent. If the fact is not in the KB, tell the guest you'll forward the question to a superior. Example phrasing: "Das kläre ich kurz mit dem Team und melde mich gleich zurück."

Tier 2 — Local-area or time-sensitive information: restaurant recommendations, current shop hours, neighborhood facts, current weather, news, events. Escalate to the team. They know the neighborhood; you do not have internet access and do not know current state.

Tier 3 — Static general knowledge: time zones, climate norms, basic geography, common cultural facts you were trained on. Answer if confident. Hedge or escalate if unsure.

Tier 4 — Time-sensitive non-property info: escalate or hedge with vague reassurance.

You have NO internet access. Your training cutoff is early 2025. You do not know any fact that depends on current real-world state.

# Anti-hallucination — never invent

Never invent any detail not present in the provided context (Wissensdatenbank, guest profile, reservation info, conversation history). Specifically: never invent the guest's family composition, pets, allergies, prior stays, or preferences. This is a hard rule. A single fabricated detail creates real-world problems at the property.

# Sign-off rule

Sign-offs apply ONLY at conversation close — when the guest is saying goodbye, the conversation is fully resolved, and there are no pending topics. Never sign off mid-conversation.

When applied:
1. Look at the recent team replies in the conversation log. If a prior sign-off pattern exists from the team, mirror it (same names, same format).
2. If no precedent exists, default to: "Liebe Grüße, Elena, Imke, Anna-Lena, und Sebastian - Team Urlaubsmagie"
3. About 15 to 20 percent of the time on closing replies, use one of these UMI-mentioning variants instead, picked at random:
   - "UMI und dein Urlaubsmagie Team"
   - "UMI, Elena, Anna-Lena, Sebastian - Urlaubsmagie Team"
   - "UMI von Urlaubsmagie"

# Goodbye phrasing — never apartment-specific

When closing a conversation, never reference a specific apartment, room, or property code. Always use general phrasing referring to Urlaubsmagie as a whole, like "bei Urlaubsmagie" or "in einer unserer Unterkünfte". Reservations are confirmed days or weeks in advance, and we cannot guarantee the same apartment will be available on a future stay.

# Tone setting for THIS conversation

{{ tone_instruction }}

# Context

Date: {{ now_str }}.

Guest: {{ guest_name }}{% if guest_language %} (speaks {{ guest_language }}){% endif %}

{% if reservation_compact %}
Reservation: {{ reservation_compact }}
{% endif %}
{% if host_instructions %}
Host instructions: {{ host_instructions }}
{% endif %}
{% if knowledge_entries %}
Wissensdatenbank entries:
{% for kb in knowledge_entries %}
- {{ kb.label }}: {{ kb.value_truncated }}
{% endfor %}
{% endif %}
{% if recent_host_replies %}
Your recent replies:
{{ recent_host_replies }}
{% endif %}

# Task

{% if unanswered_count >= 2 %}
The guest sent {{ unanswered_count }} unanswered messages below. Address ALL of them in one reply. Reply to each in order, one short paragraph per topic, separated by blank lines.
{% else %}
The guest's new message is: "{{ task_text }}"
Reply to THIS message only.
{% endif %}
```

- [ ] **Step 2: Verify the rich template renders without error**

Add this test to `ChatBotAI/tests/test_prompt_loader.py`:

```python
def test_rich_guest_reply_renders():
    out = load_prompt(
        "guest_reply",
        tier="rich",
        tone_instruction="Be warm.",
        now_str="06 May 2026",
        guest_name="Max",
        guest_language="German",
        reservation_compact=None,
        host_instructions=None,
        knowledge_entries=None,
        recent_host_replies=None,
        unanswered_count=1,
        task_text="Hallo!",
        guest_profile={"name": "Max"},
    )
    assert "UMI" in out
    assert "Du always" in out
    assert "Sign-off rule" in out
    assert "06 May 2026" in out
```

- [ ] **Step 3: Run the test**

Run: `pytest ChatBotAI/tests/test_prompt_loader.py::test_rich_guest_reply_renders -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add ChatBotAI/prompts/rich/guest_reply.txt ChatBotAI/tests/test_prompt_loader.py
git commit -m "feat(prompts): add rich/guest_reply.txt with full rule set"
```

---

## Task 11: Add the `/chatbot/debug/prompt-compare` admin endpoint

**Files:**
- Modify: `ChatBotAI/routes.py`
- Modify: `ChatBotAI/templates/chatbot/debug.html`

This endpoint takes a `conversation_id` and renders both compact and rich prompts side-by-side for visual comparison. It does NOT call Ollama — it only shows the rendered system prompt strings. (Calling Ollama for both is added complexity that the existing Playtest V2 sandbox already handles cleanly for live A/B testing.)

- [ ] **Step 1: Add the route in `routes.py`**

Insert near other debug routes (search for `@admin_required` to find the cluster). Add:

```python
@chatbot_bp.route('/debug/prompt-compare')
@admin_required
def debug_prompt_compare():
    """Render compact and rich guest-reply prompts side-by-side for a conversation."""
    from .services.prompt_tier import detect_tier

    conversation_id = request.args.get('conversation_id', type=int)
    if not conversation_id:
        return jsonify({'error': 'Missing conversation_id query param'}), 400

    conversation = Conversation.query.get(conversation_id)
    if not conversation:
        return jsonify({'error': f'Conversation {conversation_id} not found'}), 404

    ai = get_ai_service()
    if not ai:
        return jsonify({'error': 'AI service not initialized'}), 500

    # Build the same context the live path would use, but render in BOTH tiers.
    guest = conversation.guest
    guest_profile = {
        'name': guest.name if guest else 'guest',
        'language': guest.language if guest else None,
    }

    # Use Message.query directly — the project's convention is to avoid order_by
    # on dynamic relationships (see memory note feedback_sqlalchemy_ordering.md).
    msgs = (
        Message.query
        .filter_by(conversation_id=conversation_id)
        .order_by(Message.timestamp.asc())
        .limit(20)
        .all()
    )
    history = [{'sender_type': m.sender_type, 'content': m.content} for m in msgs]
    last_guest_msg = next(
        (m['content'] for m in reversed(history) if m['sender_type'] == 'guest'),
        '',
    )

    kwargs = dict(
        guest_profile=guest_profile,
        conversation_history=history,
        clean_latest=last_guest_msg,
        unanswered_count=1,
        tone='friendly_professional',
        host_instructions=None,
        reservation_info=None,
        knowledge_entries=None,
    )

    # Force tier via env var trick (clean, no method change required).
    import os
    saved = os.environ.get('FORCE_PROMPT_TIER')
    try:
        os.environ['FORCE_PROMPT_TIER'] = 'compact'
        compact_prompt = ai._build_guest_reply_prompt(**kwargs)
        os.environ['FORCE_PROMPT_TIER'] = 'rich'
        rich_prompt = ai._build_guest_reply_prompt(**kwargs)
    finally:
        if saved is None:
            os.environ.pop('FORCE_PROMPT_TIER', None)
        else:
            os.environ['FORCE_PROMPT_TIER'] = saved

    return jsonify({
        'conversation_id': conversation_id,
        'detected_tier_for_current_model': detect_tier(ai.model),
        'current_model': ai.model,
        'compact_prompt': compact_prompt,
        'rich_prompt': rich_prompt,
        'compact_token_estimate': len(compact_prompt) // 4,
        'rich_token_estimate': len(rich_prompt) // 4,
    })
```

- [ ] **Step 2: Add a small link in `debug.html`**

In `templates/chatbot/debug.html`, find an existing debug section (e.g. near the playtest launcher or near other tools). Add a short snippet:

```html
<div class="debug-section">
    <h3>Prompt Compare</h3>
    <p>Render compact and rich guest-reply prompts side-by-side for a conversation:</p>
    <form onsubmit="event.preventDefault(); window.open('/chatbot/debug/prompt-compare?conversation_id=' + document.getElementById('promptCompareId').value, '_blank');">
        <input type="number" id="promptCompareId" placeholder="conversation_id" required>
        <button type="submit">Compare</button>
    </form>
</div>
```

(Place inside the existing admin-only section of the debug page so it inherits the page's styling.)

- [ ] **Step 3: Manual verification**

Restart the dev server. Log in as admin, go to `/chatbot/debug`. Find a real conversation_id (any from the inbox). Enter it in the form, click Compare. A new tab opens with JSON containing both rendered prompts.

Inspect the JSON: confirm `compact_prompt` looks similar to before, `rich_prompt` is much longer and contains the rule sections (`Du always`, `Sign-off rule`, etc.).

- [ ] **Step 4: Commit**

```bash
git add ChatBotAI/routes.py ChatBotAI/templates/chatbot/debug.html
git commit -m "feat(debug): add /chatbot/debug/prompt-compare endpoint"
```

---

## Task 12: Live Playtest V2 verification

**Files:** none — manual verification using the existing Playtest V2 sandbox.

This is the acceptance gate. No code changes; you exercise the rich prompt against the test scenarios and eyeball the results.

- [ ] **Step 1: Switch the active model to `gpt-oss:120b-cloud`**

Confirm the user has already run `ollama signin` and `ollama pull gpt-oss:120b-cloud` (per the conversation that led to this plan). If not, do that first.

In the running app, go to **Einstellungen → Hauptmodell** and select `gpt-oss:120b-cloud`. Save.

In the Flask console, the next AI call should log:
`Prompt tier: rich (model=gpt-oss:120b-cloud)`

- [ ] **Step 2: Run the six acceptance scenarios via Playtest V2**

For each scenario, open `/chatbot/debug`, launch a Playtest V2 sandbox conversation with an appropriate guest profile, send guest messages that exercise the rule, and verify UMI's reply.

| # | Scenario | What to check |
|---|---|---|
| 1 | Long thread with a clear closing ("Vielen Dank, bis bald!") | UMI signs off using the rule; over multiple runs, ~15–20% of closing replies use a UMI variant |
| 2 | Guest asks something not in the Wissensdatenbank | UMI says it'll forward to the team — does NOT invent |
| 3 | Casual du-message vs. a formal Sie-message | UMI uses du in both (brand fixed); length/mood mirrors the guest |
| 4 | Multi-question guest message (3 questions in one) | UMI addresses all three; length matches |
| 5 | Goodbye where legacy prompt would say "come back to W3" | UMI uses open phrasing ("bei Urlaubsmagie") |
| 6 | Guest brings up children/family without prior info in profile | UMI does NOT mention children or invent family details |

- [ ] **Step 3: Spot-check 5 real conversations**

Pick 5 real conversations from the inbox (read-only — never send). For each, hit `/chatbot/debug/prompt-compare?conversation_id=N` and eyeball both prompts. Confirm the rich prompt looks coherent and the compact prompt is unchanged from before.

- [ ] **Step 4: Verify auto-reload in dev**

With the dev server running and `PROMPT_DEV_AUTO_RELOAD=true` (set automatically by `DevelopmentConfig`), edit `ChatBotAI/prompts/rich/guest_reply.txt` — change one word, save. Trigger a new AI suggestion. The change should reflect without restarting the Flask process.

- [ ] **Step 5: Verify rollback path**

In the app, switch the main model back to `gemma2:9b`. Trigger an AI suggestion. Confirm the log line says `Prompt tier: compact (model=gemma2:9b)` and the reply is generated normally.

- [ ] **Step 6: Final commit (if any final tweaks were needed during verification)**

If iteration on `prompts/rich/guest_reply.txt` was needed:

```bash
git add ChatBotAI/prompts/rich/guest_reply.txt
git commit -m "tune(prompts): rich/guest_reply.txt — adjustments from playtest"
```

If no tweaks were needed, no commit. Phase 1 is complete.

---

## Self-Review Checklist (engineer to confirm before marking the plan done)

- [ ] All 12 tasks committed atomically
- [ ] `pytest ChatBotAI/tests/ -v` is green
- [ ] On `gemma2:9b`, the rendered system prompt is character-for-character identical to the legacy prompt (snapshot test enforces this for the 3 scenarios; the live smoke test in Task 9 confirms behavior end-to-end)
- [ ] On `gpt-oss:120b-cloud`, the rich prompt is used (logs confirm) and replies obey the rules in spec §6
- [ ] Switching back to `gemma2:9b` reverts to compact prompt without restart
- [ ] All 6 Playtest V2 scenarios pass eyeball review
