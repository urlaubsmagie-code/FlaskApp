# Multi-Model Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow UMI to use different Ollama models for language tasks (guest replies) vs reasoning tasks (extraction, summaries), with an optional "Reasoning Model" setting in the UI.

**Architecture:** Add a `reasoning_model` property to AIService that reads from AISettings. Pass an optional `model` parameter through `generate_response()` → `_call_chat_api()` so reasoning functions can override the model. Add a dropdown in Settings UI to configure it.

**Tech Stack:** Python/Flask backend, Jinja2 + vanilla JS frontend, SQLite AISettings table, Ollama API

---

### Task 1: Add `model` parameter to `_call_chat_api()` and `generate_response()`

**Files:**
- Modify: `services/ai_service.py:187-204` (`generate_response`)
- Modify: `services/ai_service.py:206-265` (`_call_chat_api`)

- [ ] **Step 1: Add `model` parameter to `_call_chat_api()`**

In `services/ai_service.py`, change the `_call_chat_api` signature and model usage:

```python
def _call_chat_api(self, messages: List[Dict[str, str]], timeout: Optional[int] = None, model: Optional[str] = None) -> Optional[str]:
```

Inside the method, at line 247 change the log line:

```python
effective_model = model or self.model
logger.debug(f"Sending {len(messages)} messages to Ollama ({effective_model})"
             + (f" [retry {attempt}]" if attempt > 0 else ""))
```

At line 255 change the model in the request JSON:

```python
'model': effective_model,
```

At line 276 update the log line:

```python
logger.info(f"[AI CALL] model={effective_model} | {elapsed:.1f}s | {eval_count} tokens")
```

- [ ] **Step 2: Add `model` parameter to `generate_response()`**

```python
def generate_response(self, prompt: str, system: Optional[str] = None, timeout: Optional[int] = None, model: Optional[str] = None) -> Optional[str]:
```

Pass it through to `_call_chat_api`:

```python
return self._call_chat_api(messages, timeout, model=model)
```

- [ ] **Step 3: Verify no breakage**

Restart the server. Open a conversation and click the lightbulb to trigger a response. Confirm it still works — no parameters changed for existing callers since `model` defaults to `None`.

- [ ] **Step 4: Commit**

```bash
git add services/ai_service.py
git commit -m "feat: add model parameter to _call_chat_api and generate_response"
```

---

### Task 2: Add `reasoning_model` property to AIService

**Files:**
- Modify: `services/ai_service.py` (add property after `__init__`)

- [ ] **Step 1: Add the `reasoning_model` property**

Add this property to the AIService class, after the `__init__` method (after line 48):

```python
@property
def reasoning_model(self) -> str:
    """Get the model to use for reasoning tasks (extraction, summaries).
    Returns the reasoning model if set, otherwise falls back to main model."""
    try:
        from ..models import AISettings
        rm = AISettings.get('reasoning_model')
        if rm and rm.strip():
            return rm.strip()
    except Exception:
        pass
    return self.model
```

- [ ] **Step 2: Commit**

```bash
git add services/ai_service.py
git commit -m "feat: add reasoning_model property to AIService"
```

---

### Task 3: Wire reasoning functions to use `reasoning_model`

**Files:**
- Modify: `services/ai_service.py:366` (`extract_guest_info` — calls `generate_response`)
- Modify: `services/ai_service.py:568` (`generate_conversation_summary` — calls `generate_response`)
- Modify: `services/ai_service.py:670` (`extract_knowledge_from_message` — calls `generate_response`)
- Modify: `services/ai_service.py:601-604` (`extract_correction_topic` — calls Ollama directly)

- [ ] **Step 1: Update `extract_guest_info()`**

At line 366, change:
```python
response = self.generate_response(prompt, system=system, timeout=self.timeout)
```
to:
```python
response = self.generate_response(prompt, system=system, timeout=self.timeout, model=self.reasoning_model)
```

- [ ] **Step 2: Update `generate_conversation_summary()`**

At line 568, change:
```python
response = self.generate_response(prompt, system=system)
```
to:
```python
response = self.generate_response(prompt, system=system, model=self.reasoning_model)
```

- [ ] **Step 3: Update `extract_knowledge_from_message()`**

At line 670, change:
```python
response = self.generate_response(prompt, system=system, timeout=self.timeout)
```
to:
```python
response = self.generate_response(prompt, system=system, timeout=self.timeout, model=self.reasoning_model)
```

- [ ] **Step 4: Update `extract_correction_topic()`**

This function calls Ollama's generate endpoint directly (not via `generate_response`). At line 604, change:
```python
'model': self.model,
```
to:
```python
'model': self.reasoning_model,
```

- [ ] **Step 5: Verify**

Restart the server. With no reasoning model set in AISettings, all functions should still use the main model (fallback behavior). Test by opening a conversation and triggering a suggestion.

- [ ] **Step 6: Commit**

```bash
git add services/ai_service.py
git commit -m "feat: wire reasoning functions to use reasoning_model"
```

---

### Task 4: Add `reasoning_model` to API response

**Files:**
- Modify: `routes.py:1583-1587` (`api_get_ollama_models`)

- [ ] **Step 1: Include reasoning_model in the models API response**

In the `api_get_ollama_models()` function, before the `return jsonify(...)` at line 1583, read the current reasoning model:

```python
reasoning_model = AISettings.get('reasoning_model') or ''
```

Add it to the response dict:

```python
return jsonify({
    'current_model': current_model,
    'reasoning_model': reasoning_model,
    'installed': installed,
    'suggested': suggested
})
```

- [ ] **Step 2: Add `reasoning_model` to ADMIN_ONLY_SETTINGS**

At line 1510, add `'reasoning_model'` to the set:

```python
ADMIN_ONLY_SETTINGS = {'ai_temperature', 'ai_max_tokens', 'ollama_model', 'reasoning_model'}
```

- [ ] **Step 3: Commit**

```bash
git add routes.py
git commit -m "feat: include reasoning_model in models API response"
```

---

### Task 5: Add reasoning model dropdown to Settings UI

**Files:**
- Modify: `templates/chatbot/settings.html:200` (add HTML after main model selector)
- Modify: `templates/chatbot/settings.html:535-583` (JS `loadModels` function)

- [ ] **Step 1: Add the HTML dropdown**

After the main model selector `</div>` at line 200, add the reasoning model selector:

```html
<!-- Reasoning Model Selector (optional) -->
<div class="setting-item" style="flex-direction: column; align-items: flex-start; gap: 10px; margin-top: 15px;">
    <div class="setting-info">
        <label for="reasoningModelSelect" data-i18n="settings.model.reasoning">Reasoning-Modell (optional)</label>
        <p class="setting-description" data-i18n="settings.model.reasoning.desc">Für Speicher-Extraktion, Zusammenfassungen und Wissens-Extraktion. Auf „Standard" lassen, um das Hauptmodell für alles zu verwenden.</p>
    </div>
    <select id="reasoningModelSelect" class="setting-select" style="width: 100%;">
        <option value="" data-i18n="settings.model.reasoning.default">Standard (wie Hauptmodell)</option>
    </select>
</div>
```

- [ ] **Step 2: Update `loadModels()` JS to populate the reasoning dropdown**

In the `loadModels()` function, after the main model select is populated (around line 570, after the loop that adds options to `select`), add:

```javascript
// Populate reasoning model selector
const reasoningSelect = document.getElementById('reasoningModelSelect');
if (reasoningSelect) {
    const currentReasoning = data.reasoning_model || '';
    reasoningSelect.innerHTML = '<option value="">' +
        (translations['settings.model.reasoning.default'] || 'Standard (wie Hauptmodell)') +
        '</option>';
    installedModels.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m.name;
        opt.textContent = m.name;
        if (m.name === currentReasoning) opt.selected = true;
        reasoningSelect.appendChild(opt);
    });
}
```

- [ ] **Step 3: Add change handler for reasoning model dropdown**

After the `loadModels()` function, add an event listener:

```javascript
document.getElementById('reasoningModelSelect')?.addEventListener('change', function() {
    const value = this.value;
    fetch('/chatbot/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: 'reasoning_model', value: value })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const label = value || (translations['settings.model.reasoning.default'] || 'Standard');
            showNotification('Reasoning-Modell: ' + label, 'success');
        } else {
            showNotification('Error: ' + (data.error || 'Failed'), 'error');
        }
    })
    .catch(err => showNotification('Error: ' + err.message, 'error'));
});
```

- [ ] **Step 4: Verify**

Restart server. Go to Settings. The reasoning model dropdown should appear below the main model selector, showing "Standard (wie Hauptmodell)" plus all installed models. Change it and verify the notification appears.

- [ ] **Step 5: Commit**

```bash
git add templates/chatbot/settings.html
git commit -m "feat: add reasoning model dropdown to Settings UI"
```

---

### Task 6: Add i18n translations

**Files:**
- Modify: `static/js/i18n.js` (add German + English keys)

- [ ] **Step 1: Add German translations**

After the `settings.model.suggested.desc` line (line 176), add:

```javascript
'settings.model.reasoning': 'Reasoning-Modell (optional)',
'settings.model.reasoning.desc': 'Für Speicher-Extraktion, Zusammenfassungen und Wissens-Extraktion. Auf „Standard" lassen, um das Hauptmodell für alles zu verwenden.',
'settings.model.reasoning.default': 'Standard (wie Hauptmodell)',
```

- [ ] **Step 2: Add English translations**

After the `settings.model.suggested.desc` line in the English section (line 636), add:

```javascript
'settings.model.reasoning': 'Reasoning Model (optional)',
'settings.model.reasoning.desc': 'For memory extraction, summaries, and knowledge extraction. Leave on "Standard" to use the main model for everything.',
'settings.model.reasoning.default': 'Standard (same as main model)',
```

- [ ] **Step 3: Bump i18n cache version**

Update the i18n script tag version in `templates/chatbot/base.html` from `v22` to `v23`.

- [ ] **Step 4: Commit**

```bash
git add static/js/i18n.js templates/chatbot/base.html
git commit -m "feat: add i18n translations for reasoning model setting"
```

---

### Task 7: End-to-end verification

- [ ] **Step 1: Test default behavior (no reasoning model set)**

1. Restart server
2. Go to Settings → confirm reasoning model shows "Standard"
3. Open a conversation, trigger KI-Vorschlag → should use gemma2:9b
4. Check server logs: all AI calls should show `model=gemma2:9b`

- [ ] **Step 2: Test with reasoning model set**

1. In Settings, set reasoning model to `qwen3:8b`
2. Open a conversation, send a test message to trigger extraction + response
3. Check server logs:
   - `extract_guest_info` → should log `model=qwen3:8b`
   - `generate_guest_response` → should log `model=gemma2:9b`

- [ ] **Step 3: Test fallback on invalid model**

1. Manually set `reasoning_model` to a non-existent model name in AISettings
2. Trigger extraction → should fall back to main model with a warning in logs

- [ ] **Step 4: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: multi-model routing adjustments from testing"
```
