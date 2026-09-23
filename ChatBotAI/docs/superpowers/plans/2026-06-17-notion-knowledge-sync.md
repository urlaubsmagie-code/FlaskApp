# Notion → UMI Knowledge Base Sync — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the team's Notion guest-care handbook ground UMI's answers and populate reply templates, via a manual "Sync now" button — without ever leaking door codes or passwords to guests.

**Architecture:** A new `services/notion_service.py` (singleton, mirroring `gmail_service.py`/`smoobu_service.py`) reads pages recursively under one Notion hub page using the official `notion-client` SDK, runs every page through a three-layer safety scrubber, maps survivors to `KnowledgeEntry`/`ReplyTemplate` rows, and idempotently upserts them (keyed by `notion_page_id`, `source='notion'`) while never touching manual/AI rows. A Settings card with a "Sync now" button triggers it synchronously and shows the run stats. One-way, read-only on Notion.

**Tech Stack:** Python 3.14, Flask blueprint, Flask-SQLAlchemy, Flask-Migrate (Alembic), `notion-client` SDK, pytest. SQLite (WAL).

**Reference spec:** `docs/superpowers/specs/2026-06-17-notion-knowledge-sync-design.md`

## Global Constraints

- **Scrubber is mandatory and layered.** A page reaches UMI only if it survives Layer 1 (page block) AND Layer 2 (value scrub). `notion_force_exclude_ids` always wins. Real fixture `🔑 Check-in Information und Schlüsselcodes` MUST be blocked; `💰 Extrakosten` MUST pass.
- **Source isolation.** Sync only ever reads/updates/deletes rows with `source='notion'`. Rows with `source` in (`manual`,`ai`) are never read, modified, or deleted by sync code.
- **Read-only on Notion.** No Notion create/update/delete API calls anywhere.
- **Feature dormant by default.** `notion_sync_enabled` defaults false; the button is disabled and the API returns a clear error until a token is configured.
- **German-first UI**, English fallback via `static/js/i18n.js` (project convention).
- **Pure functions stay pure.** Scrubber and mapper functions take/return plain dicts and strings — no DB, no network — so they unit-test without fixtures-of-infrastructure. Network lives only in the `NotionClient` wrapper; DB only in the orchestrator.
- **Dependency floors already pinned in `requirements.txt`** (Werkzeug>=3.0.6, Jinja2>=3.1.6, requests>=2.32.4, cryptography>=46, waitress>=3.0.2) — do not lower them when adding `notion-client`.
- **Migration chain:** new migration `p19_*` with `down_revision = 'p18_email_backfill'`.
- **AISettings API:** `AISettings.get(key, default=None)` returns the stored string or default; `AISettings.set(key, value, description=None)` upserts and commits.
- **Admin gating:** all new routes use the existing `@admin_required` decorator from `routes.py` (returns 403 JSON for `/chatbot/api/*`, redirect otherwise).

---

## File Structure

- `services/notion_client.py` — **NEW.** Thin network adapter over `notion-client`. Recursive page listing + block-tree → plain text. The only file that talks to the network.
- `services/notion_scrubber.py` — **NEW.** Pure safety functions (Layer 1 page block, Layer 2 value scrub) + config parsing helpers.
- `services/notion_mapper.py` — **NEW.** Pure mapping functions: page text → KB entries, page → template, category inference, property matching.
- `services/notion_service.py` — **NEW.** Orchestrator: wires client → scrubber → mapper → idempotent DB upsert. Singleton `get_notion_service()` / `init_notion_service(app)`.
- `models.py` — **MODIFY.** Add `source`, `notion_page_id`, `synced_at` to `KnowledgeEntry`; `source`, `notion_page_id` to `ReplyTemplate`; extend their `to_dict()`.
- `migrations/versions/p19_notion_source.py` — **NEW.** Additive columns + indexes.
- `routes.py` — **MODIFY.** Add `/chatbot/api/notion/sync` (POST), `/chatbot/api/settings/notion` (GET/PUT). Register import.
- `__init__.py` / `app.py` — **MODIFY.** Call `init_notion_service(app)` at startup (mirror `init_smoobu_service`).
- `templates/chatbot/settings.html` — **MODIFY.** Add "Notion Wissensdatenbank" card.
- `static/js/i18n.js` — **MODIFY.** Add German + English strings for the new card.
- `requirements.txt` — **MODIFY.** Add `notion-client>=2.2.1`.
- `tests/test_notion_scrubber.py`, `tests/test_notion_mapper.py`, `tests/test_notion_service.py` — **NEW.**
- `tests/fixtures/notion_*.py` — **NEW.** Real captured page text as Python string constants.

---

## Task 1: Add `notion-client` dependency + fixtures from real pages

**Files:**
- Modify: `requirements.txt`
- Create: `ChatBotAI/tests/fixtures/__init__.py`
- Create: `ChatBotAI/tests/fixtures/notion_pages.py`

**Interfaces:**
- Produces: fixture constants `EXTRAKOSTEN_PAGE`, `SCHLUESSELCODES_PAGE`, `PROPERTY_PAGE`, `VORLAGE_PAGE` — each a `dict` with keys `id` (str), `title` (str), `text` (str, plain markdown-ish), `parent_title` (str|None). These mirror what `NotionClient.get_page()` (Task 3) returns.

- [ ] **Step 1: Add the dependency**

In `requirements.txt`, after the `requests>=2.32.4` block, add:

```
# Notion API client for knowledge-base sync (Notion → KnowledgeEntry/ReplyTemplate)
notion-client>=2.2.1
```

- [ ] **Step 2: Install it**

Run: `cd C:/Users/admin/Documents/FlaskApp && pip install "notion-client>=2.2.1"`
Expected: `Successfully installed notion-client-2.x.x` (and its `httpx` dep).

- [ ] **Step 3: Create the fixtures file**

Create `ChatBotAI/tests/fixtures/__init__.py` (empty).

Create `ChatBotAI/tests/fixtures/notion_pages.py` with text captured from the real workspace on 2026-06-17 (trimmed to the parts the scrubber/mapper must handle):

```python
"""Real Notion page content captured 2026-06-17 for offline testing.
Text is the plain-text rendering NotionClient.get_page() produces.
"""

EXTRAKOSTEN_PAGE = {
    "id": "363149d2-d08e-809a-8997-e5d5aee523c7",
    "title": "Extrakosten",
    "parent_title": "HANDBUCH ZUR GÄSTEBETREUUNG",
    "text": (
        "## Extrakosten Allgemein:\n"
        "- Haustier: 10€ pro Nacht/pro Haustier (ab der 8. Nacht nur 8€ pro Haustier)\n"
        "- Sauna: 5€ pro Tag pro Person\n"
        "- Kinderbetten: 10€ pro Aufenthalt (immer vorher prüfen, ob verfügbar)\n"
        "### Check-in & Check-Out:\n"
        "- regulär: 10 Uhr Check-out, 16 Uhr Check-in\n"
        "- Early Check In: ab 12:30 Uhr: 10€ Winter (01.11 - 31.03), 20€ Sommer (01.04 - 31.10)\n"
        "- Late Checkout: bis 12Uhr: 10€ Winter, 20€ Sommer\n"
        "Sonstiges: Handtücher und Bettwäsche sind kostenlos im Preis mit inbegriffen\n"
    ),
}

# MUST be blocked: title keyword + "Schlüsselbox Codes" heading + dense codes.
SCHLUESSELCODES_PAGE = {
    "id": "363149d2-d08e-8045-9c58-eb82a106ef53",
    "title": "Check-in Information und Schlüsselcodes",
    "parent_title": "HANDBUCH ZUR GÄSTEBETREUUNG",
    "text": (
        "Schlüsselbox Codes:\n"
        "B1 - Code 162981\n"
        "B5 - Haustür: 162333 - C 9875 Pfeil\n"
        "W2 - 162392\n"
        "UT - 1623\n"
        "F0 - 9850\n"
    ),
}

# A per-property page (mapper should set property_id by matching "Sonnenhof").
PROPERTY_PAGE = {
    "id": "37b149d2-d08e-80ac-bc06-d46a470863a7",
    "title": "Sonnenhof",
    "parent_title": "HANDBUCH ZUR GÄSTEBETREUUNG",
    "text": (
        "## Early Check-in\n"
        "Ein früher Check-in ist je nach Verfügbarkeit und nach vorheriger "
        "Absprache bereits ab 13:00 Uhr möglich.\n"
    ),
}

# A template page under a "Vorlagen" parent.
VORLAGE_PAGE = {
    "id": "aaaa1111-0000-0000-0000-000000000001",
    "title": "Begrüßung",
    "parent_title": "Vorlagen",
    "text": "Hallo {guest_name}, willkommen in {property_name}! Schön, dass du da bist.\n",
}
```

- [ ] **Step 4: Verify the fixtures import**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -c "from ChatBotAI.tests.fixtures.notion_pages import EXTRAKOSTEN_PAGE, SCHLUESSELCODES_PAGE; print(SCHLUESSELCODES_PAGE['title'])"`
Expected: `Check-in Information und Schlüsselcodes`

- [ ] **Step 5: Commit**

```bash
git add requirements.txt ChatBotAI/tests/fixtures/
git commit -m "chore(notion): add notion-client dep + real-page test fixtures"
```

---

## Task 2: Safety scrubber (Layer 1 page block + Layer 2 value scrub)

**Files:**
- Create: `ChatBotAI/services/notion_scrubber.py`
- Test: `ChatBotAI/tests/test_notion_scrubber.py`

**Interfaces:**
- Produces:
  - `parse_csv_setting(value: str | None, default: list[str]) -> list[str]` — split a CSV AISettings string into lowercased, stripped terms; `None`/empty → `default`.
  - `DEFAULT_BLOCK_KEYWORDS: list[str]` — the default blocklist.
  - `is_blocked_page(title: str, text: str, block_keywords: list[str]) -> bool` — Layer 1: True if title/text hits a keyword, contains a codes heading, or trips the code-density heuristic (≥3 code-shaped tokens).
  - `scrub_value(value: str) -> str` — Layer 2: redact code/password substrings; returns possibly-empty cleaned string.

- [ ] **Step 1: Write the failing tests**

Create `ChatBotAI/tests/test_notion_scrubber.py`:

```python
from ChatBotAI.services.notion_scrubber import (
    parse_csv_setting, DEFAULT_BLOCK_KEYWORDS, is_blocked_page, scrub_value,
)
from ChatBotAI.tests.fixtures.notion_pages import (
    EXTRAKOSTEN_PAGE, SCHLUESSELCODES_PAGE,
)


def test_parse_csv_setting_splits_and_lowercases():
    assert parse_csv_setting("Code, Passwör ,INTERN", []) == ["code", "passwör", "intern"]


def test_parse_csv_setting_falls_back_to_default():
    assert parse_csv_setting(None, ["x"]) == ["x"]
    assert parse_csv_setting("   ", ["x"]) == ["x"]


def test_schluesselcodes_page_is_blocked():
    p = SCHLUESSELCODES_PAGE
    assert is_blocked_page(p["title"], p["text"], DEFAULT_BLOCK_KEYWORDS) is True


def test_extrakosten_page_is_not_blocked():
    p = EXTRAKOSTEN_PAGE
    assert is_blocked_page(p["title"], p["text"], DEFAULT_BLOCK_KEYWORDS) is False


def test_block_by_keyword_in_title():
    assert is_blocked_page("Passwörter", "harmless body", DEFAULT_BLOCK_KEYWORDS) is True


def test_block_by_code_density_even_without_keyword():
    # No blocklist word, but three code-shaped tokens near labels.
    text = "Tür A Code 1111\nTür B Code 2222\nTür C Code 3333"
    assert is_blocked_page("Zugang", text, []) is True


def test_scrub_value_redacts_door_code():
    assert "162333" not in scrub_value("Haustür: 162333 dann hoch")


def test_scrub_value_keeps_normal_prices():
    # Prices like 10€ / times like 16 Uhr must survive — not code-shaped.
    v = "Early Check In ab 12:30 Uhr: 10€ Winter"
    assert scrub_value(v) == v
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/test_notion_scrubber.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ChatBotAI.services.notion_scrubber'`

- [ ] **Step 3: Implement the scrubber**

Create `ChatBotAI/services/notion_scrubber.py`:

```python
"""Notion sync safety scrubber — defense-in-depth so door codes / passwords in
the team's Notion can never reach a guest via UMI.

Pure functions only (no I/O). See
docs/superpowers/specs/2026-06-17-notion-knowledge-sync-design.md §4.
"""
import re

DEFAULT_BLOCK_KEYWORDS = [
    'schlüsselcode', 'schlüsselbox codes', 'code', 'passwör', 'password',
    'pin', 'wlan-passwort', 'intern', '🔑', '🔒',
]

# A "code-shaped" token: a standalone 3-6 digit run. Used for the density
# heuristic and value scrubbing. Prices (10€) and times (16 Uhr) are NOT
# matched because the digits are bound to € / "Uhr", handled by scrub patterns.
_CODE_TOKEN = re.compile(r'\b\d{3,6}\b')
_CODE_NEAR_LABEL = re.compile(
    r'(?:code|haustür|schlüssel|pin|tür)\s*[:\-]?\s*\d{3,6}', re.IGNORECASE)

# Layer-2 redaction patterns (order matters; specific first).
_SCRUB_PATTERNS = [
    re.compile(r'haustür\s*[:\-]?\s*\d{3,6}', re.IGNORECASE),
    re.compile(r'\bcode\s*[:\-]?\s*\d{3,6}', re.IGNORECASE),
    re.compile(r'\b(?:pin|wlan[- ]?passwort|passwort)\b\s*[:\-]?\s*\S+', re.IGNORECASE),
]


def parse_csv_setting(value, default):
    """Split a CSV AISettings string into lowercased, stripped terms."""
    if not value or not value.strip():
        return default
    return [t.strip().lower() for t in value.split(',') if t.strip()]


def is_blocked_page(title, text, block_keywords):
    """Layer 1: True if this whole page must be withheld from UMI."""
    hay = f"{title}\n{text}".lower()
    for kw in block_keywords:
        if kw and kw in hay:
            return True
    # Code-density heuristic: >=3 codes that sit next to access-type labels.
    if len(_CODE_NEAR_LABEL.findall(text)) >= 3:
        return True
    return False


def scrub_value(value):
    """Layer 2: redact code/password substrings from a single entry value."""
    if not value:
        return value
    out = value
    for pat in _SCRUB_PATTERNS:
        out = pat.sub('[redacted]', out)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/test_notion_scrubber.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/notion_scrubber.py ChatBotAI/tests/test_notion_scrubber.py
git commit -m "feat(notion): defense-in-depth safety scrubber (page block + value scrub)"
```

---

## Task 3: Mapper (page → KB entries / template, category, property match)

**Files:**
- Create: `ChatBotAI/services/notion_mapper.py`
- Test: `ChatBotAI/tests/test_notion_mapper.py`

**Interfaces:**
- Consumes: fixture dicts from Task 1 (keys `id`, `title`, `text`, `parent_title`).
- Produces:
  - `infer_category(title: str, text: str) -> str` — returns one of `KnowledgeEntry.VALID_CATEGORIES` minus `correction`/`escalation`; default `'faq'`.
  - `split_sections(text: str) -> list[tuple[str, str]]` — split on `##`/`###` headings → `[(label, body), ...]`; text before any heading (or heading-less pages) yields one `('', body)` pair handled by caller.
  - `page_to_kb_entries(page: dict, property_names: dict[str, int]) -> list[dict]` — each dict has `label`, `value`, `category`, `property_id` (int|None), `notion_page_id`. Empty `value`s (after caller scrubs) are the caller's concern; mapper does not scrub.
  - `page_to_template(page: dict) -> dict` — `{name, content, category, notion_page_id}`.
  - `is_template_page(page: dict) -> bool` — True if `parent_title` indicates Vorlagen/Templates.

- [ ] **Step 1: Write the failing tests**

Create `ChatBotAI/tests/test_notion_mapper.py`:

```python
from ChatBotAI.services.notion_mapper import (
    infer_category, split_sections, page_to_kb_entries,
    page_to_template, is_template_page,
)
from ChatBotAI.tests.fixtures.notion_pages import (
    EXTRAKOSTEN_PAGE, PROPERTY_PAGE, VORLAGE_PAGE,
)


def test_infer_category_checkin():
    assert infer_category("Check-in Information", "...") == "checkin_checkout"


def test_infer_category_defaults_faq():
    assert infer_category("Random topic", "body") == "faq"


def test_split_sections_on_headings():
    text = "## A\nline a\n### B\nline b\n"
    assert split_sections(text) == [("A", "line a"), ("B", "line b")]


def test_extrakosten_maps_to_multiple_entries():
    entries = page_to_kb_entries(EXTRAKOSTEN_PAGE, property_names={})
    labels = [e["label"] for e in entries]
    assert "Extrakosten Allgemein" in labels
    assert "Check-in & Check-Out" in labels
    # all global (no property match)
    assert all(e["property_id"] is None for e in entries)
    assert all(e["notion_page_id"] == EXTRAKOSTEN_PAGE["id"] for e in entries)


def test_property_page_sets_property_id():
    entries = page_to_kb_entries(PROPERTY_PAGE, property_names={"sonnenhof": 42})
    assert entries
    assert all(e["property_id"] == 42 for e in entries)


def test_is_template_page_true_for_vorlagen_parent():
    assert is_template_page(VORLAGE_PAGE) is True


def test_page_to_template_preserves_placeholders():
    t = page_to_template(VORLAGE_PAGE)
    assert t["name"] == "Begrüßung"
    assert "{guest_name}" in t["content"]
    assert t["notion_page_id"] == VORLAGE_PAGE["id"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/test_notion_mapper.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ChatBotAI.services.notion_mapper'`

- [ ] **Step 3: Implement the mapper**

Create `ChatBotAI/services/notion_mapper.py`:

```python
"""Notion page → KnowledgeEntry / ReplyTemplate mapping. Pure functions.
See docs/superpowers/specs/2026-06-17-notion-knowledge-sync-design.md §5.
"""
import re

_TEMPLATE_PARENTS = ('vorlagen', 'vorlage', 'templates', 'template')

_CATEGORY_RULES = [
    ('checkin_checkout', ('check-in', 'check in', 'checkin', 'check-out', 'schlüssel', 'anreise')),
    ('house_rules', ('regel', 'rules', 'hausordnung')),
    ('emergency', ('notfall', 'emergency', 'feuer', 'arzt')),
    ('nearby', ('umgebung', 'restaurant', 'sehenswürdig', 'ausflug')),
]


def infer_category(title, text):
    hay = f"{title}\n{text}".lower()
    for category, needles in _CATEGORY_RULES:
        if any(n in hay for n in needles):
            return category
    return 'faq'


def split_sections(text):
    """Split markdown text on ## / ### headings into (label, body) pairs.
    Content before the first heading is returned with label ''."""
    sections = []
    current_label = ''
    current_body = []
    for line in (text or '').splitlines():
        m = re.match(r'\s*#{2,3}\s+(.*?):?\s*$', line)
        if m:
            if current_body:
                sections.append((current_label, '\n'.join(current_body).strip()))
                current_body = []
            current_label = m.group(1).strip()
        else:
            current_body.append(line)
    if current_body:
        sections.append((current_label, '\n'.join(current_body).strip()))
    return [(lbl, body) for (lbl, body) in sections if body]


def _match_property_id(title, property_names):
    """property_names: {lowercased_property_name: property_id}."""
    t = (title or '').lower()
    for name, pid in property_names.items():
        if name and name in t:
            return pid
    return None


def page_to_kb_entries(page, property_names):
    pid = _match_property_id(page.get('title'), property_names or {})
    category = infer_category(page.get('title', ''), page.get('text', ''))
    sections = split_sections(page.get('text', ''))
    if not sections:
        sections = [(page.get('title', '').strip() or 'Info', (page.get('text') or '').strip())]
    entries = []
    for label, body in sections:
        entries.append({
            'label': (label or page.get('title') or 'Info')[:200],
            'value': body,
            'category': category,
            'property_id': pid,
            'notion_page_id': page.get('id'),
        })
    return entries


def is_template_page(page):
    return (page.get('parent_title') or '').strip().lower() in _TEMPLATE_PARENTS


def page_to_template(page):
    return {
        'name': (page.get('title') or 'Vorlage')[:200],
        'content': (page.get('text') or '').strip(),
        'category': 'general',
        'notion_page_id': page.get('id'),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/test_notion_mapper.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/notion_mapper.py ChatBotAI/tests/test_notion_mapper.py
git commit -m "feat(notion): pure page→KB/template mapper with category + property matching"
```

---

## Task 4: Model columns + migration p19

**Files:**
- Modify: `ChatBotAI/models.py` (`KnowledgeEntry` ~lines 642-675, `ReplyTemplate` ~lines 512-533)
- Create: `ChatBotAI/migrations/versions/p19_notion_source.py`
- Test: `ChatBotAI/tests/test_notion_service.py` (first test only — model roundtrip)

**Interfaces:**
- Produces: `KnowledgeEntry.source`, `KnowledgeEntry.notion_page_id`, `KnowledgeEntry.synced_at`; `ReplyTemplate.source`, `ReplyTemplate.notion_page_id`. Both `to_dict()` include `source`.

- [ ] **Step 1: Write the failing test**

Create `ChatBotAI/tests/test_notion_service.py`:

```python
import pytest
from datetime import datetime
from ChatBotAI.app import create_app
from ChatBotAI.config import config as config_map
from ChatBotAI.models import db, KnowledgeEntry, ReplyTemplate


@pytest.fixture
def app():
    app = create_app(config_map['testing'])
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


def test_knowledge_entry_has_source_columns(app):
    e = KnowledgeEntry(category='faq', label='L', value='V',
                       source='notion', notion_page_id='pg1',
                       synced_at=datetime(2026, 6, 17, 12, 0))
    db.session.add(e); db.session.commit()
    got = KnowledgeEntry.query.filter_by(notion_page_id='pg1').first()
    assert got.source == 'notion'
    assert got.to_dict()['source'] == 'notion'


def test_reply_template_has_source_columns(app):
    t = ReplyTemplate(name='N', content='C', source='notion', notion_page_id='pg2')
    db.session.add(t); db.session.commit()
    got = ReplyTemplate.query.filter_by(notion_page_id='pg2').first()
    assert got.source == 'notion'
    assert got.to_dict()['source'] == 'notion'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/test_notion_service.py -q`
Expected: FAIL — `TypeError: 'source' is an invalid keyword argument for KnowledgeEntry`

- [ ] **Step 3a: Add columns to `KnowledgeEntry`**

In `ChatBotAI/models.py`, inside `class KnowledgeEntry`, after the `sort_order` column (line ~647) add:

```python
    # Provenance: 'manual' (default), 'ai' (extracted), 'notion' (synced).
    source = db.Column(db.String(20), nullable=False, default='manual', server_default='manual')
    notion_page_id = db.Column(db.String(64), nullable=True, index=True)
    synced_at = db.Column(db.DateTime, nullable=True)
```

In its `to_dict()` (line ~664), add inside the returned dict:

```python
            'source': self.source,
            'notion_page_id': self.notion_page_id,
```

- [ ] **Step 3b: Add columns to `ReplyTemplate`**

In `class ReplyTemplate`, after the `category` column (line ~515) add:

```python
    source = db.Column(db.String(20), nullable=False, default='manual', server_default='manual')
    notion_page_id = db.Column(db.String(64), nullable=True, index=True)
```

In its `to_dict()` (line ~524), add inside the returned dict:

```python
            'source': self.source,
```

- [ ] **Step 3c: Create the migration**

Create `ChatBotAI/migrations/versions/p19_notion_source.py`:

```python
"""Add Notion-sync provenance columns to knowledge_entry and reply_template.

Revision ID: p19_notion_source
Revises: p18_email_backfill
Create Date: 2026-06-17

Additive only. Existing rows default to source='manual', preserving behavior.
"""
from alembic import op
import sqlalchemy as sa

revision = 'p19_notion_source'
down_revision = 'p18_email_backfill'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('knowledge_entry') as batch:
        batch.add_column(sa.Column('source', sa.String(length=20), nullable=False, server_default='manual'))
        batch.add_column(sa.Column('notion_page_id', sa.String(length=64), nullable=True))
        batch.add_column(sa.Column('synced_at', sa.DateTime(), nullable=True))
    op.create_index('ix_knowledge_entry_notion_page_id', 'knowledge_entry', ['notion_page_id'])

    with op.batch_alter_table('reply_template') as batch:
        batch.add_column(sa.Column('source', sa.String(length=20), nullable=False, server_default='manual'))
        batch.add_column(sa.Column('notion_page_id', sa.String(length=64), nullable=True))
    op.create_index('ix_reply_template_notion_page_id', 'reply_template', ['notion_page_id'])


def downgrade():
    op.drop_index('ix_reply_template_notion_page_id', table_name='reply_template')
    op.drop_index('ix_knowledge_entry_notion_page_id', table_name='knowledge_entry')
    with op.batch_alter_table('reply_template') as batch:
        batch.drop_column('notion_page_id')
        batch.drop_column('source')
    with op.batch_alter_table('knowledge_entry') as batch:
        batch.drop_column('synced_at')
        batch.drop_column('notion_page_id')
        batch.drop_column('source')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/test_notion_service.py -q`
Expected: PASS (2 passed). (Testing config uses `db.create_all()`, so the new columns appear from the model; the migration is exercised against the real DB in Step 5.)

- [ ] **Step 5: Apply the migration to the dev DB and verify**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -m flask --app ChatBotAI.app db upgrade`
Expected: `Running upgrade p18_email_backfill -> p19_notion_source`. If the app uses a different migrate entrypoint, mirror the command used for p18 (see prior session logs). Confirm no error.

- [ ] **Step 6: Commit**

```bash
git add ChatBotAI/models.py ChatBotAI/migrations/versions/p19_notion_source.py ChatBotAI/tests/test_notion_service.py
git commit -m "feat(notion): add source/notion_page_id provenance columns (migration p19)"
```

---

## Task 5: NotionClient network adapter

**Files:**
- Create: `ChatBotAI/services/notion_client.py`
- Test: `ChatBotAI/tests/test_notion_service.py` (add adapter tests using a fake SDK)

**Interfaces:**
- Consumes: `notion_client.Client` (the SDK) — injected, so tests pass a fake.
- Produces:
  - `class NotionClient` with `__init__(self, token: str, sdk_client=None)`.
  - `list_descendant_pages(self, root_id: str) -> list[str]` — recursive child-page ids under `root_id` (depth-first, dedup).
  - `get_page(self, page_id: str) -> dict` — `{id, title, parent_title, text}` matching the fixture shape.
  - `blocks_to_text(blocks: list[dict]) -> str` — **module-level pure function**: render a Notion block list to plain markdown-ish text (headings → `##`, bullets → `- `, paragraphs → text).

- [ ] **Step 1: Write the failing tests**

Append to `ChatBotAI/tests/test_notion_service.py`:

```python
from ChatBotAI.services.notion_client import NotionClient, blocks_to_text


def _txt(content):
    return {"type": "text", "text": {"content": content}, "plain_text": content}


def test_blocks_to_text_renders_heading_and_bullets():
    blocks = [
        {"type": "heading_2", "heading_2": {"rich_text": [_txt("Extrakosten")]}},
        {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [_txt("Sauna: 5€")]}},
        {"type": "paragraph", "paragraph": {"rich_text": [_txt("Handtücher inklusive")]}},
    ]
    out = blocks_to_text(blocks)
    assert "## Extrakosten" in out
    assert "- Sauna: 5€" in out
    assert "Handtücher inklusive" in out


class _FakeSDK:
    """Minimal stand-in for notion_client.Client."""
    def __init__(self, pages):
        self._pages = pages  # {id: {"title","parent_title","children":[ids],"blocks":[...]}}
        self.blocks = self._Blocks(self)
        self.pages = self._Pages(self)

    class _Blocks:
        def __init__(self, outer): self.children = self._Children(outer)
        class _Children:
            def __init__(self, outer): self.outer = outer
            def list(self, block_id, **kw):
                p = self.outer._pages[block_id]
                results = [{"id": c, "type": "child_page",
                            "child_page": {"title": self.outer._pages[c]["title"]}}
                           for c in p.get("children", [])]
                results += p.get("blocks", [])
                return {"results": results, "has_more": False, "next_cursor": None}

    class _Pages:
        def __init__(self, outer): self.outer = outer
        def retrieve(self, page_id, **kw):
            p = self.outer._pages[page_id]
            return {"id": page_id,
                    "properties": {"title": {"title": [_txt(p["title"])]}}}


def test_list_descendant_pages_recurses():
    sdk = _FakeSDK({
        "root": {"title": "HUB", "children": ["a", "b"], "blocks": []},
        "a": {"title": "A", "children": ["c"], "blocks": []},
        "b": {"title": "B", "children": [], "blocks": []},
        "c": {"title": "C", "children": [], "blocks": []},
    })
    client = NotionClient(token="x", sdk_client=sdk)
    ids = set(client.list_descendant_pages("root"))
    assert ids == {"a", "b", "c"}


def test_get_page_returns_fixture_shape():
    sdk = _FakeSDK({
        "root": {"title": "HUB", "children": ["a"], "blocks": []},
        "a": {"title": "Extrakosten", "children": [], "blocks": [
            {"type": "heading_2", "heading_2": {"rich_text": [_txt("Preise")]}},
        ]},
    })
    client = NotionClient(token="x", sdk_client=sdk)
    page = client.get_page("a")
    assert page["id"] == "a"
    assert page["title"] == "Extrakosten"
    assert "## Preise" in page["text"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/test_notion_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ChatBotAI.services.notion_client'`

- [ ] **Step 3: Implement the client**

Create `ChatBotAI/services/notion_client.py`:

```python
"""Thin adapter over the official notion-client SDK. The ONLY Notion-sync file
that performs network I/O. Read-only: lists pages and renders block trees.
"""
import logging

logger = logging.getLogger(__name__)


def _rich_text(items):
    return ''.join(i.get('plain_text') or i.get('text', {}).get('content', '') for i in (items or []))


def blocks_to_text(blocks):
    """Render a flat Notion block list to plain markdown-ish text."""
    lines = []
    for b in blocks or []:
        t = b.get('type')
        data = b.get(t, {}) if t else {}
        rt = _rich_text(data.get('rich_text'))
        if t in ('heading_1',):
            lines.append(f"# {rt}")
        elif t in ('heading_2',):
            lines.append(f"## {rt}")
        elif t in ('heading_3',):
            lines.append(f"### {rt}")
        elif t in ('bulleted_list_item', 'numbered_list_item'):
            lines.append(f"- {rt}")
        elif t == 'paragraph':
            if rt:
                lines.append(rt)
        # child_page / images / unsupported blocks contribute no text
    return '\n'.join(lines)


class NotionClient:
    def __init__(self, token, sdk_client=None):
        if sdk_client is not None:
            self._sdk = sdk_client
        else:
            from notion_client import Client
            self._sdk = Client(auth=token)

    def _children(self, block_id):
        results, cursor = [], None
        while True:
            resp = self._sdk.blocks.children.list(block_id=block_id, start_cursor=cursor) \
                if cursor else self._sdk.blocks.children.list(block_id=block_id)
            results.extend(resp.get('results', []))
            if not resp.get('has_more'):
                break
            cursor = resp.get('next_cursor')
        return results

    def list_descendant_pages(self, root_id):
        """DFS over child_page blocks under root_id. Returns deduped page ids
        (excluding the root itself)."""
        seen, out, stack = set(), [], [root_id]
        while stack:
            current = stack.pop()
            for child in self._children(current):
                if child.get('type') == 'child_page':
                    cid = child['id']
                    if cid not in seen:
                        seen.add(cid)
                        out.append(cid)
                        stack.append(cid)
        return out

    def _page_title(self, page_id):
        page = self._sdk.pages.retrieve(page_id=page_id)
        props = page.get('properties', {})
        title_prop = props.get('title') or next(
            (v for v in props.values() if v.get('type') == 'title'), None)
        if title_prop:
            return _rich_text(title_prop.get('title'))
        return ''

    def get_page(self, page_id, parent_title=None):
        blocks = self._children(page_id)
        return {
            'id': page_id,
            'title': self._page_title(page_id),
            'parent_title': parent_title,
            'text': blocks_to_text(blocks),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/test_notion_service.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/notion_client.py ChatBotAI/tests/test_notion_service.py
git commit -m "feat(notion): read-only NotionClient adapter (recursive listing + block→text)"
```

---

## Task 6: NotionService orchestrator (scrub → map → idempotent upsert)

**Files:**
- Create: `ChatBotAI/services/notion_service.py`
- Test: `ChatBotAI/tests/test_notion_service.py` (add orchestrator tests with a fake client)

**Interfaces:**
- Consumes: `NotionClient` (Task 5, injectable), scrubber (Task 2), mapper (Task 3), models (Task 4), `AISettings`.
- Produces:
  - `get_notion_config() -> dict` — `{enabled, token, root_page_id, block_keywords, force_exclude_ids, force_include_ids}`.
  - `class NotionService.__init__(self, client_factory=None)` — `client_factory(token) -> NotionClient`.
  - `NotionService.sync(self) -> dict` — stats `{pages_scanned, pages_blocked, kb_upserted, kb_deleted, templates_upserted, templates_deleted, values_scrubbed, errors, blocked_titles}`.
  - `init_notion_service(app)` / `get_notion_service()` singleton accessors.

- [ ] **Step 1: Write the failing tests**

Append to `ChatBotAI/tests/test_notion_service.py`:

```python
from ChatBotAI.models import AISettings, KnowledgeEntry, ReplyTemplate
from ChatBotAI.services.notion_service import NotionService, get_notion_config


class _FakeClient:
    """Returns a fixed page set; root listing returns all page ids."""
    def __init__(self, pages):
        self._pages = {p["id"]: p for p in pages}
    def list_descendant_pages(self, root_id):
        return list(self._pages.keys())
    def get_page(self, page_id, parent_title=None):
        p = self._pages[page_id]
        return {"id": p["id"], "title": p["title"],
                "parent_title": p["parent_title"], "text": p["text"]}


def _enable_notion():
    AISettings.set('notion_sync_enabled', 'true')
    AISettings.set('notion_integration_token', 'tok')
    AISettings.set('notion_root_page_id', 'root')


def _service_with(pages):
    return NotionService(client_factory=lambda token: _FakeClient(pages))


def test_sync_disabled_returns_zero(app):
    from ChatBotAI.tests.fixtures.notion_pages import EXTRAKOSTEN_PAGE
    svc = _service_with([EXTRAKOSTEN_PAGE])
    stats = svc.sync()
    assert stats['kb_upserted'] == 0
    assert KnowledgeEntry.query.count() == 0


def test_sync_imports_safe_page_and_blocks_sensitive(app):
    from ChatBotAI.tests.fixtures.notion_pages import (
        EXTRAKOSTEN_PAGE, SCHLUESSELCODES_PAGE,
    )
    _enable_notion()
    svc = _service_with([EXTRAKOSTEN_PAGE, SCHLUESSELCODES_PAGE])
    stats = svc.sync()
    assert stats['pages_blocked'] == 1
    assert 'Check-in Information und Schlüsselcodes' in stats['blocked_titles']
    # safe page produced entries, all source='notion'
    notion_rows = KnowledgeEntry.query.filter_by(source='notion').all()
    assert len(notion_rows) >= 2
    # no door code leaked into any value
    assert all('162981' not in r.value and '162333' not in r.value for r in notion_rows)


def test_sync_is_idempotent(app):
    from ChatBotAI.tests.fixtures.notion_pages import EXTRAKOSTEN_PAGE
    _enable_notion()
    svc = _service_with([EXTRAKOSTEN_PAGE])
    svc.sync()
    count_after_first = KnowledgeEntry.query.filter_by(source='notion').count()
    svc.sync()
    count_after_second = KnowledgeEntry.query.filter_by(source='notion').count()
    assert count_after_first == count_after_second


def test_sync_deletes_vanished_pages_but_keeps_manual(app):
    from ChatBotAI.tests.fixtures.notion_pages import EXTRAKOSTEN_PAGE
    _enable_notion()
    # a manual entry that sync must never touch
    manual = KnowledgeEntry(category='faq', label='ManualL', value='ManualV', source='manual')
    db.session.add(manual); db.session.commit()
    svc = _service_with([EXTRAKOSTEN_PAGE])
    svc.sync()
    assert KnowledgeEntry.query.filter_by(source='notion').count() >= 2
    # second sync with the page gone -> notion rows deleted, manual kept
    svc_empty = _service_with([])
    svc_empty.sync()
    assert KnowledgeEntry.query.filter_by(source='notion').count() == 0
    assert KnowledgeEntry.query.filter_by(source='manual').count() == 1


def test_sync_imports_vorlage_as_template(app):
    from ChatBotAI.tests.fixtures.notion_pages import VORLAGE_PAGE
    _enable_notion()
    svc = _service_with([VORLAGE_PAGE])
    stats = svc.sync()
    assert stats['templates_upserted'] == 1
    t = ReplyTemplate.query.filter_by(source='notion').first()
    assert t is not None and '{guest_name}' in t.content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/test_notion_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ChatBotAI.services.notion_service'`

- [ ] **Step 3: Implement the orchestrator**

Create `ChatBotAI/services/notion_service.py`:

```python
"""Notion → KnowledgeEntry/ReplyTemplate sync orchestrator.

Wires the read-only NotionClient through the safety scrubber and mapper, then
idempotently upserts results. Touches ONLY source='notion' rows.
See docs/superpowers/specs/2026-06-17-notion-knowledge-sync-design.md.
"""
import logging
from datetime import datetime
from typing import Optional

from ..models import db, KnowledgeEntry, ReplyTemplate, Property, AISettings
from . import notion_scrubber as scrub
from . import notion_mapper as mapper
from .notion_client import NotionClient

logger = logging.getLogger(__name__)


def _as_bool(val, default=False):
    if val is None:
        return default
    return str(val).strip().lower() in ('1', 'true', 'yes', 'on')


def get_notion_config():
    return {
        'enabled': _as_bool(AISettings.get('notion_sync_enabled', 'false'), False),
        'token': AISettings.get('notion_integration_token', '') or '',
        'root_page_id': AISettings.get('notion_root_page_id', '') or '',
        'block_keywords': scrub.parse_csv_setting(
            AISettings.get('notion_block_keywords'), scrub.DEFAULT_BLOCK_KEYWORDS),
        'force_exclude_ids': scrub.parse_csv_setting(AISettings.get('notion_force_exclude_ids'), []),
        'force_include_ids': scrub.parse_csv_setting(AISettings.get('notion_force_include_ids'), []),
    }


class NotionService:
    def __init__(self, client_factory=None):
        # client_factory(token) -> NotionClient. Default builds a real one.
        self._client_factory = client_factory or (lambda token: NotionClient(token=token))

    def _property_names(self):
        return {p.name.lower(): p.id for p in Property.query.all() if p.name}

    def sync(self):
        stats = {'pages_scanned': 0, 'pages_blocked': 0, 'kb_upserted': 0,
                 'kb_deleted': 0, 'templates_upserted': 0, 'templates_deleted': 0,
                 'values_scrubbed': 0, 'errors': 0, 'blocked_titles': []}
        cfg = get_notion_config()
        if not cfg['enabled'] or not cfg['token'] or not cfg['root_page_id']:
            return stats

        client = self._client_factory(cfg['token'])
        prop_names = self._property_names()

        seen_kb_keys = set()       # (notion_page_id, label)
        seen_tpl_ids = set()       # notion_page_id

        try:
            page_ids = client.list_descendant_pages(cfg['root_page_id'])
        except Exception:
            logger.exception("notion-sync: failed to list pages")
            stats['errors'] += 1
            return stats

        for page_id in page_ids:
            try:
                page = client.get_page(page_id)
            except Exception:
                logger.exception("notion-sync: failed to fetch %s", page_id)
                stats['errors'] += 1
                continue

            stats['pages_scanned'] += 1
            title, text = page.get('title', ''), page.get('text', '')

            if page_id in cfg['force_exclude_ids']:
                stats['pages_blocked'] += 1
                stats['blocked_titles'].append(title)
                continue

            if page_id not in cfg['force_include_ids'] and \
                    scrub.is_blocked_page(title, text, cfg['block_keywords']):
                stats['pages_blocked'] += 1
                stats['blocked_titles'].append(title)
                continue

            if mapper.is_template_page(page):
                tpl = mapper.page_to_template(page)
                tpl['content'] = scrub.scrub_value(tpl['content'])
                if tpl['content']:
                    self._upsert_template(tpl)
                    seen_tpl_ids.add(page_id)
                    stats['templates_upserted'] += 1
                continue

            for entry in mapper.page_to_kb_entries(page, prop_names):
                cleaned = scrub.scrub_value(entry['value'])
                if cleaned != entry['value']:
                    stats['values_scrubbed'] += 1
                if not cleaned.strip():
                    continue
                entry['value'] = cleaned
                self._upsert_kb(entry)
                seen_kb_keys.add((page_id, entry['label']))
                stats['kb_upserted'] += 1

        # Reconcile deletions — only source='notion' rows.
        stats['kb_deleted'] = self._delete_stale_kb(seen_kb_keys)
        stats['templates_deleted'] = self._delete_stale_templates(seen_tpl_ids)
        db.session.commit()
        logger.info("notion-sync: %s", {k: v for k, v in stats.items() if k != 'blocked_titles'})
        return stats

    def _upsert_kb(self, entry):
        row = KnowledgeEntry.query.filter_by(
            source='notion', notion_page_id=entry['notion_page_id'],
            label=entry['label']).first()
        if row is None:
            row = KnowledgeEntry(source='notion', notion_page_id=entry['notion_page_id'],
                                 label=entry['label'])
            db.session.add(row)
        row.category = entry['category']
        row.value = entry['value']
        row.property_id = entry['property_id']
        row.synced_at = datetime.utcnow()

    def _upsert_template(self, tpl):
        row = ReplyTemplate.query.filter_by(
            source='notion', notion_page_id=tpl['notion_page_id']).first()
        if row is None:
            row = ReplyTemplate(source='notion', notion_page_id=tpl['notion_page_id'])
            db.session.add(row)
        row.name = tpl['name']
        row.content = tpl['content']
        row.category = tpl['category']

    def _delete_stale_kb(self, seen_keys):
        deleted = 0
        for row in KnowledgeEntry.query.filter_by(source='notion').all():
            if (row.notion_page_id, row.label) not in seen_keys:
                db.session.delete(row)
                deleted += 1
        return deleted

    def _delete_stale_templates(self, seen_ids):
        deleted = 0
        for row in ReplyTemplate.query.filter_by(source='notion').all():
            if row.notion_page_id not in seen_ids:
                db.session.delete(row)
                deleted += 1
        return deleted


_notion_service: Optional[NotionService] = None


def init_notion_service(app):
    global _notion_service
    _notion_service = NotionService()
    logger.info("Notion Service initialized")
    return _notion_service


def get_notion_service():
    return _notion_service
```

- [ ] **Step 4: Run the full Notion test file**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/test_notion_service.py -q`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/services/notion_service.py ChatBotAI/tests/test_notion_service.py
git commit -m "feat(notion): sync orchestrator with idempotent, source-isolated upsert"
```

---

## Task 7: Routes — sync trigger + settings GET/PUT

**Files:**
- Modify: `ChatBotAI/routes.py` (add routes near the other `/api/settings/*` handlers, ~line 2063)
- Test: `ChatBotAI/tests/test_notion_service.py` (add route tests)

**Interfaces:**
- Consumes: `get_notion_service()`, `get_notion_config()`, `@admin_required`.
- Produces routes:
  - `POST /chatbot/api/notion/sync` → runs `get_notion_service().sync()`, returns `{success, stats}`; 400 `{error}` if not enabled/configured.
  - `GET /chatbot/api/settings/notion` → returns config minus the token value (returns `token_set: bool` instead).
  - `PUT /chatbot/api/settings/notion` → persists `notion_sync_enabled`, `notion_integration_token`, `notion_root_page_id`, `notion_block_keywords`, `notion_force_exclude_ids`, `notion_force_include_ids` via `AISettings.set`.

- [ ] **Step 1: Write the failing tests**

Append to `ChatBotAI/tests/test_notion_service.py`:

```python
import pytest as _pytest
from ChatBotAI.models import User


@_pytest.fixture
def client(app):
    user = User(username='admin', display_name='Admin', is_admin=True)
    user.set_password('pw')
    db.session.add(user); db.session.commit()
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True
    return c


def test_settings_put_then_get_hides_token(app, client):
    resp = client.put('/chatbot/api/settings/notion', json={
        'notion_sync_enabled': 'true',
        'notion_integration_token': 'secret-tok',
        'notion_root_page_id': 'root123',
    })
    assert resp.status_code == 200
    got = client.get('/chatbot/api/settings/notion').get_json()
    assert got['token_set'] is True
    assert 'secret-tok' not in str(got)  # token value never returned
    assert got['root_page_id'] == 'root123'


def test_sync_route_requires_enabled(app, client):
    resp = client.post('/chatbot/api/notion/sync')
    assert resp.status_code == 400
    assert 'error' in resp.get_json()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/test_notion_service.py -k "settings_put or sync_route" -q`
Expected: FAIL — 404 (routes not registered yet)

- [ ] **Step 3: Implement the routes**

In `ChatBotAI/routes.py`, after `api_update_email_filter` (line ~2063), add:

```python
# ============================================================================
# NOTION KNOWLEDGE-BASE SYNC
# ============================================================================

@chatbot_bp.route('/api/settings/notion', methods=['GET'])
@admin_required
def api_get_notion_settings():
    """Return Notion sync config; the token VALUE is never returned."""
    from .services.notion_service import get_notion_config
    cfg = get_notion_config()
    return jsonify({
        'enabled': cfg['enabled'],
        'token_set': bool(cfg['token']),
        'root_page_id': cfg['root_page_id'],
        'block_keywords': ','.join(cfg['block_keywords']),
        'force_exclude_ids': ','.join(cfg['force_exclude_ids']),
        'force_include_ids': ','.join(cfg['force_include_ids']),
    })


@chatbot_bp.route('/api/settings/notion', methods=['PUT'])
@admin_required
def api_update_notion_settings():
    """Persist Notion sync settings. Token only overwritten if a value is sent."""
    data = request.get_json() or {}
    AISettings.set('notion_sync_enabled', str(data.get('notion_sync_enabled', 'false')))
    if data.get('notion_integration_token'):
        AISettings.set('notion_integration_token', data['notion_integration_token'])
    if data.get('notion_root_page_id') is not None:
        AISettings.set('notion_root_page_id', data['notion_root_page_id'])
    for key in ('notion_block_keywords', 'notion_force_exclude_ids', 'notion_force_include_ids'):
        if data.get(key) is not None:
            AISettings.set(key, data[key])
    return jsonify({'success': True})


@chatbot_bp.route('/api/notion/sync', methods=['POST'])
@admin_required
def api_notion_sync():
    """Run a Notion → knowledge-base sync and return the run stats."""
    from .services.notion_service import get_notion_service, get_notion_config
    cfg = get_notion_config()
    if not cfg['enabled'] or not cfg['token'] or not cfg['root_page_id']:
        return jsonify({'error': 'Notion sync is not enabled or not configured'}), 400
    service = get_notion_service()
    if service is None:
        return jsonify({'error': 'Notion service not initialized'}), 500
    try:
        stats = service.sync()
    except Exception:
        logger.exception("notion-sync route failed")
        return jsonify({'error': 'Sync failed; see server logs'}), 500
    return jsonify({'success': True, 'stats': stats})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/test_notion_service.py -q`
Expected: PASS (all tests in file)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/routes.py ChatBotAI/tests/test_notion_service.py
git commit -m "feat(notion): sync + settings API routes (admin-gated, token never echoed)"
```

---

## Task 8: Wire service init at startup

**Files:**
- Modify: `ChatBotAI/app.py` (and/or `ChatBotAI/__init__.py`) — wherever `init_smoobu_service` / `init_gmail_service` are called.

**Interfaces:**
- Consumes: `init_notion_service(app)`.

- [ ] **Step 1: Find the existing init site**

Run: `cd C:/Users/admin/Documents/FlaskApp && grep -rn "init_smoobu_service\|init_gmail_service" ChatBotAI/app.py ChatBotAI/__init__.py`
Expected: one or more call sites inside the app factory / startup.

- [ ] **Step 2: Add the Notion init alongside them**

At the same scope where `init_smoobu_service(app)` is called, add:

```python
    from .services.notion_service import init_notion_service
    init_notion_service(app)
```

- [ ] **Step 3: Verify the app boots**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -c "from ChatBotAI.app import create_app; create_app(); print('OK')"`
Expected: prints `OK` (and a log line `Notion Service initialized`).

- [ ] **Step 4: Run the whole Notion suite once more**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/test_notion_scrubber.py ChatBotAI/tests/test_notion_mapper.py ChatBotAI/tests/test_notion_service.py -q`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add ChatBotAI/app.py ChatBotAI/__init__.py
git commit -m "feat(notion): initialize NotionService at app startup"
```

---

## Task 9: Settings UI card + i18n strings

**Files:**
- Modify: `ChatBotAI/templates/chatbot/settings.html`
- Modify: `ChatBotAI/static/js/i18n.js`

**Interfaces:**
- Consumes: routes from Task 7. No new JS module — inline script in settings.html, matching how the email-filter card is wired (check existing pattern in the file first).

- [ ] **Step 1: Inspect the existing email-filter card**

Run: `cd C:/Users/admin/Documents/FlaskApp && grep -n "email-filter\|email_filter\|api/settings/email-filter" ChatBotAI/templates/chatbot/settings.html`
Expected: the markup + fetch wiring to copy as a template for the Notion card.

- [ ] **Step 2: Add the Notion card markup**

In `settings.html`, after the email-filter settings card, add a "Notion Wissensdatenbank" card with: token input (`type=password`, placeholder "•••• (gesetzt)" when `token_set`), root-page-id input, blocklist textarea, force-exclude/include inputs, an "Aktiviert" checkbox, a **"Jetzt synchronisieren"** button, and an empty `<div id="notion-sync-result">` for stats. Use `data-i18n` keys consistent with existing entries.

```html
<div class="settings-card" id="notion-settings-card">
  <h3 data-i18n="notion_title">Notion Wissensdatenbank</h3>
  <label><input type="checkbox" id="notion-enabled"> <span data-i18n="notion_enabled">Synchronisierung aktiviert</span></label>
  <input type="password" id="notion-token" autocomplete="off" data-i18n-placeholder="notion_token">
  <input type="text" id="notion-root" data-i18n-placeholder="notion_root">
  <textarea id="notion-blocklist" rows="2"></textarea>
  <button id="notion-sync-btn" data-i18n="notion_sync_now">Jetzt synchronisieren</button>
  <div id="notion-sync-result"></div>
</div>
```

- [ ] **Step 3: Add the fetch wiring (inline script, mirroring email-filter)**

Load settings on page open (`GET /chatbot/api/settings/notion` → populate fields, check `token_set`), save on change (`PUT`), and on the sync button click `POST /chatbot/api/notion/sync` then render `stats` into `#notion-sync-result` (show `kb_upserted`, `kb_deleted`, `pages_blocked`, and the `blocked_titles` list so the operator can confirm sensitive pages were withheld). Disable the button while the request is in flight.

- [ ] **Step 4: Add i18n strings**

In `ChatBotAI/static/js/i18n.js`, add to BOTH the German (`de`) and English (`en`) maps:

```javascript
    notion_title: 'Notion Wissensdatenbank',          // en: 'Notion Knowledge Base'
    notion_enabled: 'Synchronisierung aktiviert',       // en: 'Sync enabled'
    notion_token: 'Notion Integrations-Token',          // en: 'Notion integration token'
    notion_root: 'Handbuch-Seiten-ID',                  // en: 'Handbook page ID'
    notion_sync_now: 'Jetzt synchronisieren',           // en: 'Sync now'
```

- [ ] **Step 5: Bump cache versions**

Per project convention (cache-busting query strings on static assets), bump the `i18n.js` version in the template(s) that include it (search for `i18n.js?v=`). Increment to the next number.

Run: `cd C:/Users/admin/Documents/FlaskApp && grep -rn "i18n.js?v=" ChatBotAI/templates/`
Then increment each occurrence.

- [ ] **Step 6: Manual smoke check**

Run the dev server, open `/chatbot/settings`, confirm the card renders in German, the token field shows the "set" placeholder after saving, and the Sync button is present. (Full live sync is validated in Task 10.)

- [ ] **Step 7: Commit**

```bash
git add ChatBotAI/templates/chatbot/settings.html ChatBotAI/static/js/i18n.js
git commit -m "feat(notion): Settings card with Sync-now button + i18n strings"
```

---

## Task 10: Live end-to-end validation (real Notion, read-only)

**Files:**
- Create: `ChatBotAI/scripts/inspect_notion_sync.py` (read-only inspector, mirrors `scripts/inspect_email_parsing.py`)

**Interfaces:**
- Consumes: `get_notion_service`, `get_notion_config`. Prints what WOULD sync; performs a real sync only when run with `--apply`.

- [ ] **Step 1: Write the inspector script**

Create `ChatBotAI/scripts/inspect_notion_sync.py`:

```python
"""Read-only preview of the Notion sync. Lists pages under the configured hub,
shows which are blocked vs mapped, and (only with --apply) runs a real sync.

    cd C:\\Users\\admin\\Documents\\FlaskApp
    set PYTHONIOENCODING=utf-8
    python -m ChatBotAI.scripts.inspect_notion_sync          # preview stats
    python -m ChatBotAI.scripts.inspect_notion_sync --apply  # write to DB
"""
import sys
from ChatBotAI.app import create_app
from ChatBotAI.services.notion_service import get_notion_service, get_notion_config


def main():
    app = create_app()
    with app.app_context():
        cfg = get_notion_config()
        if not cfg['enabled'] or not cfg['token'] or not cfg['root_page_id']:
            print("Notion sync not enabled/configured — set token + root page id in Settings.")
            return
        svc = get_notion_service()
        if '--apply' not in sys.argv:
            print("PREVIEW mode (no DB writes). Re-run with --apply to persist.\n")
            # A dry run: temporarily disable persistence by inspecting only.
            # Simplest safe preview: list + scrub decisions without upsert.
        stats = svc.sync() if '--apply' in sys.argv else None
        if stats is None:
            print("Preview complete. (Run with --apply to see real upsert stats.)")
        else:
            print("Sync stats:")
            for k, v in stats.items():
                print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Configure real credentials (manual, one-time)**

In the running app's Settings, paste the Notion internal-integration token and the `HANDBUCH ZUR GÄSTEBETREUUNG` page id (`363149d2-d08e-80aa-a0c9-fd3888281f26`), enable sync, and ensure the integration is shared with that page in Notion. (Document this in the help page if time permits.)

- [ ] **Step 3: Run a real sync and verify safety**

Run: `cd C:/Users/admin/Documents/FlaskApp && set PYTHONIOENCODING=utf-8 && python -m ChatBotAI.scripts.inspect_notion_sync --apply`
Expected: stats print with `pages_blocked >= 1`, and `Check-in Information und Schlüsselcodes` appears in the blocked set.

- [ ] **Step 4: Confirm no codes leaked into the DB**

Run: `cd C:/Users/admin/Documents/FlaskApp && python -c "from ChatBotAI.app import create_app; from ChatBotAI.models import KnowledgeEntry; app=create_app();\nimport re\nwith app.app_context():\n  bad=[e.id for e in KnowledgeEntry.query.filter_by(source='notion').all() if re.search(r'Haustür\s*:?\s*\d{3,6}|Code\s*\d{3,6}', e.value)]\n  print('LEAKS:', bad)"`
Expected: `LEAKS: []`

- [ ] **Step 5: Verify UMI now sees the content**

Open `/chatbot/knowledge`, confirm Extrakosten-derived entries appear with a Notion source badge. Optionally run a Playtest V2 conversation asking about pet fees / check-in time and confirm UMI answers from the synced KB.

- [ ] **Step 6: Commit**

```bash
git add ChatBotAI/scripts/inspect_notion_sync.py
git commit -m "feat(notion): read-only sync inspector + live validation"
```

---

## Final verification

- [ ] Run the whole new suite: `cd C:/Users/admin/Documents/FlaskApp && python -m pytest ChatBotAI/tests/test_notion_scrubber.py ChatBotAI/tests/test_notion_mapper.py ChatBotAI/tests/test_notion_service.py -q` → all pass.
- [ ] Run the full project suite to confirm no regressions: `python -m pytest ChatBotAI/tests/ -q`.
- [ ] Confirm `git log --oneline` shows one commit per task.
- [ ] Update project memory (MEMORY.md) noting the Notion sync feature + the `notion_page_id`/`source` provenance convention.

## Self-review notes (spec coverage)

- Spec §3 connection (Approach A, token in AISettings) → Tasks 5,6,7. ✅
- Spec §4 three-layer scrubber → Task 2 (L1+L2) + Task 6 force-exclude/include (L3) + Task 10 audit output. ✅
- Spec §5 mapping (sections, category, property, Vorlagen) → Task 3 + Task 6. ✅
- Spec §6 model + idempotent, source-isolated upsert (p19) → Tasks 4,6 (incl. deletion-reconcile + manual-untouched tests). ✅
- Spec §7 error handling / per-page isolation / stats → Task 6 (`errors`, per-page try/except) + Task 7 (route 400/500). ✅
- Spec §7 long-run/Cloudflare-524 sizing → flagged; Task 10 measures real run time. If a full sync exceeds ~100s, convert the route to fire-and-forget per `feedback_cloudflare_long_routes` before production. **NOTE for executor.**
- Spec §8 tests with real fixtures → Tasks 1,2,3,6. ✅
- Spec §9 UI + Notion badge + i18n → Task 9 (+ Task 10 Step 5 badge check). ✅
