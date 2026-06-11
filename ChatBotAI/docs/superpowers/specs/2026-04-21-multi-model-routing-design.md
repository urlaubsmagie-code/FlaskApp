# Multi-Model Routing Design

**Date:** 2026-04-21
**Status:** Draft

## Problem

UMI uses one Ollama model for all AI tasks. Different tasks have different strengths — guest replies need natural German, while extraction/summarization need structured reasoning. Using a single model forces a compromise.

## Solution

Add an optional **Reasoning Model** setting. The main model handles all language tasks (guest replies). If a reasoning model is set, extraction/summarization tasks use it instead. If not set, everything uses the main model (zero model swaps).

## Task Classification

**Language tasks** (always use main model):
- `generate_guest_response()` — guest replies (compact + full prompt)
- Closing/gratitude replies
- Per-message lightbulb suggest

**Reasoning tasks** (use reasoning model if set, else main model):
- `extract_guest_info()` — memory extraction
- `generate_conversation_summary()` — conversation summaries
- `extract_knowledge_from_message()` — knowledge extraction
- `extract_correction_topic()` — correction topic labels

## Backend Changes

### AIService (`services/ai_service.py`)

1. Add `reasoning_model` property:
   - Reads `AISettings.get('reasoning_model')`
   - Returns the value if set and non-empty
   - Falls back to `self.model` if empty/null

2. Add optional `model` parameter to `_call_chat_api()`:
   - Signature: `_call_chat_api(self, messages, timeout=None, model=None)`
   - If `model` is provided, use it instead of `self.model` in the Ollama API call
   - If `model` is None, use `self.model` (current behavior)

3. Update reasoning functions to pass `model=self.reasoning_model`:
   - `extract_guest_info()` — uses `_call_chat_api` via `generate_response()`, so add `model` param to `generate_response()` too
   - `generate_conversation_summary()` — same pattern
   - `extract_knowledge_from_message()` — calls Ollama directly, update the model in the request JSON
   - `extract_correction_topic()` — calls Ollama directly via generate endpoint, update the model in the request JSON

4. Language functions unchanged — they keep using `self.model`.

### No migration needed

`AISettings` is a key-value table. The new key `reasoning_model` is just a new row — no schema change.

## Settings UI Changes

### Template (`templates/chatbot/settings.html`)

Add a new dropdown below the existing model selector, inside the same admin-only card:

- Label: **"Reasoning-Modell (optional)"** / "Reasoning Model (optional)"
- Helper text: *"Für Speicher-Extraktion, Zusammenfassungen und Wissens-Extraktion. Auf 'Standard' lassen, um das Hauptmodell für alles zu verwenden."*
- Dropdown options:
  - "Standard (wie Hauptmodell)" — empty value, default
  - All installed Ollama models (reuse existing `installedModels` array from `loadModels()`)
- On change: save via `POST /chatbot/api/settings` with key `reasoning_model`

### JavaScript

- In `loadModels()`: after populating the main model dropdown, also populate the reasoning model dropdown with the same model list
- Load current reasoning model value from `AISettings` and pre-select it
- Add change handler to save the selection

### i18n (`static/js/i18n.js`)

Add translation keys:
- `settings.model.reasoning` — "Reasoning-Modell (optional)" / "Reasoning Model (optional)"
- `settings.model.reasoning.desc` — helper text in DE/EN
- `settings.model.reasoning.default` — "Standard (wie Hauptmodell)" / "Standard (same as main model)"

## API Changes

### Existing endpoint: `POST /chatbot/api/settings`

Already handles saving arbitrary `AISettings` key-value pairs. No route changes needed — the frontend just sends `{key: 'reasoning_model', value: 'qwen3:8b'}`.

### Existing endpoint: `GET /chatbot/api/ollama/models`

Already returns installed models. Add `reasoning_model` to the response so the frontend knows the current value.

## Edge Cases

1. **Reasoning model not installed** — if the saved model name doesn't match any installed model, fall back to main model silently, log a warning.
2. **Semaphore** — existing semaphore serializes all AI calls. No concurrent GPU access regardless of model differences.
3. **Model swap delay** — Ollama takes ~3-5s to swap models. Only affects background reasoning tasks, not user-facing response time.
4. **Empty/null value** — treated as "use main model". No swap occurs.

## Testing

- Set reasoning model to empty → all tasks use main model (current behavior)
- Set reasoning model to qwen3:8b → extraction/summary use qwen3, replies use gemma2
- Delete the reasoning model from Ollama → should fall back to main model with a log warning
- Check Settings UI shows both dropdowns with correct pre-selected values
