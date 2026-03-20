# Knowledge Base Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Knowledge Base system for storing structured facts (WiFi, check-in, nearby places) that the AI includes when responding to guests.

**Architecture:** New `KnowledgeEntry` model with optional property FK. Separate page at `/chatbot/knowledge` for CRUD management. AI context loading in all three response code paths (message_router auto-respond, routes generate, routes suggest). Formatted entries injected into system prompt.

**Tech Stack:** Flask, SQLAlchemy, Alembic, Jinja2, vanilla JS, Ollama chat API

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `models.py` | Modify | Add `KnowledgeEntry` model |
| `migrations/versions/p6_knowledge_add_knowledge_entry.py` | Create | DB migration |
| `routes.py` | Modify | Page route + 4 API routes + knowledge loading in 2 existing AI routes (3rd path is in message_router) |
| `services/message_router.py` | Modify | Knowledge loading in `_generate_ai_response` |
| `services/ai_service.py` | Modify | `knowledge_entries` param + `_format_knowledge_entries()` |
| `templates/chatbot/knowledge.html` | Create | Knowledge Base page template |
| `templates/chatbot/base.html` | Modify | Sidebar nav entry |
| `templates/chatbot/settings.html` | Modify | Link note below Host Instructions |
| `static/js/knowledge.js` | Create | CRUD + filter + modal logic |
| `static/js/i18n.js` | Modify | New i18n keys |

---

### Task 1: Database Model + Migration

**Files:**
- Modify: `models.py` (add after `AISettings` class, ~line 469, before `preload_last_messages`)
- Create: `migrations/versions/p6_knowledge_add_knowledge_entry.py`

- [ ] **Step 1: Add KnowledgeEntry model to models.py**

Add after the `AISettings` class (around line 469, before `preload_last_messages`):

```python
class KnowledgeEntry(db.Model):
    """
    Structured facts for AI context.
    Stores host knowledge (WiFi, check-in procedures, nearby places, etc.)
    that the AI references when responding to guests.
    Entries can be global (property_id=NULL) or per-property.
    """
    __tablename__ = 'knowledge_entry'

    VALID_CATEGORIES = [
        'general', 'checkin_checkout', 'nearby',
        'house_rules', 'emergency', 'faq'
    ]

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('property.id', ondelete='CASCADE'), nullable=True, index=True)
    category = db.Column(db.String(50), nullable=False)
    label = db.Column(db.String(200), nullable=False)
    value = db.Column(db.Text, nullable=False)
    sort_order = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Composite index for AI context queries
    __table_args__ = (
        db.Index('ix_knowledge_entry_property_category', 'property_id', 'category'),
    )

    # Relationship
    property = db.relationship('Property', backref=db.backref('knowledge_entries', cascade='all, delete-orphan', lazy='dynamic'))

    def __repr__(self):
        scope = f'property={self.property_id}' if self.property_id else 'global'
        return f'<KnowledgeEntry {self.id}: [{self.category}] {self.label} ({scope})>'

    def to_dict(self):
        return {
            'id': self.id,
            'property_id': self.property_id,
            'property_name': self.property.name if self.property else None,
            'category': self.category,
            'label': self.label,
            'value': self.value,
            'sort_order': self.sort_order,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
```

- [ ] **Step 2: Create migration file**

Create `migrations/versions/p6_knowledge_add_knowledge_entry.py`:

```python
"""Add knowledge_entry table for AI knowledge base

Revision ID: p6_knowledge
Revises: p5_perf_idx2
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'p6_knowledge'
down_revision = 'p5_perf_idx2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'knowledge_entry',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('property_id', sa.Integer(), sa.ForeignKey('property.id', ondelete='CASCADE'), nullable=True),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('label', sa.String(200), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_knowledge_entry_property_id', 'knowledge_entry', ['property_id'])
    op.create_index('ix_knowledge_entry_property_category', 'knowledge_entry', ['property_id', 'category'])


def downgrade():
    op.drop_index('ix_knowledge_entry_property_category', table_name='knowledge_entry')
    op.drop_index('ix_knowledge_entry_property_id', table_name='knowledge_entry')
    op.drop_table('knowledge_entry')
```

- [ ] **Step 3: Run migration**

```bash
cd C:/Users/admin/Documents/FlaskApp && python -m ChatBotAI.run db upgrade
```

If the app doesn't have a CLI db command, use Flask-Migrate directly or let `create_all()` handle it on next startup.

- [ ] **Step 4: Commit**

```bash
git add models.py migrations/versions/p6_knowledge_add_knowledge_entry.py
git commit -m "feat: add KnowledgeEntry model and migration"
```

---

### Task 2: AI Service — Format + Inject Knowledge

**Files:**
- Modify: `services/ai_service.py` (lines 408-450 and 495-696)

- [ ] **Step 1: Add `_format_knowledge_entries` method**

Add after `_format_reservation_info` (around line 879):

```python
@staticmethod
def _format_knowledge_entries(entries: List[Dict[str, Any]], max_chars: int = 2000) -> str:
    """Format knowledge base entries for the AI prompt, grouped by category.

    Args:
        entries: List of KnowledgeEntry.to_dict() dicts
        max_chars: Maximum characters for the formatted output

    Returns:
        Formatted string or empty string if no entries
    """
    if not entries:
        return ""

    CATEGORY_LABELS = {
        'general': 'General Info',
        'checkin_checkout': 'Check-in / Check-out',
        'nearby': 'Nearby Places',
        'house_rules': 'House Rules',
        'emergency': 'Emergency Contacts',
        'faq': 'FAQ',
    }

    # Group by category
    by_category = {}
    for entry in entries:
        cat = entry.get('category', 'general')
        by_category.setdefault(cat, []).append(entry)

    lines = []
    total_len = 0
    truncated = False

    for cat_key in ['general', 'checkin_checkout', 'nearby', 'house_rules', 'emergency', 'faq']:
        cat_entries = by_category.get(cat_key, [])
        if not cat_entries:
            continue

        header = f"[{CATEGORY_LABELS.get(cat_key, cat_key)}]"
        if total_len + len(header) + 1 > max_chars:
            truncated = True
            break

        lines.append(header)
        total_len += len(header) + 1

        for entry in cat_entries:
            line = f"- {entry['label']}: {entry['value']}"
            if total_len + len(line) + 1 > max_chars:
                truncated = True
                break
            lines.append(line)
            total_len += len(line) + 1

        if truncated:
            break
        lines.append("")  # blank line between categories

    if truncated:
        lines.append("(...additional entries omitted)")

    return "\n".join(lines).strip()
```

- [ ] **Step 2: Add `knowledge_entries` parameter to `generate_guest_response`**

Modify `generate_guest_response` signature (line 408) to add the new optional parameter:

```python
def generate_guest_response(
        self,
        guest_profile: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
        latest_message: str,
        property_info: Optional[Dict[str, Any]] = None,
        tone: Optional[str] = None,
        host_instructions: Optional[str] = None,
        conversation_subject: Optional[str] = None,
        max_history: int = 10,
        reservation_info: Optional[Dict[str, Any]] = None,
        knowledge_entries: Optional[List[Dict[str, Any]]] = None
) -> Optional[str]:
```

Pass it through to `_build_chat_messages` (around line 439):

```python
messages = self._build_chat_messages(
    guest_profile,
    conversation_history,
    latest_message,
    property_info,
    tone=tone,
    host_instructions=host_instructions,
    conversation_subject=conversation_subject,
    max_history=max_history,
    reservation_info=reservation_info,
    knowledge_entries=knowledge_entries
)
```

- [ ] **Step 3: Add `knowledge_entries` parameter to `_build_chat_messages`**

Modify signature (line 495) to accept:

```python
def _build_chat_messages(
        self,
        guest_profile: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
        latest_message: str,
        property_info: Optional[Dict[str, Any]],
        tone: Optional[str] = None,
        host_instructions: Optional[str] = None,
        conversation_subject: Optional[str] = None,
        max_history: int = 10,
        reservation_info: Optional[Dict[str, Any]] = None,
        knowledge_entries: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, str]]:
```

Add injection between reservation info and host instructions (after line 571, before line 573):

```python
if knowledge_entries:
    kb_text = self._format_knowledge_entries(knowledge_entries)
    if kb_text:
        system_parts.append(f"\n=== HOST KNOWLEDGE BASE ===\n{kb_text}\n===")
```

- [ ] **Step 4: Commit**

```bash
git add services/ai_service.py
git commit -m "feat: add knowledge entries formatting and injection in AI prompts"
```

---

### Task 3: Knowledge Loading in All AI Code Paths

**Files:**
- Modify: `services/message_router.py` (lines 405-467)
- Modify: `routes.py` (lines 539-612 and 685-770)

- [ ] **Step 1: Add knowledge loading in MessageRouter._generate_ai_response**

In `message_router.py`, add after the reservation_info block (around line 454) and before the `generate_guest_response` call:

Also add `KnowledgeEntry` to the top-level import in `message_router.py` (line 17):

```python
from ..models import db, Guest, Conversation, Message, Property, AISettings, KnowledgeEntry
```

Then add the loading code:

```python
# Load knowledge base entries for AI context
knowledge_entries = []
try:
    query = KnowledgeEntry.query.filter(
        db.or_(
            KnowledgeEntry.property_id.is_(None),
            KnowledgeEntry.property_id == conversation.property_id
        )
    ).order_by(KnowledgeEntry.category, KnowledgeEntry.sort_order)
    if conversation.property_id:
        knowledge_entries = [e.to_dict() for e in query.all()]
    else:
        # No property assigned — only global entries
        knowledge_entries = [e.to_dict() for e in
                            KnowledgeEntry.query.filter_by(property_id=None)
                            .order_by(KnowledgeEntry.category, KnowledgeEntry.sort_order).all()]
except Exception as e:
    logger.warning(f"Failed to load knowledge entries: {e}")
```

Then add `knowledge_entries=knowledge_entries` to the `generate_guest_response` call (line 457):

```python
response_text = self.ai_service.generate_guest_response(
    guest_profile=profile,
    conversation_history=[m.to_dict() for m in messages],
    latest_message=trigger_message.content,
    property_info=property_info,
    tone=tone,
    host_instructions=host_instructions,
    conversation_subject=conversation.subject,
    max_history=max_history,
    reservation_info=reservation_info,
    knowledge_entries=knowledge_entries
)
```

- [ ] **Step 2: Add knowledge loading in routes.py api_generate_ai_response**

In `routes.py`, add after the reservation_info block (around line 599) and before the `generate_guest_response` call (line 602):

```python
# Load knowledge base entries for AI context
knowledge_entries = []
try:
    knowledge_query = KnowledgeEntry.query.filter(
        db.or_(
            KnowledgeEntry.property_id.is_(None),
            KnowledgeEntry.property_id == conversation.property_id
        )
    ).order_by(KnowledgeEntry.category, KnowledgeEntry.sort_order)
    if conversation.property_id:
        knowledge_entries = [e.to_dict() for e in knowledge_query.all()]
    else:
        knowledge_entries = [e.to_dict() for e in
                            KnowledgeEntry.query.filter_by(property_id=None)
                            .order_by(KnowledgeEntry.category, KnowledgeEntry.sort_order).all()]
except Exception as e:
    logger.warning(f"Failed to load knowledge entries: {e}")
```

Add `knowledge_entries=knowledge_entries` to the `generate_guest_response` call at line 602.

Also add `KnowledgeEntry` to the imports at the top of `routes.py` (line ~12):

```python
from .models import db, Guest, GuestDetail, Conversation, Message, Property, AISettings, User, KnowledgeEntry
```

- [ ] **Step 3: Add knowledge loading in routes.py api_suggest_ai_response**

Same pattern in `api_suggest_ai_response` (around line 754), add after reservation_info block and before the `generate_guest_response` call. Same code as Step 2.

Add `knowledge_entries=knowledge_entries` to the `generate_guest_response` call.

- [ ] **Step 4: Commit**

```bash
git add services/message_router.py routes.py
git commit -m "feat: load knowledge entries in all three AI response code paths"
```

---

### Task 4: API Routes for Knowledge CRUD

**Files:**
- Modify: `routes.py` (add new routes at end of file, before any error handlers)

- [ ] **Step 1: Add GET /api/knowledge**

```python
@chatbot_bp.route('/api/knowledge')
def api_list_knowledge():
    """List knowledge entries with optional property filter"""
    property_filter = request.args.get('property_id')

    query = KnowledgeEntry.query

    if property_filter == 'global':
        query = query.filter_by(property_id=None)
    elif property_filter:
        try:
            pid = int(property_filter)
            query = query.filter_by(property_id=pid)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid property_id'}), 400

    entries = query.order_by(KnowledgeEntry.category, KnowledgeEntry.sort_order).all()
    return jsonify([e.to_dict() for e in entries])
```

- [ ] **Step 2: Add POST /api/knowledge**

```python
@chatbot_bp.route('/api/knowledge', methods=['POST'])
def api_create_knowledge():
    """Create a knowledge entry"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    category = data.get('category', '').strip()
    label = data.get('label', '').strip()
    value = data.get('value', '').strip()
    property_id = data.get('property_id')

    # Validation
    if category not in KnowledgeEntry.VALID_CATEGORIES:
        return jsonify({'error': f'Invalid category. Must be one of: {", ".join(KnowledgeEntry.VALID_CATEGORIES)}'}), 400
    if not label:
        return jsonify({'error': 'Label is required'}), 400
    if len(label) > 200:
        return jsonify({'error': 'Label must be 200 characters or less'}), 400
    if not value:
        return jsonify({'error': 'Value is required'}), 400
    if len(value) > 2000:
        return jsonify({'error': 'Value must be 2000 characters or less'}), 400

    if property_id is not None:
        prop = Property.query.get(property_id)
        if not prop:
            return jsonify({'error': 'Property not found'}), 400

    # Auto-increment sort_order
    max_order = db.session.query(db.func.max(KnowledgeEntry.sort_order)).filter_by(
        property_id=property_id, category=category
    ).scalar() or 0

    entry = KnowledgeEntry(
        property_id=property_id,
        category=category,
        label=label,
        value=value,
        sort_order=max_order + 1
    )
    db.session.add(entry)
    db.session.commit()

    return jsonify(entry.to_dict()), 201
```

- [ ] **Step 3: Add PUT /api/knowledge/<id>**

```python
@chatbot_bp.route('/api/knowledge/<int:entry_id>', methods=['PUT'])
def api_update_knowledge(entry_id):
    """Update a knowledge entry"""
    entry = KnowledgeEntry.query.get_or_404(entry_id)
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    if 'category' in data:
        category = data['category'].strip()
        if category not in KnowledgeEntry.VALID_CATEGORIES:
            return jsonify({'error': f'Invalid category'}), 400
        entry.category = category

    if 'label' in data:
        label = data['label'].strip()
        if not label:
            return jsonify({'error': 'Label is required'}), 400
        if len(label) > 200:
            return jsonify({'error': 'Label must be 200 characters or less'}), 400
        entry.label = label

    if 'value' in data:
        value = data['value'].strip()
        if not value:
            return jsonify({'error': 'Value is required'}), 400
        if len(value) > 2000:
            return jsonify({'error': 'Value must be 2000 characters or less'}), 400
        entry.value = value

    if 'property_id' in data:
        pid = data['property_id']
        if pid is not None:
            prop = Property.query.get(pid)
            if not prop:
                return jsonify({'error': 'Property not found'}), 400
        entry.property_id = pid

    if 'sort_order' in data:
        entry.sort_order = int(data['sort_order'])

    db.session.commit()
    return jsonify(entry.to_dict())
```

- [ ] **Step 4: Add DELETE /api/knowledge/<id>**

```python
@chatbot_bp.route('/api/knowledge/<int:entry_id>', methods=['DELETE'])
def api_delete_knowledge(entry_id):
    """Delete a knowledge entry"""
    entry = KnowledgeEntry.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    return jsonify({'success': True})
```

- [ ] **Step 5: Commit**

```bash
git add routes.py
git commit -m "feat: add Knowledge Base CRUD API routes"
```

---

### Task 5: Page Route + Template

**Files:**
- Modify: `routes.py` (add page route)
- Create: `templates/chatbot/knowledge.html`

- [ ] **Step 1: Add page route in routes.py**

Add near the other page routes (around line 100):

```python
@chatbot_bp.route('/knowledge')
def knowledge_base():
    """Knowledge Base management page"""
    properties = Property.query.order_by(Property.name).all()
    return render_template('chatbot/knowledge.html', properties=properties)
```

- [ ] **Step 2: Create knowledge.html template**

Create `templates/chatbot/knowledge.html` — full page with filter bar, entries list grouped by category, add/edit modal. Uses existing dark/light theme CSS variables and card layout. Extends `base.html`. Loads `knowledge.js` in `extra_js` block.

The template should include:
- Page header with title + Add button
- Property filter dropdown (All / Global / each property)
- Entries container (populated by JS)
- Add/Edit modal with scope radio (Global/Per Property), property dropdown, category dropdown, label input, value textarea
- Delete confirmation

```html
{% extends "chatbot/base.html" %}

{% block title %}{{ _('Knowledge Base') if _ else 'Wissensdatenbank' }}{% endblock %}

{% block content %}
<div class="settings-container">
    <div class="page-header">
        <h1><i class="fas fa-book"></i> <span data-i18n="knowledge.title">Wissensdatenbank</span></h1>
        <button class="btn btn-primary" onclick="knowledgeApp.openAddModal()">
            <i class="fas fa-plus"></i> <span data-i18n="knowledge.add">Eintrag hinzufügen</span>
        </button>
    </div>

    <!-- Filter Bar -->
    <div class="settings-card" style="margin-bottom: 20px;">
        <div class="card-body" style="padding: 15px;">
            <div style="display: flex; gap: 15px; align-items: center; flex-wrap: wrap;">
                <label data-i18n="knowledge.filter.property" style="font-weight: 500;">Unterkunft:</label>
                <select id="propertyFilter" class="setting-input" style="max-width: 300px;" onchange="knowledgeApp.loadEntries()">
                    <option value="" data-i18n="knowledge.filter.all">Alle</option>
                    <option value="global" data-i18n="knowledge.filter.global">Global</option>
                    {% for prop in properties %}
                    <option value="{{ prop.id }}">{{ prop.name }}</option>
                    {% endfor %}
                </select>
            </div>
        </div>
    </div>

    <!-- Entries Container -->
    <div id="entriesContainer">
        <div class="settings-card">
            <div class="card-body" style="text-align: center; padding: 40px; color: var(--text-secondary);">
                <i class="fas fa-spinner fa-spin" style="font-size: 24px;"></i>
                <p data-i18n="knowledge.loading">Lade Einträge...</p>
            </div>
        </div>
    </div>
</div>

<!-- Add/Edit Modal (uses existing dialog.edit-modal pattern) -->
<dialog id="knowledgeModal" class="edit-modal" style="max-width: 500px;" aria-labelledby="modalTitle">
    <div class="modal-header">
        <h2 id="modalTitle" data-i18n="knowledge.add">Eintrag hinzufügen</h2>
        <button class="btn-close" onclick="knowledgeApp.closeModal()" aria-label="Close">&times;</button>
    </div>
    <div class="modal-body">
        <form id="knowledgeForm" onsubmit="return knowledgeApp.saveEntry(event)">
            <input type="hidden" id="entryId" value="">

            <div class="setting-item" style="flex-direction: column; align-items: flex-start;">
                <label data-i18n="knowledge.scope">Geltungsbereich</label>
                <div style="display: flex; gap: 15px; margin-top: 5px;">
                    <label style="display: flex; align-items: center; gap: 5px; cursor: pointer;">
                        <input type="radio" name="scope" value="global" checked onchange="knowledgeApp.toggleScope()">
                        <span data-i18n="knowledge.scope.global">Global</span>
                    </label>
                    <label style="display: flex; align-items: center; gap: 5px; cursor: pointer;">
                        <input type="radio" name="scope" value="property" onchange="knowledgeApp.toggleScope()">
                        <span data-i18n="knowledge.scope.property">Pro Unterkunft</span>
                    </label>
                </div>
            </div>

            <div class="setting-item" id="propertySelectRow" style="flex-direction: column; align-items: flex-start; display: none;">
                <label for="entryPropertyId" data-i18n="knowledge.property">Unterkunft</label>
                <select id="entryPropertyId" class="setting-input" style="width: 100%;">
                    {% for prop in properties %}
                    <option value="{{ prop.id }}">{{ prop.name }}</option>
                    {% endfor %}
                </select>
            </div>

            <div class="setting-item" style="flex-direction: column; align-items: flex-start;">
                <label for="entryCategory" data-i18n="knowledge.category">Kategorie</label>
                <select id="entryCategory" class="setting-input" style="width: 100%;">
                    <option value="general" data-i18n="knowledge.cat.general">Allgemeine Infos</option>
                    <option value="checkin_checkout" data-i18n="knowledge.cat.checkin">Check-in / Check-out</option>
                    <option value="nearby" data-i18n="knowledge.cat.nearby">In der Nähe</option>
                    <option value="house_rules" data-i18n="knowledge.cat.rules">Hausregeln</option>
                    <option value="emergency" data-i18n="knowledge.cat.emergency">Notfallkontakte</option>
                    <option value="faq" data-i18n="knowledge.cat.faq">Häufige Fragen</option>
                </select>
            </div>

            <div class="setting-item" style="flex-direction: column; align-items: flex-start;">
                <label for="entryLabel" data-i18n="knowledge.label">Bezeichnung</label>
                <input type="text" id="entryLabel" class="setting-input" style="width: 100%;"
                    data-i18n-placeholder="knowledge.label.placeholder" placeholder="z.B. WLAN-Passwort" required maxlength="200">
            </div>

            <div class="setting-item" style="flex-direction: column; align-items: flex-start;">
                <label for="entryValue" data-i18n="knowledge.value">Information</label>
                <textarea id="entryValue" class="setting-textarea" rows="4" style="width: 100%;"
                    data-i18n-placeholder="knowledge.value.placeholder" placeholder="z.B. SunnyBeach2024" required maxlength="2000"></textarea>
            </div>

            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" onclick="knowledgeApp.closeModal()" data-i18n="knowledge.cancel">Abbrechen</button>
                <button type="submit" class="btn btn-primary" data-i18n="knowledge.save">Speichern</button>
            </div>
        </form>
    </div>
</dialog>
{% endblock %}

{% block extra_js %}
<script src="{{ url_for('chatbot.static', filename='js/knowledge.js') }}?v=1"></script>
{% endblock %}
```

- [ ] **Step 3: Commit**

```bash
git add routes.py templates/chatbot/knowledge.html
git commit -m "feat: add Knowledge Base page route and template"
```

---

### Task 6: JavaScript — Knowledge Base Logic

**Files:**
- Create: `static/js/knowledge.js`

- [ ] **Step 1: Create knowledge.js**

```javascript
/**
 * Knowledge Base management
 * CRUD operations, property filtering, category grouping
 */

const CATEGORY_LABELS = {
    general: { de: 'Allgemeine Infos', en: 'General Info' },
    checkin_checkout: { de: 'Check-in / Check-out', en: 'Check-in / Check-out' },
    nearby: { de: 'In der Nähe', en: 'Nearby Places' },
    house_rules: { de: 'Hausregeln', en: 'House Rules' },
    emergency: { de: 'Notfallkontakte', en: 'Emergency Contacts' },
    faq: { de: 'Häufige Fragen', en: 'FAQ / Common Questions' },
};

const CATEGORY_ICONS = {
    general: 'fa-info-circle',
    checkin_checkout: 'fa-key',
    nearby: 'fa-map-marker-alt',
    house_rules: 'fa-clipboard-list',
    emergency: 'fa-phone-alt',
    faq: 'fa-question-circle',
};

const CATEGORY_ORDER = ['general', 'checkin_checkout', 'nearby', 'house_rules', 'emergency', 'faq'];

const knowledgeApp = {
    entries: [],

    async loadEntries() {
        const filter = document.getElementById('propertyFilter').value;
        let url = '/chatbot/api/knowledge';
        if (filter) url += `?property_id=${encodeURIComponent(filter)}`;

        try {
            const resp = await fetch(url);
            if (!resp.ok) throw new Error('Failed to load');
            this.entries = await resp.json();
            this.renderEntries();
        } catch (e) {
            console.error('Failed to load knowledge entries:', e);
            document.getElementById('entriesContainer').innerHTML =
                '<div class="settings-card"><div class="card-body" style="text-align:center;padding:40px;color:var(--text-secondary);">' +
                '<i class="fas fa-exclamation-triangle" style="font-size:24px;color:var(--danger-color);"></i>' +
                '<p>' + (typeof i18n !== 'undefined' ? i18n.t('knowledge.error.load') : 'Fehler beim Laden') + '</p></div></div>';
        }
    },

    renderEntries() {
        const container = document.getElementById('entriesContainer');
        const lang = (typeof i18n !== 'undefined' && i18n.currentLanguage) || 'de';

        if (!this.entries.length) {
            container.innerHTML =
                '<div class="settings-card"><div class="card-body" style="text-align:center;padding:40px;color:var(--text-secondary);">' +
                '<i class="fas fa-book-open" style="font-size:48px;margin-bottom:15px;opacity:0.3;"></i>' +
                '<p style="font-size:16px;">' + (typeof i18n !== 'undefined' ? i18n.t('knowledge.empty') : 'Noch keine Einträge vorhanden') + '</p>' +
                '<p style="font-size:14px;opacity:0.7;">' + (typeof i18n !== 'undefined' ? i18n.t('knowledge.empty.hint') : 'Fügen Sie Fakten hinzu, die die KI bei Gästeanfragen nutzen soll.') + '</p></div></div>';
            return;
        }

        // Group by category
        const grouped = {};
        for (const entry of this.entries) {
            const cat = entry.category || 'general';
            if (!grouped[cat]) grouped[cat] = [];
            grouped[cat].push(entry);
        }

        let html = '';
        for (const cat of CATEGORY_ORDER) {
            const entries = grouped[cat];
            if (!entries || !entries.length) continue;

            const catLabel = CATEGORY_LABELS[cat] ? CATEGORY_LABELS[cat][lang] || CATEGORY_LABELS[cat].de : cat;
            const catIcon = CATEGORY_ICONS[cat] || 'fa-folder';

            html += '<div class="settings-card" style="margin-bottom: 15px;">';
            html += '<div class="card-header"><h2><i class="fas ' + catIcon + '"></i> ' + this.escapeHtml(catLabel) + '</h2></div>';
            html += '<div class="card-body" style="padding: 0;">';

            for (const entry of entries) {
                const scopeBadge = entry.property_name
                    ? '<span class="badge" style="background:var(--primary-color);color:white;padding:2px 8px;border-radius:10px;font-size:11px;margin-left:8px;">' + this.escapeHtml(entry.property_name) + '</span>'
                    : '<span class="badge" style="background:var(--text-secondary);color:white;padding:2px 8px;border-radius:10px;font-size:11px;margin-left:8px;">Global</span>';

                html += '<div class="setting-item" style="padding: 12px 20px; border-bottom: 1px solid var(--border-color);">';
                html += '<div style="flex: 1; min-width: 0;">';
                html += '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:5px;">';
                html += '<strong>' + this.escapeHtml(entry.label) + '</strong>' + scopeBadge;
                html += '</div>';
                html += '<div style="color:var(--text-secondary);margin-top:4px;white-space:pre-line;">' + this.escapeHtml(entry.value) + '</div>';
                html += '</div>';
                html += '<div style="display:flex;gap:8px;margin-left:10px;">';
                html += '<button class="btn btn-icon" onclick="knowledgeApp.openEditModal(' + entry.id + ')" title="Edit"><i class="fas fa-pencil-alt"></i></button>';
                html += '<button class="btn btn-icon" onclick="knowledgeApp.deleteEntry(' + entry.id + ')" title="Delete" style="color:var(--danger-color);"><i class="fas fa-trash"></i></button>';
                html += '</div>';
                html += '</div>';
            }

            html += '</div></div>';
        }

        container.innerHTML = html;
    },

    openAddModal() {
        document.getElementById('entryId').value = '';
        document.getElementById('knowledgeForm').reset();
        document.querySelector('input[name="scope"][value="global"]').checked = true;
        this.toggleScope();
        const titleEl = document.getElementById('modalTitle');
        titleEl.setAttribute('data-i18n', 'knowledge.add');
        titleEl.textContent = typeof i18n !== 'undefined' ? i18n.t('knowledge.add') : 'Eintrag hinzufügen';
        document.getElementById('knowledgeModal').showModal();
    },

    openEditModal(id) {
        const entry = this.entries.find(e => e.id === id);
        if (!entry) return;

        document.getElementById('entryId').value = entry.id;
        document.getElementById('entryCategory').value = entry.category;
        document.getElementById('entryLabel').value = entry.label;
        document.getElementById('entryValue').value = entry.value;

        if (entry.property_id) {
            document.querySelector('input[name="scope"][value="property"]').checked = true;
            document.getElementById('entryPropertyId').value = entry.property_id;
        } else {
            document.querySelector('input[name="scope"][value="global"]').checked = true;
        }
        this.toggleScope();

        const titleEl = document.getElementById('modalTitle');
        titleEl.setAttribute('data-i18n', 'knowledge.edit');
        titleEl.textContent = typeof i18n !== 'undefined' ? i18n.t('knowledge.edit') : 'Eintrag bearbeiten';
        document.getElementById('knowledgeModal').showModal();
    },

    closeModal() {
        document.getElementById('knowledgeModal').close();
    },

    toggleScope() {
        const isProperty = document.querySelector('input[name="scope"][value="property"]').checked;
        document.getElementById('propertySelectRow').style.display = isProperty ? 'flex' : 'none';
    },

    async saveEntry(event) {
        event.preventDefault();
        const id = document.getElementById('entryId').value;
        const isProperty = document.querySelector('input[name="scope"][value="property"]').checked;

        const data = {
            category: document.getElementById('entryCategory').value,
            label: document.getElementById('entryLabel').value.trim(),
            value: document.getElementById('entryValue').value.trim(),
            property_id: isProperty ? parseInt(document.getElementById('entryPropertyId').value) : null,
        };

        try {
            const url = id ? `/chatbot/api/knowledge/${id}` : '/chatbot/api/knowledge';
            const method = id ? 'PUT' : 'POST';
            const resp = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });

            if (!resp.ok) {
                const err = await resp.json();
                alert(err.error || 'Save failed');
                return;
            }

            this.closeModal();
            this.loadEntries();
        } catch (e) {
            console.error('Save failed:', e);
            alert('Save failed');
        }
    },

    async deleteEntry(id) {
        const msg = typeof i18n !== 'undefined' ? i18n.t('knowledge.delete.confirm') : 'Eintrag wirklich löschen?';
        if (!confirm(msg)) return;

        try {
            const resp = await fetch(`/chatbot/api/knowledge/${id}`, { method: 'DELETE' });
            if (!resp.ok) throw new Error('Delete failed');
            this.loadEntries();
        } catch (e) {
            console.error('Delete failed:', e);
            alert('Delete failed');
        }
    },

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },
};

// Load entries on page ready
document.addEventListener('DOMContentLoaded', () => knowledgeApp.loadEntries());
```

- [ ] **Step 2: Commit**

```bash
git add static/js/knowledge.js
git commit -m "feat: add Knowledge Base JavaScript for CRUD and filtering"
```

---

### Task 7: Navigation + Settings Link + i18n

**Files:**
- Modify: `templates/chatbot/base.html` (lines 49-54)
- Modify: `templates/chatbot/settings.html` (around line 89)
- Modify: `static/js/i18n.js`

- [ ] **Step 1: Add sidebar nav entry in base.html**

Add after the Settings nav item (line 53) and before the Debug conditional (line 55):

```html
<li class="nav-item">
    <a href="{{ url_for('chatbot.knowledge_base') }}" class="nav-link {% if request.endpoint == 'chatbot.knowledge_base' %}active{% endif %}">
        <i class="fas fa-book"></i>
        <span data-i18n="nav.knowledge">Wissensdatenbank</span>
    </a>
</li>
```

- [ ] **Step 2: Add settings page link**

In `settings.html`, add after the Host Instructions textarea closing `</textarea>` tag (line 89), before the next `<div class="setting-item">`:

```html
<p class="setting-description" style="margin-top: 8px;">
    <span data-i18n="settings.ai.knowledgeLink">Für strukturierte Fakten (WLAN, Check-in, Umgebung) nutze die</span>
    <a href="{{ url_for('chatbot.knowledge_base') }}" style="color: var(--primary-color);">
        <span data-i18n="settings.ai.knowledgeLinkText">Wissensdatenbank →</span>
    </a>
</p>
```

- [ ] **Step 3: Add i18n keys**

Add the following keys to the `de` section and corresponding `en` section in `static/js/i18n.js`:

German keys:
```javascript
// Knowledge Base
'nav.knowledge': 'Wissensdatenbank',
'knowledge.title': 'Wissensdatenbank',
'knowledge.add': 'Eintrag hinzufügen',
'knowledge.edit': 'Eintrag bearbeiten',
'knowledge.save': 'Speichern',
'knowledge.cancel': 'Abbrechen',
'knowledge.filter.property': 'Unterkunft:',
'knowledge.filter.all': 'Alle',
'knowledge.filter.global': 'Global',
'knowledge.scope': 'Geltungsbereich',
'knowledge.scope.global': 'Global',
'knowledge.scope.property': 'Pro Unterkunft',
'knowledge.property': 'Unterkunft',
'knowledge.category': 'Kategorie',
'knowledge.label': 'Bezeichnung',
'knowledge.label.placeholder': 'z.B. WLAN-Passwort',
'knowledge.value': 'Information',
'knowledge.value.placeholder': 'z.B. SunnyBeach2024',
'knowledge.loading': 'Lade Einträge...',
'knowledge.empty': 'Noch keine Einträge vorhanden',
'knowledge.empty.hint': 'Fügen Sie Fakten hinzu, die die KI bei Gästeanfragen nutzen soll.',
'knowledge.error.load': 'Fehler beim Laden der Einträge',
'knowledge.delete.confirm': 'Eintrag wirklich löschen?',
'knowledge.cat.general': 'Allgemeine Infos',
'knowledge.cat.checkin': 'Check-in / Check-out',
'knowledge.cat.nearby': 'In der Nähe',
'knowledge.cat.rules': 'Hausregeln',
'knowledge.cat.emergency': 'Notfallkontakte',
'knowledge.cat.faq': 'Häufige Fragen',
'settings.ai.knowledgeLink': 'Für strukturierte Fakten (WLAN, Check-in, Umgebung) nutze die',
'settings.ai.knowledgeLinkText': 'Wissensdatenbank →',
```

English keys:
```javascript
'nav.knowledge': 'Knowledge Base',
'knowledge.title': 'Knowledge Base',
'knowledge.add': 'Add Entry',
'knowledge.edit': 'Edit Entry',
'knowledge.save': 'Save',
'knowledge.cancel': 'Cancel',
'knowledge.filter.property': 'Property:',
'knowledge.filter.all': 'All',
'knowledge.filter.global': 'Global',
'knowledge.scope': 'Scope',
'knowledge.scope.global': 'Global',
'knowledge.scope.property': 'Per Property',
'knowledge.property': 'Property',
'knowledge.category': 'Category',
'knowledge.label': 'Label',
'knowledge.label.placeholder': 'e.g. WiFi Password',
'knowledge.value': 'Information',
'knowledge.value.placeholder': 'e.g. SunnyBeach2024',
'knowledge.loading': 'Loading entries...',
'knowledge.empty': 'No entries yet',
'knowledge.empty.hint': 'Add facts that the AI should use when responding to guests.',
'knowledge.error.load': 'Failed to load entries',
'knowledge.delete.confirm': 'Really delete this entry?',
'knowledge.cat.general': 'General Info',
'knowledge.cat.checkin': 'Check-in / Check-out',
'knowledge.cat.nearby': 'Nearby Places',
'knowledge.cat.rules': 'House Rules',
'knowledge.cat.emergency': 'Emergency Contacts',
'knowledge.cat.faq': 'FAQ / Common Questions',
'settings.ai.knowledgeLink': 'For structured facts (WiFi, check-in, nearby places), use the',
'settings.ai.knowledgeLinkText': 'Knowledge Base →',
```

- [ ] **Step 4: Bump cache versions in base.html**

Update `i18n.js` version from `v=12` to `v=13` on line 189.

- [ ] **Step 5: Commit**

```bash
git add templates/chatbot/base.html templates/chatbot/settings.html static/js/i18n.js
git commit -m "feat: add Knowledge Base navigation, settings link, and i18n keys"
```

---

### Task 8: Manual Testing

- [ ] **Step 1: Start the app and verify migration**

```bash
cd C:/Users/admin/Documents/FlaskApp && python -m ChatBotAI.run
```

Navigate to `http://localhost:5000/chatbot/knowledge` — page should load with empty state.

- [ ] **Step 2: Test CRUD**

1. Click "Add Entry" → fill in a Global entry (General / WiFi Password / TestWifi123) → Save
2. Verify it appears in the list with "Global" badge
3. Click edit → change value → Save → verify update
4. Add a per-property entry → verify property badge shows
5. Filter by property → verify filtering works
6. Filter by "Global" → verify only global entries show
7. Delete an entry → confirm → verify removal

- [ ] **Step 3: Test AI context injection**

1. Add a few knowledge entries (global + per-property)
2. Open a conversation that has a property assigned
3. Click "AI Suggest" → check server logs for `[AI CONTEXT]` — should see knowledge entries in the prompt
4. Verify the AI response references the knowledge if relevant

- [ ] **Step 4: Test navigation**

1. Verify sidebar shows "Wissensdatenbank" link between Settings and Debug
2. Verify Settings page shows the link below Host Instructions
3. Switch language to English → verify all labels translate
4. Test on mobile viewport → verify page is responsive

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: Knowledge Base — complete implementation with AI integration"
```
