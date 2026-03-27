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
