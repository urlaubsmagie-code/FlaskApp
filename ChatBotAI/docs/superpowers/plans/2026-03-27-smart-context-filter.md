# Smart Context Filter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce AI prompt overload by filtering context to only what's relevant for each guest message, fixing wrong-topic responses on qwen3:8b.

**Architecture:** New `ContextFilter` class in `services/context_filter.py` with 4 filters (gratitude detection, already-answered detection, KB keyword filtering, guest profile filtering). Called before `generate_guest_response()` in all 3 AI code paths. Pure Python, no dependencies.

**Tech Stack:** Python, Flask, SQLAlchemy (existing stack only)

**Spec:** `docs/superpowers/specs/2026-03-27-smart-context-filter-design.md`

---

### Task 1: Create ContextFilter — keyword extraction and stop words

**Files:**
- Create: `services/context_filter.py`

This task creates the foundation: the `ContextFilter` class, `FilteredContext` dataclass, stop word lists, suffix rules, and the `_extract_keywords()` method that all filters depend on.

- [ ] **Step 1: Create `services/context_filter.py` with imports, constants, and dataclass**

```python
"""
Smart Context Filter for ChatBotAI
Filters AI prompt context to only what's relevant for each guest message.
Reduces prompt overload on small models (qwen3:8b).
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class FilteredContext:
    """Result of context filtering — only relevant context for the current message."""
    knowledge_entries: List[Dict[str, Any]]
    guest_profile: Dict[str, Any]
    property_info: Optional[Dict[str, Any]]
    corrections: List[Dict[str, Any]]
    reservation_info: Optional[Dict[str, Any]]
    resolved_topics: List[str]
    is_closing: bool
    filter_log: Dict[str, Any] = field(default_factory=dict)


class ContextFilter:
    """Filters AI context to only what's relevant for the current guest message.

    Stateless — all methods are class/static methods. Thread-safe.
    """

    # German stop words (common articles, pronouns, prepositions, verbs)
    DE_STOP_WORDS = frozenset({
        'der', 'die', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'einer', 'eines', 'einem', 'einen',
        'ich', 'du', 'er', 'sie', 'es', 'wir', 'ihr', 'mir', 'mich', 'uns', 'euch',
        'mein', 'meine', 'meinem', 'meinen', 'meiner', 'dein', 'deine', 'ihr', 'ihre',
        'und', 'oder', 'aber', 'doch', 'auch', 'noch', 'schon', 'sehr', 'ganz', 'nur', 'mal',
        'nicht', 'kein', 'keine', 'keinen', 'keinem',
        'ist', 'sind', 'war', 'hat', 'haben', 'wird', 'kann', 'muss', 'soll', 'wollen',
        'auf', 'mit', 'für', 'von', 'zu', 'zum', 'zur', 'bei', 'nach', 'vor', 'über', 'unter',
        'an', 'in', 'im', 'am', 'aus', 'bis', 'durch', 'um', 'gegen', 'ohne', 'zwischen',
        'wie', 'wo', 'was', 'wer', 'wann', 'warum', 'welche', 'welcher', 'welches',
        'bitte', 'hallo', 'guten', 'gute', 'guter', 'morgen', 'tag', 'abend',
        'danke', 'vielen', 'dank',
        'ja', 'nein', 'gut', 'okay',
        'wenn', 'dass', 'weil', 'ob', 'als', 'da', 'so', 'dann', 'denn',
        'hier', 'dort', 'jetzt', 'heute', 'morgen', 'gestern',
        'diese', 'dieser', 'dieses', 'diesem', 'diesen',
        'alle', 'alles', 'allem',
        'man', 'sich', 'werden', 'worden', 'sein', 'seine', 'seinem', 'seinen', 'seiner',
    })

    # English stop words
    EN_STOP_WORDS = frozenset({
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should',
        'may', 'might', 'shall', 'can',
        'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them',
        'my', 'your', 'his', 'its', 'our', 'their',
        'this', 'that', 'these', 'those',
        'and', 'or', 'but', 'not', 'no', 'nor',
        'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'up', 'about',
        'into', 'through', 'during', 'before', 'after', 'above', 'below', 'between',
        'how', 'where', 'what', 'who', 'when', 'why', 'which',
        'if', 'then', 'than', 'so', 'as', 'just', 'also', 'very', 'too',
        'here', 'there', 'now', 'today', 'please', 'hello', 'hi', 'hey',
        'thanks', 'thank', 'yes', 'no', 'ok', 'okay',
    })

    STOP_WORDS = DE_STOP_WORDS | EN_STOP_WORDS

    # German suffixes to strip (ordered longest first to avoid partial strips)
    DE_SUFFIXES = ['-keit', '-heit', '-nung', '-ung', '-lich', '-isch', '-nen', '-ern', '-en', '-er', '-st', '-te']
    # English suffixes
    EN_SUFFIXES = ['-tion', '-ment', '-ing', '-ely', '-ed', '-ly', '-er', '-es']

    @classmethod
    def _extract_keywords(cls, text: str) -> Set[str]:
        """Extract meaningful keywords from text.

        Returns both original tokens and stemmed versions.
        Removes stop words, punctuation, and very short tokens.
        """
        if not text:
            return set()

        # Lowercase and strip HTML
        text = re.sub(r'<[^>]+>', '', text.lower())
        # Replace punctuation with spaces (keep hyphens within words)
        text = re.sub(r'[^\w\s-]', ' ', text)
        # Split on whitespace
        tokens = text.split()

        keywords = set()
        for token in tokens:
            token = token.strip('-')
            if not token or len(token) < 3:
                continue
            if token in cls.STOP_WORDS:
                continue

            # Keep original token
            keywords.add(token)

            # Also add stemmed version
            stemmed = cls._stem(token)
            if stemmed and len(stemmed) >= 4 and stemmed != token:
                keywords.add(stemmed)

        return keywords

    @classmethod
    def _stem(cls, word: str) -> str:
        """Naive suffix stripping for German and English.

        Intentionally simple — keeps both original and stemmed for matching.
        """
        for suffix in cls.DE_SUFFIXES + cls.EN_SUFFIXES:
            clean_suffix = suffix.lstrip('-')
            if word.endswith(clean_suffix) and len(word) > len(clean_suffix) + 2:
                return word[:-len(clean_suffix)]
        return word
```

- [ ] **Step 2: Verify file is importable**

Run: `cd "C:\Users\admin\Documents\FlaskApp" && python -c "from ChatBotAI.services.context_filter import ContextFilter, FilteredContext; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add services/context_filter.py
git commit -m "feat(context-filter): add ContextFilter class with keyword extraction"
```

---

### Task 2: Filter 1 — Gratitude/Closing Detection

**Files:**
- Modify: `services/context_filter.py`

- [ ] **Step 1: Add gratitude phrases and `_detect_closing()` method**

Add after the `STOP_WORDS` constant, before `_extract_keywords`:

```python
    # Gratitude phrases that signal conversation closing (when preceded by host/AI reply)
    GRATITUDE_PHRASES = frozenset({
        # German
        'danke', 'vielen dank', 'dankeschön', 'dankeschon', 'herzlichen dank',
        'danke schön', 'danke schon', 'danke dir', 'danke sehr', 'danke ihnen',
        'super danke', 'toll danke', 'prima danke', 'perfekt danke',
        'besten dank', 'tausend dank',
        # English
        'thanks', 'thank you', 'thx', 'many thanks', 'cheers', 'appreciated',
        'thanks a lot', 'thank you so much', 'thanks so much', 'much appreciated',
        # Spanish
        'gracias', 'muchas gracias',
        # French
        'merci', 'merci beaucoup',
        # Italian
        'grazie', 'molte grazie', 'mille grazie',
    })

    @classmethod
    def _detect_closing(cls, latest_message: str, conversation_history: List[Dict[str, Any]]) -> bool:
        """Detect if the guest's message is a gratitude/closing after the host already replied.

        Returns True when the message is short gratitude AND the previous message is from host/AI.
        """
        if not latest_message or not conversation_history:
            return False

        # Clean the message
        cleaned = re.sub(r'<[^>]+>', '', latest_message).strip()
        # Remove emoji
        cleaned = re.sub(r'[\U0001F600-\U0001F9FF\U0001F300-\U0001F5FF\U00002702-\U000027B0\U0001F900-\U0001F9FF]+', '', cleaned).strip()
        # Remove emoticons like :) :D ;) etc.
        cleaned = re.sub(r'[:;][)\-D(P/\\]', '', cleaned).strip()
        # Remove trailing punctuation
        cleaned = re.sub(r'[.!,;:]+$', '', cleaned).strip()

        # Must be short (< 60 chars after cleaning)
        if len(cleaned) > 60:
            return False

        # Must contain a question mark? Then it's not a closing
        if '?' in latest_message:
            return False

        # Normalize for matching
        normalized = cleaned.lower().strip()
        if not normalized:
            return False

        # Check if it matches or starts with a gratitude phrase
        is_gratitude = False
        for phrase in cls.GRATITUDE_PHRASES:
            if normalized == phrase or normalized.startswith(phrase + ' ') or normalized.startswith(phrase + ','):
                is_gratitude = True
                break

        if not is_gratitude:
            return False

        # Check if the previous message is from host or AI
        if len(conversation_history) < 2:
            return False

        # Find the message just before the latest guest message
        # Walk backwards: the last message should be the guest's gratitude
        for i in range(len(conversation_history) - 2, -1, -1):
            msg = conversation_history[i]
            sender = msg.get('sender_type', '')
            if sender in ('owner', 'ai'):
                return True
            elif sender == 'guest':
                # Another guest message before the gratitude, no host reply in between
                return False

        return False
```

- [ ] **Step 2: Verify it works**

Run: `cd "C:\Users\admin\Documents\FlaskApp" && python -c "
from ChatBotAI.services.context_filter import ContextFilter
history = [
    {'sender_type': 'guest', 'content': 'Wo sind die Anzünder?'},
    {'sender_type': 'owner', 'content': 'Im Schrank bei der Sauna'},
    {'sender_type': 'guest', 'content': 'Danke :)'},
]
print('closing:', ContextFilter._detect_closing('Danke :)', history))
print('not closing:', ContextFilter._detect_closing('Wo ist das WiFi?', history))
"`
Expected: `closing: True` and `not closing: False`

- [ ] **Step 3: Commit**

```bash
git add services/context_filter.py
git commit -m "feat(context-filter): add gratitude/closing detection (Filter 1)"
```

---

### Task 3: Filter 2 — Already-Answered Detection

**Files:**
- Modify: `services/context_filter.py`

- [ ] **Step 1: Add `_detect_resolved_topics()` method**

Add after `_detect_closing`:

```python
    @classmethod
    def _detect_resolved_topics(cls, conversation_history: List[Dict[str, Any]]) -> List[str]:
        """Scan conversation history to find guest topics that were already answered.

        Returns a list of short topic labels for resolved Q&A pairs.
        """
        resolved = []

        for i, msg in enumerate(conversation_history):
            if msg.get('sender_type') != 'guest':
                continue

            content = msg.get('content', '')
            if not content:
                continue

            # Strip HTML
            content = re.sub(r'<[^>]+>', '', content).strip()

            # Skip very short messages (acknowledgments, greetings)
            if len(content) < 15:
                continue

            # Check if a host/AI message follows this guest message
            has_reply = False
            for j in range(i + 1, len(conversation_history)):
                next_sender = conversation_history[j].get('sender_type', '')
                if next_sender in ('owner', 'ai'):
                    has_reply = True
                    break
                elif next_sender == 'guest':
                    # Another guest message before a reply — keep checking
                    # (the reply might come after multiple guest messages)
                    continue

            if has_reply:
                # Extract topic label: strip stop words, keep first ~60 chars
                topic_keywords = cls._extract_keywords(content)
                if topic_keywords:
                    # Take up to 5 keywords, sorted by position in original text
                    words = content.lower().split()
                    ordered_keywords = [w for w in words if w.strip('.,!?:;') in topic_keywords][:5]
                    topic = ' '.join(ordered_keywords) if ordered_keywords else content[:60]
                    if topic and len(topic) > 3:
                        resolved.append(topic)

        return resolved
```

- [ ] **Step 2: Verify it works**

Run: `cd "C:\Users\admin\Documents\FlaskApp" && python -c "
from ChatBotAI.services.context_filter import ContextFilter
history = [
    {'sender_type': 'guest', 'content': 'Wann ist der Check-in möglich?'},
    {'sender_type': 'owner', 'content': 'Ab 15:00 Uhr.'},
    {'sender_type': 'guest', 'content': 'Wo sind die Anzünder und Pellets für die Sauna?'},
    {'sender_type': 'owner', 'content': 'Im Schrank bei der Sauna.'},
    {'sender_type': 'guest', 'content': 'Danke :)'},
]
topics = ContextFilter._detect_resolved_topics(history)
print('resolved topics:', topics)
"`
Expected: Two resolved topics containing keywords about check-in and sauna

- [ ] **Step 3: Commit**

```bash
git add services/context_filter.py
git commit -m "feat(context-filter): add already-answered detection (Filter 2)"
```

---

### Task 4: Filter 3 — Knowledge Base Filtering

**Files:**
- Modify: `services/context_filter.py`

- [ ] **Step 1: Add `_filter_knowledge_entries()` method**

Add after `_detect_resolved_topics`:

```python
    @classmethod
    def _filter_knowledge_entries(
        cls,
        entries: List[Dict[str, Any]],
        message_keywords: Set[str],
        max_entries: int = 5
    ) -> List[Dict[str, Any]]:
        """Filter KB entries by keyword relevance to the guest's message.

        Scores each entry and returns only matching ones (top N by score).
        Falls back to FAQ/general entries if nothing matches.
        """
        if not entries or not message_keywords:
            # No keywords extracted — return up to 3 fallback entries
            return cls._fallback_entries(entries, 3)

        scored = []
        for entry in entries:
            score = cls._score_entry(entry, message_keywords)
            if score > 0:
                scored.append((score, entry))

        if not scored:
            # No matches — return fallback entries
            return cls._fallback_entries(entries, 3)

        # Sort by score descending, take top N
        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:max_entries]]

    @classmethod
    def _score_entry(cls, entry: Dict[str, Any], keywords: Set[str]) -> int:
        """Score a KB entry by keyword overlap.

        +2 for exact token match in label
        +1 for exact token match in value
        +1 for substring match in label or value (keyword length >= 4)
        """
        label = entry.get('label', '').lower()
        value = entry.get('value', '').lower()

        # Tokenize label and value
        label_tokens = set(re.split(r'[\s/,;:.()\-]+', label))
        value_tokens = set(re.split(r'[\s/,;:.()\-]+', value))

        score = 0
        for kw in keywords:
            if kw in label_tokens:
                score += 2
            if kw in value_tokens:
                score += 1
            # Substring match (only for keywords >= 4 chars to reduce noise)
            if len(kw) >= 4:
                if kw in label and kw not in label_tokens:
                    score += 1
                if kw in value and kw not in value_tokens:
                    score += 1

        return score

    @classmethod
    def _fallback_entries(cls, entries: List[Dict[str, Any]], max_entries: int = 3) -> List[Dict[str, Any]]:
        """Return a small set of fallback entries (FAQ and general categories)."""
        fallback = [e for e in entries if e.get('category') in ('faq', 'general')]
        return fallback[:max_entries]
```

- [ ] **Step 2: Verify it works**

Run: `cd "C:\Users\admin\Documents\FlaskApp" && python -c "
from ChatBotAI.services.context_filter import ContextFilter
entries = [
    {'label': 'Parkkarte', 'value': 'Liegt auf dem Schreibtisch im Flur', 'category': 'general'},
    {'label': 'Check-in', 'value': 'Ab 15:00 Uhr, Schlüsselkasten Code 1234', 'category': 'checkin_checkout'},
    {'label': 'WiFi', 'value': 'Netzwerk: Haus5, Passwort: geheim123', 'category': 'general'},
    {'label': 'Sauna', 'value': 'Brennholz unter dem Balkon, Anzünder im Schrank', 'category': 'faq'},
    {'label': 'Müll', 'value': 'Gelbe Tonne Montags, Restmüll Mittwochs', 'category': 'house_rules'},
]
keywords = ContextFilter._extract_keywords('Wo finde ich die Parkkarte?')
print('keywords:', keywords)
result = ContextFilter._filter_knowledge_entries(entries, keywords)
print('filtered:', [e['label'] for e in result])
"`
Expected: Keywords include `parkkarte`/`park`/`finde`, filtered result includes "Parkkarte" entry

- [ ] **Step 3: Commit**

```bash
git add services/context_filter.py
git commit -m "feat(context-filter): add KB keyword filtering (Filter 3)"
```

---

### Task 5: Filter 4 — Guest Profile Filtering

**Files:**
- Modify: `services/context_filter.py`

- [ ] **Step 1: Add `_filter_guest_profile()` method**

Add after `_fallback_entries`:

```python
    # Keywords that trigger including specific profile sections
    PROFILE_TRIGGERS = {
        'allergies': frozenset({
            'food', 'essen', 'restaurant', 'küche', 'kuche', 'cook', 'kochen',
            'diet', 'diät', 'diat', 'allergi', 'unverträg', 'unvertrag',
            'glutenfrei', 'laktose', 'vegan', 'vegetarisch', 'lebensmittel',
            'frühstück', 'fruhstuck', 'breakfast', 'lunch', 'dinner', 'abendessen',
            'mittag',
        }),
        'pets': frozenset({
            'hund', 'hunde', 'katze', 'katzen', 'dog', 'dogs', 'cat', 'cats',
            'pet', 'pets', 'tier', 'tiere', 'haustier', 'haustiere', 'welpe',
            'puppy', 'animal',
        }),
        'family': frozenset({
            'kind', 'kinder', 'baby', 'babys', 'babies', 'familie', 'family',
            'child', 'children', 'kids', 'kleinkind', 'toddler', 'teenager',
            'tochter', 'sohn', 'daughter', 'son',
        }),
    }

    @classmethod
    def _filter_guest_profile(
        cls,
        profile: Dict[str, Any],
        message_keywords: Set[str],
        latest_message: str
    ) -> Dict[str, Any]:
        """Filter guest profile to only include sections relevant to the message.

        Always includes: name, booking, total_stays, special_requests
        Conditionally includes: allergies, pets, family, preferences, interests
        Fallback: include everything if message is long or has no clear topic.
        """
        if not profile:
            return profile

        # Fallback: include everything for long/unclear messages
        cleaned_message = re.sub(r'<[^>]+>', '', latest_message or '').strip()
        if len(cleaned_message) > 100:
            return profile

        # If no keywords at all, include everything (safe default)
        if not message_keywords:
            return profile

        # Start with always-included fields
        filtered = {}
        for key in ('name', 'booking', 'total_stays', 'special_requests', 'language'):
            if key in profile:
                filtered[key] = profile[key]

        # Check each conditional section
        lowered_message = cleaned_message.lower()

        for section, trigger_words in cls.PROFILE_TRIGGERS.items():
            if section not in profile or not profile[section]:
                continue

            # Check if any trigger word appears in the message (substring match)
            include = False
            for trigger in trigger_words:
                if trigger in lowered_message:
                    include = True
                    break
            # Also check keyword overlap
            if not include and message_keywords & trigger_words:
                include = True

            if include:
                filtered[section] = profile[section]

        # Preferences and interests: include if any keyword overlaps with stored values
        for section in ('preferences', 'interests'):
            if section not in profile or not profile[section]:
                continue
            for item in profile[section]:
                item_text = f"{item.get('key', '')} {item.get('value', '')}".lower()
                if any(kw in item_text for kw in message_keywords):
                    filtered[section] = profile[section]
                    break

        return filtered
```

- [ ] **Step 2: Verify it works**

Run: `cd "C:\Users\admin\Documents\FlaskApp" && python -c "
from ChatBotAI.services.context_filter import ContextFilter
profile = {
    'name': 'Ben Höhne',
    'booking': [{'key': 'check_in', 'value': '2026-03-25'}],
    'family': [{'key': 'children', 'value': '2 kids'}],
    'pets': [{'key': 'dog', 'value': 'Golden Retriever'}],
    'allergies': [{'key': 'nuts', 'value': 'severe'}],
    'special_requests': [{'value': 'Late check-out'}],
}
kw = ContextFilter._extract_keywords('Wo finde ich die Parkkarte?')
result = ContextFilter._filter_guest_profile(profile, kw, 'Wo finde ich die Parkkarte?')
print('sections:', list(result.keys()))
print('no pets:', 'pets' not in result)
print('no allergies:', 'allergies' not in result)
print('has name:', 'name' in result)
"`
Expected: Only name, booking, special_requests — no pets, no allergies, no family

- [ ] **Step 3: Commit**

```bash
git add services/context_filter.py
git commit -m "feat(context-filter): add guest profile filtering (Filter 4)"
```

---

### Task 6: Main `filter()` entry point

**Files:**
- Modify: `services/context_filter.py`

- [ ] **Step 1: Add the `filter()` class method**

Add as the first method of the class (right after the class constants, before `_detect_closing`):

```python
    @classmethod
    def filter(
        cls,
        latest_message: str,
        conversation_history: List[Dict[str, Any]],
        knowledge_entries: Optional[List[Dict[str, Any]]] = None,
        guest_profile: Optional[Dict[str, Any]] = None,
        property_info: Optional[Dict[str, Any]] = None,
        corrections: Optional[List[Dict[str, Any]]] = None,
        reservation_info: Optional[Dict[str, Any]] = None,
    ) -> FilteredContext:
        """Main entry point: filter all context for relevance to the latest message.

        Applies 4 filters in sequence:
        1. Gratitude/closing detection — strips all context for thank-you messages
        2. Already-answered detection — identifies resolved topics
        3. KB keyword filtering — only relevant KB entries
        4. Guest profile filtering — only relevant profile sections
        """
        knowledge_entries = knowledge_entries or []
        guest_profile = guest_profile or {}
        corrections = corrections or []

        # Filter 1: Gratitude/closing detection
        is_closing = cls._detect_closing(latest_message, conversation_history)

        if is_closing:
            # Strip all context — return minimal profile (name only)
            minimal_profile = {}
            if 'name' in guest_profile:
                minimal_profile['name'] = guest_profile['name']

            log = {
                'is_closing': True,
                'keywords': [],
                'kb_total': len(knowledge_entries),
                'kb_kept': 0,
                'kb_kept_labels': [],
                'profile_sections_kept': list(minimal_profile.keys()),
                'resolved_topics_count': 0,
                'corrections_total': len(corrections),
                'corrections_kept': 0,
            }
            logger.debug(
                f"[CONTEXT FILTER] message='{latest_message[:50]}' | "
                f"is_closing=True | skipped all context"
            )

            return FilteredContext(
                knowledge_entries=[],
                guest_profile=minimal_profile,
                property_info=None,
                corrections=[],
                reservation_info=None,
                resolved_topics=[],
                is_closing=True,
                filter_log=log,
            )

        # Extract keywords from the latest message (used by Filters 3 and 4)
        message_keywords = cls._extract_keywords(latest_message)

        # Filter 2: Already-answered detection
        resolved_topics = cls._detect_resolved_topics(conversation_history)

        # Filter 3: Knowledge base filtering
        filtered_kb = cls._filter_knowledge_entries(knowledge_entries, message_keywords)

        # Filter 4: Guest profile filtering
        filtered_profile = cls._filter_guest_profile(guest_profile, message_keywords, latest_message)

        # Corrections: keep as-is for now (they're already limited to 10 by the caller)
        filtered_corrections = corrections

        log = {
            'is_closing': False,
            'keywords': list(message_keywords)[:10],
            'kb_total': len(knowledge_entries),
            'kb_kept': len(filtered_kb),
            'kb_kept_labels': [e.get('label', '?') for e in filtered_kb],
            'profile_sections_kept': list(filtered_profile.keys()),
            'resolved_topics_count': len(resolved_topics),
            'corrections_total': len(corrections),
            'corrections_kept': len(filtered_corrections),
        }
        logger.debug(
            f"[CONTEXT FILTER] message='{latest_message[:50]}' | "
            f"kb={len(filtered_kb)}/{len(knowledge_entries)} entries | "
            f"profile={','.join(filtered_profile.keys())} | "
            f"resolved={len(resolved_topics)} topics | "
            f"keywords={','.join(list(message_keywords)[:5])}"
        )

        return FilteredContext(
            knowledge_entries=filtered_kb,
            guest_profile=filtered_profile,
            property_info=property_info,
            corrections=filtered_corrections,
            reservation_info=reservation_info,
            resolved_topics=resolved_topics,
            is_closing=False,
            filter_log=log,
        )
```

- [ ] **Step 2: Verify full pipeline works**

Run: `cd "C:\Users\admin\Documents\FlaskApp" && python -c "
from ChatBotAI.services.context_filter import ContextFilter

# Test 1: Closing detection
history = [
    {'sender_type': 'guest', 'content': 'Wo sind die Anzünder?'},
    {'sender_type': 'owner', 'content': 'Im Schrank bei der Sauna.'},
    {'sender_type': 'guest', 'content': 'Danke :)'},
]
r = ContextFilter.filter('Danke :)', history, knowledge_entries=[{'label': 'WiFi', 'value': 'pass123', 'category': 'general'}])
print('Test 1 - closing:', r.is_closing, '| kb:', len(r.knowledge_entries), '| profile:', r.guest_profile)

# Test 2: Normal message with KB filtering
entries = [
    {'label': 'Parkkarte', 'value': 'Auf dem Schreibtisch', 'category': 'general'},
    {'label': 'Check-in', 'value': 'Ab 15 Uhr', 'category': 'checkin_checkout'},
    {'label': 'WiFi', 'value': 'Passwort geheim', 'category': 'general'},
]
profile = {'name': 'Ben', 'pets': [{'key': 'dog', 'value': 'Rex'}], 'booking': []}
r = ContextFilter.filter('Wo finde ich die Parkkarte?', history, knowledge_entries=entries, guest_profile=profile)
print('Test 2 - kb:', [e['label'] for e in r.knowledge_entries], '| pets in profile:', 'pets' in r.guest_profile)
"`
Expected: Test 1 shows closing=True, empty KB. Test 2 shows only Parkkarte in KB, no pets in profile.

- [ ] **Step 3: Commit**

```bash
git add services/context_filter.py
git commit -m "feat(context-filter): add main filter() entry point"
```

---

### Task 7: Integrate into `ai_service.py` — new parameters and closing prompt

**Files:**
- Modify: `services/ai_service.py:410-460` (generate_guest_response signature)
- Modify: `services/ai_service.py:629-760` (_build_chat_messages)

- [ ] **Step 1: Add `resolved_topics` and `is_closing` params to `generate_guest_response()`**

In `services/ai_service.py`, change the method signature and the internal call:

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
            knowledge_entries: Optional[List[Dict[str, Any]]] = None,
            conversation_summary: Optional[str] = None,
            corrections: Optional[List[Dict[str, Any]]] = None,
            resolved_topics: Optional[List[str]] = None,
            is_closing: bool = False
    ) -> Optional[str]:
```

And update the `_build_chat_messages` call inside it to pass through:

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
            knowledge_entries=knowledge_entries,
            conversation_summary=conversation_summary,
            corrections=corrections,
            resolved_topics=resolved_topics,
            is_closing=is_closing
        )
```

- [ ] **Step 2: Add `resolved_topics` and `is_closing` params to `_build_chat_messages()`**

Change the method signature:

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
            knowledge_entries: Optional[List[Dict[str, Any]]] = None,
            conversation_summary: Optional[str] = None,
            corrections: Optional[List[Dict[str, Any]]] = None,
            resolved_topics: Optional[List[str]] = None,
            is_closing: bool = False
    ) -> List[Dict[str, str]]:
```

- [ ] **Step 3: Add closing prompt shortcut at the top of `_build_chat_messages()`**

Add right after the method docstring and `messages = []` (line ~652), before the existing system prompt building:

```python
        # Shortcut: for closing/gratitude messages, use a minimal prompt
        if is_closing:
            guest_name = guest_profile.get('name', 'the guest') if guest_profile else 'the guest'
            closing_system = (
                f"You are a vacation rental host. The guest ({guest_name}) is thanking you "
                "for your help. Reply briefly and warmly in the SAME LANGUAGE as the guest's message. "
                "Keep it to 1-2 sentences. Do NOT bring up any other topics."
            )
            messages.append({'role': 'system', 'content': closing_system})
            clean_latest = self._strip_html(latest_message)
            clean_latest = self._strip_email_quotes(clean_latest)
            messages.append({'role': 'user', 'content': clean_latest or latest_message.strip()})
            return messages
```

- [ ] **Step 4: Add resolved topics injection in the system prompt**

In `_build_chat_messages()`, find the section where `conversation_summary` is added (around line 748-753). Add the resolved topics section BEFORE the conversation summary, and modify the summary trailer:

```python
        if resolved_topics:
            topics_text = "\n".join(f"- {topic}" for topic in resolved_topics[:8])
            system_parts.append(
                f"\n=== ALREADY RESOLVED (do NOT address these topics again) ===\n"
                f"{topics_text}\n==="
            )

        if conversation_summary:
            # When resolved_topics are explicit, drop the generic "already resolved" trailer
            if resolved_topics:
                system_parts.append(
                    f"\n=== CONVERSATION SUMMARY (older messages, for background only) ===\n"
                    f"{conversation_summary}\n==="
                )
            else:
                system_parts.append(
                    f"\n=== CONVERSATION SUMMARY (older messages, for background only) ===\n"
                    f"{conversation_summary}\n"
                    f"=== These topics are ALREADY RESOLVED. Do NOT bring them up again unless the guest's latest message asks about them. ==="
                )
```

This replaces the existing conversation_summary block (lines 748-753 in current code).

- [ ] **Step 5: Verify the module still imports cleanly**

Run: `cd "C:\Users\admin\Documents\FlaskApp" && python -c "from ChatBotAI.services.ai_service import AIService; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add services/ai_service.py
git commit -m "feat(context-filter): add resolved_topics and is_closing params to AI service"
```

---

### Task 8: Fix bugs in routes.py and integrate ContextFilter

**Files:**
- Modify: `routes.py:804-834` (api_generate_ai_response KB query + generate call)
- Modify: `routes.py:919-1045` (api_suggest_ai_response — missing summary, corrections, KB bug, draft filter, context filter)

This is the biggest integration task. It fixes 4 bugs and adds the ContextFilter to both route endpoints:
- Bug 1: KB query missing `category != 'correction'` filter (both endpoints)
- Bug 2: `api_generate_ai_response` missing `conversation_summary` and `corrections`
- Bug 3: `api_suggest_ai_response` missing `conversation_summary` and `corrections`
- Bug 4: `api_suggest_ai_response` messages query includes pending/rejected drafts (should filter like generate endpoint)

- [ ] **Step 1: Fix `api_generate_ai_response` — add correction category filter to KB query**

In `routes.py`, around line 809, change the KB query to exclude corrections (matching message_router behavior):

Replace:
```python
                knowledge_entries = [e.to_dict() for e in
                                    KnowledgeEntry.query.filter(
                                        db.or_(
                                            KnowledgeEntry.property_id.is_(None),
                                            KnowledgeEntry.property_id == conversation.property_id
                                        )
                                    ).order_by(KnowledgeEntry.category, KnowledgeEntry.sort_order).all()]
            else:
                knowledge_entries = [e.to_dict() for e in
                                    KnowledgeEntry.query.filter_by(property_id=None)
                                    .order_by(KnowledgeEntry.category, KnowledgeEntry.sort_order).all()]
```

With:
```python
                knowledge_entries = [e.to_dict() for e in
                                    KnowledgeEntry.query.filter(
                                        KnowledgeEntry.category != 'correction',
                                        db.or_(
                                            KnowledgeEntry.property_id.is_(None),
                                            KnowledgeEntry.property_id == conversation.property_id
                                        )
                                    ).order_by(KnowledgeEntry.category, KnowledgeEntry.sort_order).all()]
            else:
                knowledge_entries = [e.to_dict() for e in
                                    KnowledgeEntry.query.filter(
                                        KnowledgeEntry.category != 'correction'
                                    ).filter_by(property_id=None)
                                    .order_by(KnowledgeEntry.category, KnowledgeEntry.sort_order).all()]
```

- [ ] **Step 2: Add ContextFilter + corrections to `api_generate_ai_response`**

After the KB loading block (~line 820) and before the `generate_guest_response` call, add corrections loading and the ContextFilter:

```python
        # Load corrections
        corrections = []
        try:
            correction_query = KnowledgeEntry.query.filter_by(category='correction')
            if conversation.property_id:
                property_corrections = correction_query.filter_by(
                    property_id=conversation.property_id
                ).order_by(KnowledgeEntry.created_at.desc()).limit(7).all()
                global_corrections = KnowledgeEntry.query.filter_by(
                    category='correction', property_id=None
                ).order_by(KnowledgeEntry.created_at.desc()).limit(3).all()
                corrections = [c.to_dict() for c in property_corrections + global_corrections]
            else:
                corrections = [c.to_dict() for c in
                               correction_query.filter_by(property_id=None)
                               .order_by(KnowledgeEntry.created_at.desc()).limit(10).all()]
        except Exception as e:
            logger.warning(f"Failed to load corrections: {e}")

        # Load conversation summary (ai_summary is a column on Conversation model)
        conversation_summary = conversation.ai_summary

        # Apply context filter
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
        logger.debug(f"[CONTEXT FILTER] generate: {filtered.filter_log}")
```

Then update the `generate_guest_response` call to use filtered context:

```python
        ai_response = ai_service.generate_guest_response(
            guest_profile=filtered.guest_profile,
            conversation_history=[m.to_dict() for m in messages],
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
            resolved_topics=filtered.resolved_topics,
            is_closing=filtered.is_closing,
        )
```

- [ ] **Step 3: Fix `api_suggest_ai_response` messages query to exclude pending/rejected drafts**

At line 948, replace:
```python
        messages = conversation.messages.order_by(Message.sent_at.desc()).limit(max_history).all()
```

With (matching the generate endpoint's pattern):
```python
        messages = conversation.messages.filter(
            db.or_(Message.approval_status.is_(None), Message.approval_status == 'approved')
        ).order_by(Message.sent_at.desc()).limit(max_history).all()
```

- [ ] **Step 4: Fix `api_suggest_ai_response` KB query to exclude corrections**

Same pattern as Step 1 — add `KnowledgeEntry.category != 'correction'` to both branches of the KB query (around line 993-1005).

- [ ] **Step 5: Add corrections, summary, and ContextFilter to `api_suggest_ai_response`**

After the KB loading block (~line 1006) and before the `generate_guest_response` call, add:

```python
        # Load corrections
        corrections = []
        try:
            correction_query = KnowledgeEntry.query.filter_by(category='correction')
            if conversation.property_id:
                property_corrections = correction_query.filter_by(
                    property_id=conversation.property_id
                ).order_by(KnowledgeEntry.created_at.desc()).limit(7).all()
                global_corrections = KnowledgeEntry.query.filter_by(
                    category='correction', property_id=None
                ).order_by(KnowledgeEntry.created_at.desc()).limit(3).all()
                corrections = [c.to_dict() for c in property_corrections + global_corrections]
            else:
                corrections = [c.to_dict() for c in
                               correction_query.filter_by(property_id=None)
                               .order_by(KnowledgeEntry.created_at.desc()).limit(10).all()]
        except Exception as e:
            logger.warning(f"Failed to load corrections: {e}")

        # Load conversation summary
        conversation_summary = conversation.ai_summary

        # Apply context filter
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
        logger.debug(f"[CONTEXT FILTER] suggest: {filtered.filter_log}")
```

Then replace the existing `generate_guest_response` call (lines 1010-1021) with:

```python
        ai_response = ai_service.generate_guest_response(
            guest_profile=filtered.guest_profile,
            conversation_history=[m.to_dict() for m in messages],
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
            resolved_topics=filtered.resolved_topics,
            is_closing=filtered.is_closing,
        )
```

And update the debug context to include filter info:

```python
        if include_debug:
            result['debug_context'] = {
                'latest_guest_message': latest_guest_message.content,
                'messages_count': len(messages),
                'messages_used': [
                    {'sender': m.sender_type, 'preview': m.content[:100]} for m in messages
                ],
                'guest_profile': filtered.guest_profile if profile else None,
                'property': property_info.get('name') if property_info else None,
                'reservation': bool(reservation_info),
                'tone': tone,
                'has_host_instructions': bool(host_instructions and host_instructions.strip()),
                'conversation_subject': conversation.subject,
                'context_filter': filtered.filter_log,
            }
```

- [ ] **Step 4: Verify routes.py still imports**

Run: `cd "C:\Users\admin\Documents\FlaskApp" && python -c "from ChatBotAI.routes import chatbot_bp; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add routes.py services/context_filter.py
git commit -m "feat(context-filter): integrate filter into routes.py, fix KB correction bug, add missing summary/corrections"
```

---

### Task 9: Integrate ContextFilter into message_router.py

**Files:**
- Modify: `services/message_router.py:596-610` (_generate_ai_response, before generate_guest_response call)

- [ ] **Step 1: Add ContextFilter call before `generate_guest_response()`**

In `services/message_router.py`, find the `generate_guest_response` call around line 597. Add the filter call before it:

```python
        # Apply context filter
        from .context_filter import ContextFilter
        filtered = ContextFilter.filter(
            latest_message=trigger_message.content,
            conversation_history=[m.to_dict() for m in messages],
            knowledge_entries=knowledge_entries,
            guest_profile=profile,
            property_info=property_info,
            corrections=corrections,
            reservation_info=reservation_info,
        )
        logger.debug(f"[CONTEXT FILTER] auto-respond: {filtered.filter_log}")

        # Generate response
        response_text = self.ai_service.generate_guest_response(
            guest_profile=filtered.guest_profile,
            conversation_history=[m.to_dict() for m in messages],
            latest_message=trigger_message.content,
            property_info=filtered.property_info,
            tone=tone,
            host_instructions=host_instructions,
            conversation_subject=conversation.subject,
            max_history=max_history,
            reservation_info=filtered.reservation_info,
            knowledge_entries=filtered.knowledge_entries,
            conversation_summary=conversation_summary,
            corrections=filtered.corrections,
            resolved_topics=filtered.resolved_topics,
            is_closing=filtered.is_closing,
        )
```

This replaces the existing `generate_guest_response` call (lines 597-610).

- [ ] **Step 2: Verify message_router still imports**

Run: `cd "C:\Users\admin\Documents\FlaskApp" && python -c "from ChatBotAI.services.message_router import MessageRouter; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add services/message_router.py
git commit -m "feat(context-filter): integrate filter into message_router auto-respond path"
```

---

### Task 10: Register in services/__init__.py

**Files:**
- Modify: `services/__init__.py`

- [ ] **Step 1: Add ContextFilter import**

Add to `services/__init__.py`:

```python
from .context_filter import ContextFilter
```

And add `'ContextFilter'` to the `__all__` list.

- [ ] **Step 2: Commit**

```bash
git add services/__init__.py
git commit -m "feat(context-filter): register ContextFilter in services __init__"
```

---

### Task 11: End-to-end manual testing

**Files:** None (testing only)

- [ ] **Step 1: Start the development server**

Run: `cd "C:\Users\admin\Documents\FlaskApp" && python -m ChatBotAI.run`
Verify: Server starts without errors on port 5000

- [ ] **Step 2: Test KI-Vorschlag on a conversation with a "Danke" message**

Open a conversation where the last guest message is a thank-you after a host reply. Click "KI-Vorschlag". Verify the AI gives a short, warm reply without mentioning irrelevant topics.

- [ ] **Step 3: Test KI-Vorschlag on a specific topic question**

Open a conversation where the guest asks about a specific topic (parking, WiFi, etc.) that has a KB entry. Click "KI-Vorschlag". Verify the AI answers about the right topic, not check-in or other irrelevant KB entries.

- [ ] **Step 4: Test KI-Vorschlag on a general question (no KB match)**

Open a conversation where the guest asks something not in the KB. Verify the AI still generates a reasonable response (using fallback KB entries or saying "I'll check").

- [ ] **Step 5: Test auto-respond path (message_router)**

If possible, trigger an auto-respond by having a conversation with AI enabled and auto-respond on. Send a test guest message via the test API. Verify the context filter runs (check logs for `[CONTEXT FILTER] auto-respond:`).

- [ ] **Step 6: Check server logs for CONTEXT FILTER debug lines**

Look for `[CONTEXT FILTER]` lines in the console output to verify the filter is running and logging correctly.

- [ ] **Step 7: Commit any fixes from testing**

```bash
git add -A
git commit -m "fix(context-filter): adjustments from manual testing"
```
