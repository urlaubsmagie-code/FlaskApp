# Learn from Corrections — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a host edits an AI draft before sending, automatically capture both versions as a "correction" and feed them into future AI prompts so the AI improves over time.

**Architecture:** Corrections are stored as `KnowledgeEntry` records with `category='correction'`. Frontend captures the original AI text on edit, sends it alongside the corrected text. Backend compares with `difflib.SequenceMatcher`, stores if meaningfully different (ratio < 0.90), and extracts a topic label via a lightweight AI call. The AI prompt gets a new `PAST CORRECTIONS` section. The Wissensdatenbank page gets a tabbed layout (Wissen / Eskalation / Korrekturen).

**Tech Stack:** Flask, SQLAlchemy, Jinja2, vanilla JS, Ollama API

---

### Task 1: Add `correction` to KnowledgeEntry.VALID_CATEGORIES

**Files:**
- Modify: `models.py:533` (VALID_CATEGORIES list)
- Modify: `routes.py:3076` (validation uses VALID_CATEGORIES — auto-works)

- [ ] **Step 1: Add 'correction' to the VALID_CATEGORIES list**

In `models.py`, line 533, change:
```python
VALID_CATEGORIES = [
    'general', 'checkin_checkout', 'nearby',
    'house_rules', 'emergency', 'faq', 'escalation'
]
```
to:
```python
VALID_CATEGORIES = [
    'general', 'checkin_checkout', 'nearby',
    'house_rules', 'emergency', 'faq', 'escalation', 'correction'
]
```

This is the only model change needed — no migration required.

- [ ] **Step 2: Commit**

```bash
git add models.py
git commit -m "feat(corrections): add 'correction' to KnowledgeEntry.VALID_CATEGORIES"
```

---

### Task 2: Frontend — Capture original AI text on edit

**Files:**
- Modify: `static/js/conversation.js` — `editMessage()` and `sendMessage()` functions

The `editMessage()` function (line 700) currently copies the AI draft text into the textarea and rejects the draft. We need to save the original text before rejection, and include it in the send payload.

- [ ] **Step 1: Add module-level variable to store pending correction original text**

At the top of `conversation.js`, after line 21 (`let autoApprove = ...`), add:

```javascript
// Pending correction: stores original AI text when host edits a draft
let pendingCorrectionOriginal = null;
```

- [ ] **Step 2: Save original text in `editMessage()` before rejecting**

In `editMessage()` (line 700), add `pendingCorrectionOriginal = content;` before the textarea assignment. The function currently reads:

```javascript
async function editMessage(messageId) {
    const msgEl = document.querySelector(`[data-message-id="${messageId}"]`);
    const content = msgEl?.querySelector('.message-text')?.textContent || '';

    const textarea = document.getElementById('messageInput');
```

After extracting `content` and before setting textarea value, add:

```javascript
    // Save original AI text for correction tracking
    pendingCorrectionOriginal = content;
```

- [ ] **Step 3: Pass correction original as parameter to all send functions**

Rather than reading the module variable inside each send function (which breaks on fallback paths where `pendingCorrectionOriginal` is already cleared), capture it in `sendMessage()` and pass it as a parameter.

In `sendMessage()` (line 319), after `scrollToBottom()` (line 332), capture and clear:

```javascript
    // Capture and clear correction tracking before dispatching
    const correctionOriginal = pendingCorrectionOriginal;
    pendingCorrectionOriginal = null;
```

Then change the platform dispatch calls (lines 334-340) to pass it through:

```javascript
    if (conversationPlatform === 'email' && gmailConnected) {
        sendViaGmail(content, tempId, correctionOriginal);
    } else if (conversationPlatform === 'smoobu' && smoobuConnected) {
        sendViaSmoobu(content, tempId, correctionOriginal);
    } else {
        sendLocal(content, tempId, correctionOriginal);
    }
```

**Update `sendLocal()`** (line 343) — add parameter and use it:
```javascript
function sendLocal(content, tempId, correctionOriginal) {
```
Change body to:
```javascript
body: JSON.stringify({
    content: content,
    ...(correctionOriginal && { original_ai_content: correctionOriginal })
})
```

**Update `sendViaGmail()`** (line 364) — add parameter, use it, and pass to fallback:
```javascript
function sendViaGmail(content, tempId, correctionOriginal) {
```
Change body to:
```javascript
body: JSON.stringify({
    message: content,
    ...(correctionOriginal && { original_ai_content: correctionOriginal })
})
```
In the fallback calls to `sendLocal(content, tempId)`, change to `sendLocal(content, tempId, correctionOriginal)` (3 occurrences: lines ~373, ~382, ~395).

**Update `sendViaSmoobu()`** (line 399) — add parameter, use it, and pass to fallback:
```javascript
function sendViaSmoobu(content, tempId, correctionOriginal) {
```
Change body to:
```javascript
body: JSON.stringify({
    message: content,
    ...(correctionOriginal && { original_ai_content: correctionOriginal })
})
```
In the fallback calls to `sendLocal(content, tempId)`, change to `sendLocal(content, tempId, correctionOriginal)` (2 occurrences: lines ~425, ~428).

- [ ] **Step 5: Also clear on new AI draft generation**

In `generateAIResponse()` (line 469), at the top before the fetch call, add:

```javascript
    pendingCorrectionOriginal = null;
```

And in `suggestAIResponse()` (line 526), at the top before the fetch call, add:

```javascript
    pendingCorrectionOriginal = null;
```

This handles the edge case where the host clicks Edit but then generates a new draft instead of sending.

- [ ] **Step 6: Clear on approve and on empty send**

In `approveMessage()` (line 673), at the top of the function, add:
```javascript
    pendingCorrectionOriginal = null;
```

In `sendMessage()`, in the early return when content is empty (line 324 `if (!content) return;`), change to:
```javascript
    if (!content) {
        pendingCorrectionOriginal = null;
        return;
    }
```

This prevents stale correction state from leaking into unrelated sends.

- [ ] **Step 7: Commit**

```bash
git add static/js/conversation.js
git commit -m "feat(corrections): capture original AI text on edit for correction tracking"
```

---

### Task 3: Backend — Store correction on message send

**Files:**
- Modify: `routes.py` — `api_send_message()`, `api_gmail_reply()`, `api_smoobu_reply()`

- [ ] **Step 1: Add a helper function for storing corrections**

At the top of `routes.py`, add with the other imports:

```python
import difflib
```

Then add a helper function near the top of the file (after imports, before routes — around line 30 or wherever helper functions live):

```python
def _store_correction_if_needed(original_ai_content, corrected_content, conversation):
    """Compare original AI text with host's corrected version and store as correction if meaningfully different."""
    if not original_ai_content or not corrected_content:
        return None

    # Check similarity — skip if just a typo fix (ratio >= 0.90)
    ratio = difflib.SequenceMatcher(None, original_ai_content, corrected_content).ratio()
    if ratio >= 0.90:
        logger.info(f"[CORRECTION] Skipped — similarity {ratio:.2f} >= 0.90 (typo-level edit)")
        return None

    # Format the correction value
    value = f"FALSCH: {original_ai_content}\nRICHTIG: {corrected_content}"

    # Create KnowledgeEntry with placeholder label
    entry = KnowledgeEntry(
        property_id=conversation.property_id,
        category='correction',
        label='(wird extrahiert...)',
        value=value,
        sort_order=0
    )
    db.session.add(entry)
    db.session.commit()

    logger.info(f"[CORRECTION] Stored correction {entry.id} for conversation {conversation.id} "
                f"(similarity={ratio:.2f}, property_id={conversation.property_id})")

    # Extract topic label via AI in background thread
    entry_id = entry.id
    app = current_app._get_current_object()

    def _extract_topic():
        with app.app_context():
            try:
                ai = get_ai_service()
                if not ai:
                    return
                topic = ai.extract_correction_topic(original_ai_content, corrected_content)
                if topic:
                    e = KnowledgeEntry.query.get(entry_id)
                    if e:
                        e.label = topic
                        db.session.commit()
                        logger.info(f"[CORRECTION] Topic extracted for {entry_id}: {topic}")
            except Exception as ex:
                logger.warning(f"[CORRECTION] Topic extraction failed for {entry_id}: {ex}")

    threading.Thread(target=_extract_topic, daemon=True).start()

    return entry
```

- [ ] **Step 2: Add correction capture to `api_send_message()` (local send)**

In `api_send_message()` (line 574), after `db.session.commit()` (line 592) and before `response_data = message.to_dict()` (line 594), add:

```python
    # Store correction if host edited an AI draft
    original_ai_content = data.get('original_ai_content')
    if original_ai_content:
        _store_correction_if_needed(original_ai_content, data['content'], conversation)
```

- [ ] **Step 3: Add correction capture to `api_gmail_reply()`**

In `api_gmail_reply()` (line 2669), after the owner message is stored (after `router.process_owner_message(...)` around line 2720), add:

```python
        # Store correction if host edited an AI draft
        original_ai_content = data.get('original_ai_content')
        if original_ai_content:
            _store_correction_if_needed(original_ai_content, message_content, conversation)
```

- [ ] **Step 4: Add correction capture to `api_smoobu_reply()`**

In `api_smoobu_reply()` (line 2988), after the owner message is stored (after `router.process_owner_message(...)` around line 3024), add:

```python
        # Store correction if host edited an AI draft
        original_ai_content = data.get('original_ai_content')
        if original_ai_content:
            _store_correction_if_needed(original_ai_content, message_content, conversation)
```

- [ ] **Step 5: Commit**

```bash
git add routes.py
git commit -m "feat(corrections): store correction on message send when host edits AI draft"
```

---

### Task 4: AI Service — Topic extraction method

**Files:**
- Modify: `services/ai_service.py` — add `extract_correction_topic()` method

- [ ] **Step 1: Add the `extract_correction_topic()` method to AIService**

Add this method to the `AIService` class (after `generate_conversation_summary` or any convenient location):

```python
    def extract_correction_topic(self, original: str, corrected: str) -> Optional[str]:
        """Extract a 1-3 word topic label from a correction pair.

        Args:
            original: The original AI-generated text
            corrected: The host's corrected version

        Returns:
            Topic string (1-3 words) or None on failure
        """
        try:
            prompt = (
                "Given this original AI response and the host's corrected version, "
                "what is the topic of this correction in 1-3 words? "
                "Respond with ONLY the topic words, nothing else.\n\n"
                f"Original: {original[:500]}\n"
                f"Corrected: {corrected[:500]}"
            )

            response = requests.post(
                self.generate_endpoint,
                json={
                    'model': self.model,
                    'prompt': prompt,
                    'stream': False,
                    'options': {
                        'temperature': 0.1,
                        'num_predict': 20
                    }
                },
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                topic = result.get('response', '').strip()
                # Clean up: remove quotes, periods, limit length
                topic = topic.strip('"\'.')
                if topic and len(topic) <= 50:
                    return topic
            return None
        except Exception as e:
            logger.warning(f"Correction topic extraction failed: {e}")
            return None
```

- [ ] **Step 2: Commit**

```bash
git add services/ai_service.py
git commit -m "feat(corrections): add extract_correction_topic() to AIService"
```

---

### Task 5: AI Prompt — Load corrections and add PAST CORRECTIONS section

**Files:**
- Modify: `services/message_router.py` — `_generate_ai_response()` to load corrections
- Modify: `services/ai_service.py` — `generate_guest_response()` and `_build_chat_messages()` to accept and format corrections

- [ ] **Step 1: Load corrections in `_generate_ai_response()` (message_router.py)**

In `_generate_ai_response()`, after the knowledge_entries loading block (after the `except` at line 560), add:

```python
        # Load past corrections for AI context
        corrections = []
        try:
            correction_query = KnowledgeEntry.query.filter_by(category='correction')
            if conversation.property_id:
                # Up to 7 same-property + up to 3 global, max 10
                property_corrections = correction_query.filter_by(
                    property_id=conversation.property_id
                ).order_by(KnowledgeEntry.created_at.desc()).limit(7).all()

                global_corrections = correction_query.filter_by(
                    property_id=None
                ).order_by(KnowledgeEntry.created_at.desc()).limit(3).all()

                corrections = [c.to_dict() for c in property_corrections + global_corrections]
            else:
                corrections = [c.to_dict() for c in
                               correction_query.filter_by(property_id=None)
                               .order_by(KnowledgeEntry.created_at.desc()).limit(10).all()]
        except Exception as e:
            logger.warning(f"Failed to load corrections: {e}")
```

- [ ] **Step 2: Pass `corrections` to `generate_guest_response()`**

In the `generate_guest_response()` call (line 563), add the new parameter:

```python
        response_text = self.ai_service.generate_guest_response(
            ...existing params...,
            conversation_summary=conversation_summary,
            corrections=corrections
        )
```

- [ ] **Step 3: Add `corrections` parameter to `generate_guest_response()` in ai_service.py**

Add `corrections: Optional[List[Dict[str, Any]]] = None` to the method signature (after `conversation_summary`):

```python
    def generate_guest_response(
            self,
            ...existing params...,
            conversation_summary: Optional[str] = None,
            corrections: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[str]:
```

Pass it through to `_build_chat_messages()`:

```python
        messages = self._build_chat_messages(
            ...existing params...,
            conversation_summary=conversation_summary,
            corrections=corrections
        )
```

- [ ] **Step 4: Add `corrections` parameter to `_build_chat_messages()` and format the section**

Add `corrections: Optional[List[Dict[str, Any]]] = None` to the method signature.

Then, in `_build_chat_messages()`, after the `conversation_summary` section (after line 704), add:

```python
        if corrections:
            corrections_text = self._format_corrections(corrections)
            if corrections_text:
                system_parts.append(f"\n=== PAST CORRECTIONS (you made these mistakes before — don't repeat them) ===\n{corrections_text}\n===")
```

- [ ] **Step 5: Add `_format_corrections()` static method to AIService**

```python
    @staticmethod
    def _format_corrections(corrections: List[Dict[str, Any]], max_chars: int = 1500) -> str:
        """Format correction entries for the AI system prompt."""
        lines = []
        total = 0
        for c in corrections:
            label = c.get('label', 'Unknown')
            value = c.get('value', '')

            # Parse FALSCH:/RICHTIG: format
            if '\nRICHTIG: ' in value:
                parts = value.split('\nRICHTIG: ', 1)
                original = parts[0].replace('FALSCH: ', '', 1).strip()
                corrected = parts[1].strip()
                line = f'- "{label}": Don\'t say "{original[:150]}" → Correct: "{corrected[:150]}"'
            else:
                line = f'- "{label}": {value[:200]}'

            if total + len(line) > max_chars:
                break
            lines.append(line)
            total += len(line)

        return "\n".join(lines) if lines else ""
```

- [ ] **Step 6: Commit**

```bash
git add services/message_router.py services/ai_service.py
git commit -m "feat(corrections): load corrections and add PAST CORRECTIONS section to AI prompt"
```

---

### Task 6: Wissensdatenbank UI — Tabbed layout

**Files:**
- Modify: `templates/chatbot/knowledge.html` — add tab buttons
- Modify: `static/js/knowledge.js` — tab switching, separate rendering per tab
- Modify: `static/css/style.css` — tab styles

- [ ] **Step 1: Add tab buttons to knowledge.html**

Replace the page header section (lines 7-12) with a tabbed layout:

```html
<div class="settings-container">
    <div class="page-header">
        <h1><i class="fas fa-book"></i> <span data-i18n="knowledge.title">Wissensdatenbank</span></h1>
        <button class="btn btn-primary" onclick="knowledgeApp.openAddModal()">
            <i class="fas fa-plus"></i> <span data-i18n="knowledge.add">Eintrag hinzufügen</span>
        </button>
    </div>

    <!-- Tab Bar -->
    <div class="knowledge-tabs">
        <button class="knowledge-tab active" data-tab="knowledge" onclick="knowledgeApp.switchTab('knowledge')">
            <i class="fas fa-book"></i> <span data-i18n="knowledge.tab.knowledge">Wissen</span>
        </button>
        <button class="knowledge-tab" data-tab="escalation" onclick="knowledgeApp.switchTab('escalation')">
            <i class="fas fa-exclamation-triangle"></i> <span data-i18n="knowledge.tab.escalation">Eskalation</span>
        </button>
        <button class="knowledge-tab" data-tab="corrections" onclick="knowledgeApp.switchTab('corrections')">
            <i class="fas fa-spell-check"></i> <span data-i18n="knowledge.tab.corrections">Korrekturen</span>
        </button>
    </div>
```

- [ ] **Step 2: Add `correction` option to the category dropdown in the modal**

In the `<select id="entryCategory">` (line 76-84), add after the escalation option:

```html
                    <option value="correction" data-i18n="knowledge.cat.correction">Korrektur</option>
```

- [ ] **Step 3: Add tab styles to style.css**

Add these styles to `static/css/style.css`:

```css
/* Knowledge Base Tabs */
.knowledge-tabs {
    display: flex;
    gap: 4px;
    margin-bottom: 20px;
    border-bottom: 2px solid var(--border-color);
    padding-bottom: 0;
}

.knowledge-tab {
    padding: 10px 20px;
    border: none;
    background: none;
    color: var(--text-secondary);
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    border-bottom: 2px solid transparent;
    margin-bottom: -2px;
    transition: color 0.2s, border-color 0.2s;
    display: flex;
    align-items: center;
    gap: 6px;
}

.knowledge-tab:hover {
    color: var(--text-primary);
}

.knowledge-tab.active {
    color: var(--primary-color);
    border-bottom-color: var(--primary-color);
}

/* Correction entry styling */
.correction-entry {
    padding: 12px 20px;
    border-bottom: 1px solid var(--border-color);
}

.correction-entry:last-child {
    border-bottom: none;
}

.correction-pair {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-top: 8px;
    font-size: 13px;
}

.correction-original,
.correction-corrected {
    padding: 6px 10px;
    border-radius: 4px;
    line-height: 1.4;
}

.correction-original {
    background: rgba(239, 68, 68, 0.08);
    border-left: 3px solid var(--danger-color);
    color: var(--text-secondary);
}

.correction-corrected {
    background: rgba(34, 197, 94, 0.08);
    border-left: 3px solid var(--success-color);
}
```

- [ ] **Step 4: Implement tab switching in knowledge.js**

Add `currentTab` state and `switchTab()` to `knowledgeApp`, and modify `renderEntries()` to filter by active tab. Also add correction-specific rendering.

Replace the entire `knowledge.js` with updated version that adds:

1. `currentTab: 'knowledge'` property
2. `switchTab(tab)` method that updates button active states and re-renders
3. `renderEntries()` filters entries based on `currentTab`
4. `renderCorrections(entries)` method for the corrections tab with the FALSCH/RICHTIG format
5. Tab-aware empty states

Add to `CATEGORY_LABELS`:
```javascript
correction: { de: 'Korrektur', en: 'Correction' },
```

Add to `CATEGORY_ICONS`:
```javascript
correction: 'fa-spell-check',
```

Add to `CATEGORY_ORDER`:
```javascript
'correction'
```

Add to `knowledgeApp`:

```javascript
    currentTab: 'knowledge',

    switchTab(tab) {
        this.currentTab = tab;
        document.querySelectorAll('.knowledge-tab').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tab);
        });
        // Update URL param without reload
        const url = new URL(window.location);
        url.searchParams.set('tab', tab);
        history.replaceState(null, '', url);
        this.renderEntries();
    },
```

Modify `renderEntries()` to filter based on `this.currentTab`:
- `'knowledge'` tab: show categories `general, checkin_checkout, nearby, house_rules, emergency, faq`
- `'escalation'` tab: show category `escalation`
- `'corrections'` tab: show category `correction` (use special rendering)

Add `renderCorrections(entries)`:
```javascript
    renderCorrections(entries) {
        const container = document.getElementById('entriesContainer');
        const lang = (typeof i18n !== 'undefined' && i18n.currentLanguage) || 'de';

        if (!entries.length) {
            const emptyText = typeof i18n !== 'undefined' ? i18n.t('knowledge.corrections.empty') : 'Noch keine Korrekturen';
            const hintText = typeof i18n !== 'undefined' ? i18n.t('knowledge.corrections.empty.hint') : 'Wenn Sie KI-Entwürfe bearbeiten, lernt die KI automatisch daraus.';
            container.innerHTML =
                '<div class="settings-card"><div class="card-body" style="text-align:center;padding:40px;color:var(--text-secondary);">' +
                '<i class="fas fa-spell-check" style="font-size:48px;margin-bottom:15px;opacity:0.3;"></i>' +
                '<p style="font-size:16px;">' + emptyText + '</p>' +
                '<p style="font-size:14px;opacity:0.7;">' + hintText + '</p></div></div>';
            return;
        }

        const originalLabel = typeof i18n !== 'undefined' ? i18n.t('knowledge.corrections.original') : 'KI sagte';
        const correctedLabel = typeof i18n !== 'undefined' ? i18n.t('knowledge.corrections.corrected') : 'Richtig ist';

        let html = '<div class="settings-card"><div class="card-body" style="padding: 0;">';

        for (const entry of entries) {
            const scopeBadge = entry.property_name
                ? '<span class="badge" style="background:var(--primary-color);color:white;padding:2px 8px;border-radius:10px;font-size:11px;margin-left:8px;">' + this.escapeHtml(entry.property_name) + '</span>'
                : '<span class="badge" style="background:var(--text-secondary);color:white;padding:2px 8px;border-radius:10px;font-size:11px;margin-left:8px;">Global</span>';

            // Parse FALSCH:/RICHTIG: format
            let originalText = '';
            let correctedText = '';
            const value = entry.value || '';
            if (value.includes('\nRICHTIG: ')) {
                const parts = value.split('\nRICHTIG: ');
                originalText = parts[0].replace('FALSCH: ', '');
                correctedText = parts[1];
            } else {
                correctedText = value;
            }

            const date = entry.created_at ? new Date(entry.created_at).toLocaleDateString(lang === 'de' ? 'de-DE' : 'en-US') : '';

            html += '<div class="correction-entry">';
            html += '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:5px;">';
            html += '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:5px;">';
            html += '<strong>' + this.escapeHtml(entry.label) + '</strong>' + scopeBadge;
            html += '<span style="color:var(--text-light);font-size:12px;margin-left:8px;">' + date + '</span>';
            html += '</div>';
            html += '<div style="display:flex;gap:8px;">';
            html += '<button class="btn btn-icon" onclick="knowledgeApp.openEditModal(' + entry.id + ')" title="Edit"><i class="fas fa-pencil-alt"></i></button>';
            html += '<button class="btn btn-icon" onclick="knowledgeApp.deleteEntry(' + entry.id + ')" title="Delete" style="color:var(--danger-color);"><i class="fas fa-trash"></i></button>';
            html += '</div></div>';

            html += '<div class="correction-pair">';
            if (originalText) {
                html += '<div class="correction-original"><strong>' + originalLabel + ':</strong> ' + this.escapeHtml(originalText.substring(0, 200)) + (originalText.length > 200 ? '...' : '') + '</div>';
            }
            html += '<div class="correction-corrected"><strong>' + correctedLabel + ':</strong> ' + this.escapeHtml(correctedText.substring(0, 200)) + (correctedText.length > 200 ? '...' : '') + '</div>';
            html += '</div></div>';
        }

        html += '</div></div>';
        container.innerHTML = html;
    },
```

On DOMContentLoaded, check the URL `?tab=` parameter and switch to that tab:

```javascript
document.addEventListener('DOMContentLoaded', () => {
    const params = new URLSearchParams(window.location.search);
    const tab = params.get('tab');
    if (tab && ['knowledge', 'escalation', 'corrections'].includes(tab)) {
        knowledgeApp.currentTab = tab;
        document.querySelectorAll('.knowledge-tab').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tab);
        });
    }
    knowledgeApp.loadEntries();
});
```

- [ ] **Step 5: Update the `openAddModal()` to pre-set category based on current tab**

In `openAddModal()`, after resetting the form, set the category based on the active tab:

```javascript
    openAddModal() {
        document.getElementById('entryId').value = '';
        document.getElementById('knowledgeForm').reset();
        document.querySelector('input[name="scope"][value="global"]').checked = true;
        this.toggleScope();

        // Pre-set category based on current tab
        if (this.currentTab === 'corrections') {
            document.getElementById('entryCategory').value = 'correction';
        } else if (this.currentTab === 'escalation') {
            document.getElementById('entryCategory').value = 'escalation';
        }

        const titleEl = document.getElementById('modalTitle');
        titleEl.setAttribute('data-i18n', 'knowledge.add');
        titleEl.textContent = typeof i18n !== 'undefined' ? i18n.t('knowledge.add') : 'Eintrag hinzufügen';
        document.getElementById('knowledgeModal').showModal();
    },
```

- [ ] **Step 6: Commit**

```bash
git add templates/chatbot/knowledge.html static/js/knowledge.js static/css/style.css
git commit -m "feat(corrections): add tabbed layout to Wissensdatenbank (Wissen/Eskalation/Korrekturen)"
```

---

### Task 7: i18n — Add translation keys

**Files:**
- Modify: `static/js/i18n.js` — add keys for both `de` and `en`

- [ ] **Step 1: Add German keys**

After the existing `'knowledge.cat.escalation'` line (line 360), add:

```javascript
        'knowledge.tab.knowledge': 'Wissen',
        'knowledge.tab.escalation': 'Eskalation',
        'knowledge.tab.corrections': 'Korrekturen',
        'knowledge.cat.correction': 'Korrektur',
        'knowledge.corrections.empty': 'Noch keine Korrekturen',
        'knowledge.corrections.empty.hint': 'Wenn Sie KI-Entwürfe bearbeiten, lernt die KI automatisch daraus.',
        'knowledge.corrections.original': 'KI sagte',
        'knowledge.corrections.corrected': 'Richtig ist',
        'knowledge.corrections.autoSaved': 'KI-Korrektur gespeichert',
```

- [ ] **Step 2: Add English keys**

After the existing English knowledge keys (after `'knowledge.cat.escalation': 'Escalation'`), add:

```javascript
        'knowledge.tab.knowledge': 'Knowledge',
        'knowledge.tab.escalation': 'Escalation',
        'knowledge.tab.corrections': 'Corrections',
        'knowledge.cat.correction': 'Correction',
        'knowledge.corrections.empty': 'No corrections yet',
        'knowledge.corrections.empty.hint': 'When you edit AI drafts, the AI automatically learns from your changes.',
        'knowledge.corrections.original': 'AI said',
        'knowledge.corrections.corrected': 'Correct is',
        'knowledge.corrections.autoSaved': 'AI correction saved',
```

- [ ] **Step 3: Bump cache version**

Update the i18n script tag version in `templates/chatbot/base.html` (if applicable) and the knowledge.js script tag in `knowledge.html`. The existing knowledge.js tag at line 109:

```html
<script src="{{ url_for('chatbot.static', filename='js/knowledge.js') }}?v=1"></script>
```

Change to `?v=2`.

- [ ] **Step 4: Commit**

```bash
git add static/js/i18n.js templates/chatbot/knowledge.html
git commit -m "feat(corrections): add i18n keys and bump cache versions"
```

---

### Task 8: Show notification when correction is auto-saved

**Files:**
- Modify: `routes.py` — return `correction_saved` flag in send responses
- Modify: `static/js/conversation.js` — show toast based on server response

The notification must fire AFTER the server confirms the correction was stored, not optimistically.

- [ ] **Step 1: Return `correction_saved` flag from `api_send_message()`**

In `api_send_message()`, change the correction capture code (added in Task 3) to capture the result:

```python
    # Store correction if host edited an AI draft
    correction_saved = False
    original_ai_content = data.get('original_ai_content')
    if original_ai_content:
        correction_saved = _store_correction_if_needed(original_ai_content, data['content'], conversation) is not None
```

Then include it in the response:

```python
    response_data = message.to_dict()
    response_data['correction_saved'] = correction_saved
```

- [ ] **Step 2: Show notification in `sendLocal()` on success**

In `sendLocal()`, in the `.then()` success handler, after the message ID swap, add:

```javascript
        if (data.correction_saved) {
            showNotification(i18n.t('knowledge.corrections.autoSaved'), 'info', 3000);
        }
```

For Gmail and Smoobu routes: the correction is a side effect and they don't need to return a flag — we can show a simpler notification based on whether `correctionOriginal` was passed. In `sendViaGmail()` and `sendViaSmoobu()`, in the `.then()` success handler, add:

```javascript
        if (correctionOriginal) {
            showNotification(i18n.t('knowledge.corrections.autoSaved'), 'info', 3000);
        }
```

This is acceptable since the Gmail/Smoobu send succeeded, meaning the server processed the request and the correction storage is highly likely to succeed (it's a simple DB insert).

- [ ] **Step 3: Commit**

```bash
git add routes.py static/js/conversation.js
git commit -m "feat(corrections): show notification when AI correction is confirmed saved"
```

---

### Task 9: Exclude corrections from knowledge_entries query in message_router

**Files:**
- Modify: `services/message_router.py` — filter out corrections from knowledge_entries

- [ ] **Step 1: Exclude corrections from the knowledge_entries query**

In `_generate_ai_response()`, the existing knowledge_entries query (line 546-558) loads ALL entries. Corrections should be loaded separately (done in Task 5). Add a filter to exclude them:

Change line 549 from:
```python
knowledge_entries = [e.to_dict() for e in
                    KnowledgeEntry.query.filter(
                        db.or_(
                            KnowledgeEntry.property_id.is_(None),
                            KnowledgeEntry.property_id == conversation.property_id
                        )
                    ).order_by(KnowledgeEntry.category, KnowledgeEntry.sort_order).all()]
```
to:
```python
knowledge_entries = [e.to_dict() for e in
                    KnowledgeEntry.query.filter(
                        KnowledgeEntry.category != 'correction',
                        db.or_(
                            KnowledgeEntry.property_id.is_(None),
                            KnowledgeEntry.property_id == conversation.property_id
                        )
                    ).order_by(KnowledgeEntry.category, KnowledgeEntry.sort_order).all()]
```

Do the same for the else branch (line 556):
```python
knowledge_entries = [e.to_dict() for e in
                    KnowledgeEntry.query.filter(
                        KnowledgeEntry.category != 'correction'
                    ).filter_by(property_id=None)
                    .order_by(KnowledgeEntry.category, KnowledgeEntry.sort_order).all()]
```

- [ ] **Step 2: Commit**

```bash
git add services/message_router.py
git commit -m "feat(corrections): exclude corrections from regular knowledge_entries query"
```

---

### Task 10: Manual test and verify end-to-end

- [ ] **Step 1: Start the app**

```bash
python -m ChatBotAI.run
```

- [ ] **Step 2: Test correction capture flow**

1. Open a conversation with AI enabled
2. Click "Suggest" to get an AI draft in the textarea
3. Edit the text meaningfully (change a fact, not just a typo)
4. Click Send
5. Verify notification "KI-Korrektur gespeichert" appears
6. Go to Wissensdatenbank → Korrekturen tab
7. Verify the correction appears with FALSCH/RICHTIG display
8. Verify topic label gets extracted (may take a few seconds)

- [ ] **Step 3: Test AI prompt includes corrections**

1. Open the same conversation
2. Click "Suggest" and check the console for AI Context
3. The AI should now avoid repeating the corrected mistake

- [ ] **Step 4: Test edge cases**

1. Edit but make only a tiny change (typo fix) → no correction stored
2. Switch tabs in Wissensdatenbank → state persists via URL
3. Manually add a correction via the "Add" button on the Korrekturen tab
4. Delete a correction → removed from future prompts

- [ ] **Step 5: Final commit (if any fixups needed)**

```bash
git add -A
git commit -m "feat(corrections): Learn from Corrections feature complete"
```
