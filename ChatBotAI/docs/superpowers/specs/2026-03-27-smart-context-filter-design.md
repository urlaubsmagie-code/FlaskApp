# Smart Context Filter — Design Spec

**Date**: 2026-03-27
**Status**: Approved
**Goal**: Reduce AI prompt overload by filtering context to only what's relevant for each guest message, improving response accuracy on qwen3:8b.

## Problem

The AI system prompt currently includes ALL available context for every message:
- Full guest profile (family, pets, allergies, booking, interests, preferences, special requests)
- All knowledge base entries (20-50 entries, capped at 2000 chars)
- Full property details (address, amenities, house rules, check-in/out times)
- Reservation info from Smoobu
- All corrections (up to 10)
- Conversation summary
- Host instructions
- Last 10 conversation messages

For an 8B model (qwen3:8b), this creates two failure modes:
1. **AI responds to already-handled topics** — guest says "Danke :)" after the host answered, AI rehashes old topics (sauna, dogs, check-in)
2. **AI responds to the wrong topic** — guest asks about Parkkarte, AI answers about check-in because check-in KB entries dominate the context

### Additional Bugs Found

1. **Missing context in KI-Vorschlag**: `api_suggest_ai_response` in routes.py is missing `conversation_summary` and `corrections` parameters, making it less informed than the auto-respond path.
2. **KB correction filter missing in routes.py**: Both `api_suggest_ai_response` and `api_generate_ai_response` do NOT filter `KnowledgeEntry.category != 'correction'` from KB queries, unlike `message_router.py` which correctly excludes them. This means corrections can appear both as KB entries and as corrections in the auto-respond path (double-fed), and in the route endpoints corrections masquerade as regular KB entries.

## Solution

A new `ContextFilter` class in `services/context_filter.py` that preprocesses loaded context before prompt building. Pure Python, no AI calls, no new dependencies, instant execution. Thread-safe — implemented as a stateless class with all methods taking inputs as parameters (no instance state). Stop word lists and suffix rules stored as `frozenset` class constants for O(1) lookup.

### Architecture

```
Guest message arrives
        |
Load ALL context (unchanged)
        |
ContextFilter.filter()    <-- NEW
        |
Filtered context (only relevant)
        |
generate_guest_response() receives filtered params
        |
_build_chat_messages() builds focused prompt
```

### Call Site Pattern

The ContextFilter is called in each code path **before** `generate_guest_response()`. The caller destructures the `FilteredContext` dataclass back into individual parameters:

```python
from .services.context_filter import ContextFilter

filtered = ContextFilter.filter(
    latest_message=latest_guest_message.content,
    conversation_history=[m.to_dict() for m in messages],
    knowledge_entries=knowledge_entries,
    guest_profile=profile,
    property_info=property_info,
    corrections=corrections,
    reservation_info=reservation_info,
)

logger.debug(f"[CONTEXT FILTER] {filtered.filter_log}")

ai_response = ai_service.generate_guest_response(
    guest_profile=filtered.guest_profile,
    conversation_history=[m.to_dict() for m in messages],  # full history, unchanged
    latest_message=latest_guest_message.content,
    property_info=filtered.property_info,
    tone=tone,
    host_instructions=host_instructions,
    conversation_subject=conversation.subject,
    max_history=max_history,
    reservation_info=filtered.reservation_info,
    knowledge_entries=filtered.knowledge_entries,
    conversation_summary=conversation_summary,
    corrections=filtered.corrections,
    resolved_topics=filtered.resolved_topics,  # NEW param
    is_closing=filtered.is_closing,            # NEW param
)
```

Note: `conversation_history` is passed unmodified — the filter operates on context (KB, profile, etc.), not on the message history itself.

## Filter Details

### Filter 1: Gratitude/Closing Detection

Detects when a guest sends a thank-you or closing message after the host/AI already replied.

**Relationship to existing `is_acknowledgment()`:** The existing method catches pure closers ("Ok", "Gut") and skips AI entirely (no response generated). This filter is a separate, complementary layer: it catches gratitude messages ("Danke", "Thanks") which DO get a response, but a **minimal** one with stripped context. The two don't overlap — `is_acknowledgment()` runs first and short-circuits before the filter is reached.

**Logic:**
- Check if the latest guest message is short gratitude (< 60 chars, matches gratitude phrases)
- Check if the message immediately before it is from `owner` or `ai` (covers both manual replies and auto-responded conversations)
- If both true: set `is_closing = True`

**Gratitude phrases** (multilingual, stored as `frozenset`):
- DE: danke, vielen dank, dankeschön, herzlichen dank, danke schön, danke dir, danke sehr, super danke, toll danke
- EN: thanks, thank you, thx, many thanks, cheers, appreciated, thanks a lot, thank you so much
- ES: gracias, muchas gracias
- FR: merci, merci beaucoup
- IT: grazie, molte grazie

Matching: lowercase, strip punctuation and emoji, check if normalized text matches or starts with a gratitude phrase. Also handle "Danke :)" pattern (gratitude + emoji/smiley).

**Effect when `is_closing = True`:**
- Strip ALL context: no KB, no guest profile details (keep name only), no property, no corrections, no reservation
- The system prompt gets a simplified instruction: "The guest is thanking the host. Reply briefly and warmly. Keep it to 1-2 sentences."
- This prevents the model from filling the void with hallucinated context

### Filter 2: Already-Answered Detection

Scans the **raw** conversation history (before any merging/collapsing done by `_build_chat_messages`) to identify guest topics that already received a host/AI reply.

**Logic:**
- Walk conversation history chronologically (the raw message list passed to `ContextFilter.filter()`)
- For each guest message: check if a subsequent message from `owner` or `ai` exists (i.e., someone replied)
- If yes: extract a topic label from the guest's message
- Topic extraction: take the message content, strip HTML, strip stop words, keep the first 60 chars of meaningful text
- Not limited to messages with `?` — statements like "Ich brauche einen Parkplatz" also count as topics that were addressed
- Skip very short messages (< 15 chars) to avoid labeling "Ok" or "Danke" as topics

**Output:** A list of strings like:
```
- "Sauna Anzünder Pellets" → answered
- "Parkkarte finden" → answered
- "Check-in Anweisungen" → answered
```

**Integration:** Passed as `resolved_topics` to `generate_guest_response()`, then to `_build_chat_messages()`. Injected into the system prompt as:
```
=== ALREADY RESOLVED (do NOT address these topics again) ===
- Sauna Anzünder Pellets → answered
- Check-in Anweisungen → answered
===
```

When `resolved_topics` are present, the conversation summary section's existing "These topics are ALREADY RESOLVED" trailer text is dropped to avoid redundancy. The explicit resolved topics list is more specific and replaces the generic instruction.

### Filter 3: Knowledge Base Filtering

Scores KB entries by keyword relevance to the guest's latest message. Only high-scoring entries are included.

**Keyword extraction:**
1. Lowercase the guest message
2. Remove punctuation
3. Remove stop words (German + English, stored as `frozenset`)
4. Keep both the original token AND a stemmed version (strip common suffixes: German -en, -er, -ung, -keit, -heit, -lich, -isch, -nen; English -ing, -ed, -tion, -ly)
5. Keep tokens with length >= 3 (after stemming, minimum length 4 to reduce noise from over-stemmed German words)

**Note on stemming:** The suffix stripping is intentionally naive. German morphology is complex and the stemmer will produce garbage in some cases (e.g., "Zimmer" → "Zimm"). This is acceptable because: (a) the original unstemmed token is also kept for matching, (b) substring matching provides a safety net, and (c) false negatives are safe — they just mean more KB context via the fallback, not wrong context. The keyword lists will be expanded iteratively based on real usage.

**Scoring each KB entry:**
- Tokenize entry's `label` and `value` fields (lowercased, split on whitespace and punctuation)
- For each keyword from the guest message:
  - +2 if exact token match in label tokens
  - +1 if exact token match in value tokens
  - +1 if keyword is a substring of any label or value token (min keyword length 4 to avoid noise)
- **Include**: entries with score >= 1
- **Cap**: top 5 entries by score
- **Fallback**: if zero entries match, include up to 3 entries from `faq` and `general` categories

**Walkthrough example:**
Guest: "Wo kann ich die Parkkarte finden?"
After stop word removal: `["parkkarte", "finden"]`
After stemming (keeping both): `["parkkarte", "parkkar", "finden", "find"]`

| KB Entry | Label tokens | Value tokens | Matches | Score |
|----------|-------------|-------------|---------|-------|
| Parkkarte: auf dem Schreibtisch | [parkkarte] | [schreibtisch] | "parkkarte" exact in label (+2) | 2 |
| Check-in: ab 15:00 Uhr | [check-in] | [15:00, uhr] | — | 0 |
| WiFi: Passwort XYZ | [wifi] | [passwort, xyz] | — | 0 |

Result: Only "Parkkarte" entry included.

### Filter 4: Guest Profile Filtering

Reduces guest profile to sections relevant to the current message.

**Always included:** name, booking dates (check-in, check-out, num_guests), special_requests (may contain active requests)

**Conditionally included based on keyword presence:**

| Profile Section | Include when message contains (substring match) |
|----------------|-------------------------------|
| allergies | food, essen, restaurant, küche, cook, diet, allergi, unverträg, glutenfrei, laktose, vegan, vegetarisch, lebensmittel, frühstück, breakfast |
| pets | hund, hunde, katze, dog, cat, pet, tier, haustier, welpe, puppy |
| family | kind, kinder, baby, familie, family, child, kids, kleinkind, toddler |
| preferences | any keyword overlap with stored preference keys |
| interests | any keyword overlap with stored interest values |

**Fallback:** If the message is long (> 100 chars) or contains no clear topic keywords, include the full profile (safe default). This ensures the filter only removes context when it's confident about the topic.

## Integration Points

### 1. New file: `services/context_filter.py`

Contains the `ContextFilter` class with:
- `filter()` — class method / static entry point, returns a `FilteredContext` dataclass
- `_detect_closing()` — Filter 1
- `_detect_resolved_topics()` — Filter 2
- `_filter_knowledge_entries()` — Filter 3
- `_filter_guest_profile()` — Filter 4
- `_extract_keywords()` — shared keyword extraction
- Stop word lists and suffix rules as `frozenset` class constants

### 2. Modified: `routes.py` (2 endpoints)

**`api_suggest_ai_response()`:**
- Add missing `conversation_summary` loading (copy from message_router pattern)
- Add missing `corrections` loading (with `category != 'correction'` filter on KB query — fixing the existing bug)
- Fix KB query to exclude `correction` category (matching message_router behavior)
- Add ContextFilter call before `generate_guest_response()`
- Include `filter_log` in debug context when `include_debug=True`

**`api_generate_ai_response()`:**
- Fix KB query to exclude `correction` category
- Add ContextFilter call before `generate_guest_response()`

### 3. Modified: `services/message_router.py`

**`_generate_ai_response()`:**
- Add ContextFilter call before `generate_guest_response()`
- (KB and correction loading is already correct here)

Note: `generate_ai_response_for_conversation()` calls `_generate_ai_response()` internally, so it's implicitly covered.

### 4. Modified: `services/ai_service.py`

**`generate_guest_response()`:**
- Accept new optional parameters: `resolved_topics: Optional[List[str]]`, `is_closing: bool = False`
- Pass them through to `_build_chat_messages()`

**`_build_chat_messages()`:**
- Accept new optional parameters: `resolved_topics: Optional[List[str]]`, `is_closing: bool = False`
- When `is_closing=True`: use a simplified system prompt (just role + "reply briefly to thank-you")
- When `resolved_topics` provided: inject `=== ALREADY RESOLVED ===` section and drop the conversation_summary trailer text about already resolved topics

### 5. No changes to:
- Database models
- Frontend (JS, HTML, CSS)
- Other services

## FilteredContext Return Type

```python
@dataclass
class FilteredContext:
    knowledge_entries: List[Dict[str, Any]]
    guest_profile: Dict[str, Any]
    property_info: Optional[Dict[str, Any]]      # None if is_closing
    corrections: List[Dict[str, Any]]
    reservation_info: Optional[Dict[str, Any]]    # None if is_closing
    resolved_topics: List[str]
    is_closing: bool
    filter_log: Dict[str, Any]                    # For debug logging
```

The `filter_log` includes before/after counts for debugging:
```python
filter_log = {
    'is_closing': False,
    'keywords': ['parkkarte', 'parkkar', 'finden', 'find'],
    'kb_total': 35,
    'kb_kept': 1,
    'kb_kept_labels': ['Parkkarte'],
    'profile_sections_total': 7,
    'profile_sections_kept': ['name', 'booking', 'special_requests'],
    'resolved_topics_count': 3,
    'corrections_total': 5,
    'corrections_kept': 2,
}
```

## Logging

All filtering decisions logged at DEBUG level:
```
[CONTEXT FILTER] message='Danke :)' | is_closing=True | skipped all context
[CONTEXT FILTER] message='Wo ist die Parkkarte?' | kb=1/35 entries | profile=name,booking,special_requests | resolved=3 topics | keywords=parkkarte,finden
```

## Testing Strategy

- Manual testing with real conversations from the app
- Test cases for each filter:
  - Gratitude after host reply → is_closing=True
  - Gratitude after AI reply → is_closing=True
  - Gratitude as first message → is_closing=False (no prior reply)
  - Question with KB matches → correct entries selected
  - Statement (no ?) with KB matches → correct entries selected
  - Question with no KB matches → fallback entries included
  - Message about pets → pet profile section included, others excluded
  - Message about food → allergies section included
  - Short generic message → full profile included (safe fallback)
  - Long message (> 100 chars) → full profile included (safe fallback)
  - KB correction category excluded from knowledge_entries

## Risk Mitigation

- **Over-filtering**: If keyword matching misses a relevant KB entry, the AI just won't have that info and will say "I'll check" — same as today when KB doesn't have the answer. This is safe.
- **Under-filtering**: If too many entries match, we cap at 5. Worst case is similar to today's behavior.
- **Fallback everywhere**: Every filter has a safe default (include everything) when uncertain. The filter only removes context when it's confident.
- **Naive stemming**: German morphology is complex. The stemmer will produce garbage for some words, but keeping both original and stemmed tokens plus substring matching provides adequate coverage. Keyword lists will be expanded based on real usage.
