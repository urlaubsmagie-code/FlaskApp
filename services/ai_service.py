"""
AI Service for ChatBotAI
Handles all interactions with Ollama for response generation and information extraction
"""

import json
import logging
import re
import time
import threading
from datetime import datetime, timezone
import requests
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)


class AIService:
    """Service for interacting with Ollama AI"""

    # Pure acknowledgment phrases that don't need a response.
    # NOT including gratitude (thanks, danke, etc.) — those deserve a reply.
    ACKNOWLEDGMENT_PHRASES = frozenset({
        # English
        'ok', 'okay', 'k', 'alright', 'all right', 'got it', 'noted',
        'understood', 'will do', 'sounds good', 'sounds great', 'cool',
        'nice', 'yep', 'yup', 'right', 'good', 'great', 'perfect',
        'fine', 'sure', 'absolutely',
        # German
        'gut', 'alles klar', 'in ordnung', 'verstanden', 'passt',
        'genau', 'stimmt', 'geht klar', 'wird gemacht', 'klar',
        'jo', 'jep', 'super', 'prima', 'top', 'perfekt', 'schön',
        # Spanish
        'vale', 'bien', 'de acuerdo', 'entendido', 'perfecto', 'claro',
        # French
        "d'accord", 'entendu', 'compris', 'parfait',
        # Italian
        'va bene', 'capito', 'inteso', 'perfetto', 'bene',
    })

    def __init__(self, ollama_url: str = 'http://localhost:11434', model: str = 'gemma2:9b', timeout: int = 120):
        self.ollama_url = ollama_url
        self.model = model
        self.timeout = timeout
        self.chat_endpoint = f"{ollama_url}/api/chat"
        self.generate_endpoint = f"{ollama_url}/api/generate"
        # Semaphore to serialize AI calls — prevents concurrent GPU crashes
        self._semaphore = threading.Semaphore(1)

    @staticmethod
    def is_acknowledgment(message: str) -> bool:
        """Check if a message is a pure acknowledgment that doesn't need a response.

        Returns True for short, content-free closers like 'Ok', 'Gut', 'Alright'.
        Returns False for gratitude ('Thanks'), questions, or messages with substance.
        """
        if not message:
            return False

        # Strip HTML and clean
        cleaned = re.sub(r'<[^>]+>', '', message).strip()
        # Remove trailing punctuation (. ! ,) but keep ? (indicates a question)
        cleaned = re.sub(r'[.!,;:]+$', '', cleaned).strip()

        # If it contains a question mark, it's not a pure acknowledgment
        if '?' in cleaned:
            return False

        # Too long to be a pure acknowledgment (allow some emoji/punctuation padding)
        if len(cleaned) > 40:
            return False

        # Normalize and check against known phrases
        normalized = cleaned.lower().strip()
        if normalized in AIService.ACKNOWLEDGMENT_PHRASES:
            return True

        # Check with common emoji stripped (guest might send "Ok 👍")
        no_emoji = re.sub(r'[\U0001F600-\U0001F9FF\U0001F300-\U0001F5FF\U00002702-\U000027B0]+', '', normalized).strip()
        if no_emoji and no_emoji in AIService.ACKNOWLEDGMENT_PHRASES:
            return True

        return False

    def test_connection(self) -> bool:
        """Test if Ollama server is reachable and model is available"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = [m.get('name', '') for m in models]
                if any(self.model in name for name in model_names):
                    logger.info(f"Ollama connection successful. Model {self.model} available.")
                    return True
                logger.warning(f"Model {self.model} not found. Available: {model_names}")
                return False
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama connection failed: {e}")
            return False

    def get_installed_models(self) -> List[Dict[str, Any]]:
        """Get list of models installed in Ollama"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                result = []
                for m in models:
                    name = m.get('name', '')
                    size_bytes = m.get('size', 0)
                    size_gb = round(size_bytes / (1024 ** 3), 1)
                    result.append({
                        'name': name,
                        'size_gb': size_gb,
                        'parameter_size': m.get('details', {}).get('parameter_size', ''),
                        'family': m.get('details', {}).get('family', ''),
                        'quantization': m.get('details', {}).get('quantization_level', ''),
                        'is_active': self.model in name or name in self.model,
                    })
                return result
            return []
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get models: {e}")
            return []

    def change_model(self, model_name: str, preload: bool = False) -> Dict[str, Any]:
        """Change the active model, optionally preloading it first.

        Args:
            model_name: Name of the model to switch to
            preload: If True, send a warmup request to verify the model loads

        Returns:
            Dict with 'success' bool and optional 'error' message
        """
        old_model = self.model
        self.model = model_name

        if preload:
            result = self._preload_model()
            if not result['success']:
                # Revert to old model
                self.model = old_model
                logger.warning(f"Model preload failed for {model_name}, reverting to {old_model}: {result['error']}")
                return result

        logger.info(f"AI model changed from {old_model} to {model_name}")
        return {'success': True}

    def _preload_model(self, timeout: int = 60) -> Dict[str, Any]:
        """Send a minimal request to force Ollama to load the model into memory.

        Returns:
            Dict with 'success' bool and optional 'error' message
        """
        try:
            logger.info(f"Preloading model {self.model}...")
            response = requests.post(
                self.chat_endpoint,
                json={
                    'model': self.model,
                    'messages': [{'role': 'user', 'content': 'Hi'}],
                    'stream': False,
                    'options': {
                        'num_predict': 1,  # Generate just 1 token to minimize work
                    }
                },
                timeout=timeout
            )

            if response.status_code == 200:
                logger.info(f"Model {self.model} preloaded successfully")
                return {'success': True}
            else:
                error_text = response.text[:200]
                logger.error(f"Model preload failed ({response.status_code}): {error_text}")
                return {'success': False, 'error': f'Ollama returned {response.status_code}: {error_text}'}

        except requests.exceptions.Timeout:
            return {'success': False, 'error': f'Model took too long to load (>{timeout}s). It may be too large for your system.'}
        except requests.exceptions.ConnectionError:
            return {'success': False, 'error': 'Lost connection to Ollama. The model may have caused an out-of-memory crash.'}
        except requests.exceptions.RequestException as e:
            return {'success': False, 'error': f'Request failed: {e}'}

    def generate_response(self, prompt: str, system: Optional[str] = None, timeout: Optional[int] = None) -> Optional[str]:
        """
        Generate a response from the AI model using the chat API.

        Args:
            prompt: The user message to send to the model
            system: Optional system message for context
            timeout: Optional timeout override

        Returns:
            Generated response text or None on failure
        """
        messages = []
        if system:
            messages.append({'role': 'system', 'content': system})
        messages.append({'role': 'user', 'content': prompt})

        return self._call_chat_api(messages, timeout)

    def _call_chat_api(self, messages: List[Dict[str, str]], timeout: Optional[int] = None) -> Optional[str]:
        """
        Call the Ollama chat API with a full messages array.
        Uses a semaphore to serialize calls (prevents GPU crashes with concurrent users).
        Retries up to 2 times on transient failures with backoff.

        Args:
            messages: List of {role, content} message dicts
            timeout: Optional timeout override

        Returns:
            Generated response text or None on failure
        """
        effective_timeout = timeout or self.timeout

        # Read configurable temperature and max tokens from DB (with fallbacks)
        temperature = 0.5
        num_predict = 1024
        try:
            from ..models import AISettings
            temp_str = AISettings.get('ai_temperature')
            if temp_str is not None:
                temperature = float(temp_str)
            tokens_str = AISettings.get('ai_max_tokens')
            if tokens_str is not None:
                num_predict = int(tokens_str)
        except Exception:
            pass  # Use defaults if DB not available

        # Acquire semaphore — only one AI call at a time
        acquired = self._semaphore.acquire(timeout=effective_timeout + 10)
        if not acquired:
            logger.warning("Timed out waiting for AI semaphore — another request is in progress")
            return None

        max_retries = 2
        retry_waits = [1, 3]

        try:
            for attempt in range(max_retries + 1):
                try:
                    logger.debug(f"Sending {len(messages)} messages to Ollama ({self.model})"
                                 + (f" [retry {attempt}]" if attempt > 0 else ""))

                    t0 = time.monotonic()

                    response = requests.post(
                        self.chat_endpoint,
                        json={
                            'model': self.model,
                            'messages': messages,
                            'stream': False,
                            'options': {
                                'temperature': temperature,
                                'num_predict': num_predict,
                            }
                        },
                        timeout=effective_timeout
                    )

                    elapsed = time.monotonic() - t0

                    if response.status_code == 200:
                        result = response.json()
                        content = result.get('message', {}).get('content', '').strip()
                        if not content:
                            content = result.get('response', '').strip()

                        # Log timing and token info
                        eval_count = result.get('eval_count', '?')
                        logger.info(f"[AI CALL] model={self.model} | {elapsed:.1f}s | {eval_count} tokens")

                        # Track in debug dashboard
                        self._track_api_call('chat', response.status_code, elapsed * 1000)
                        return content
                    else:
                        logger.error(f"Ollama API error: {response.status_code} - {response.text}")
                        self._track_api_call('chat', response.status_code, elapsed * 1000,
                                             error=response.text[:200])
                        return None  # Don't retry 4xx/5xx

                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                    elapsed = time.monotonic() - t0 if 't0' in dir() else 0
                    if attempt < max_retries:
                        wait = retry_waits[attempt]
                        logger.warning(f"AI call failed ({type(e).__name__}) after {elapsed:.1f}s, "
                                       f"retrying in {wait}s (attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait)
                    else:
                        if isinstance(e, requests.exceptions.Timeout):
                            logger.warning(f"Ollama request timed out after {effective_timeout}s (all retries exhausted)")
                        else:
                            logger.error("Could not connect to Ollama server (all retries exhausted)")
                        self._track_api_call('chat', None, elapsed * 1000, error=str(e)[:200])
                        return None

                except requests.exceptions.RequestException as e:
                    logger.error(f"Ollama request failed: {e}")
                    self._track_api_call('chat', None, 0, error=str(e)[:200])
                    return None  # Don't retry unknown errors

        finally:
            self._semaphore.release()

        return None

    @staticmethod
    def _track_api_call(endpoint: str, status_code, duration_ms: float, error=None):
        """Record an Ollama API call in the debug tracker."""
        try:
            from .debug_service import get_api_tracker
            tracker = get_api_tracker()
            if tracker:
                tracker.record('ollama', 'POST', f'/api/{endpoint}',
                               status_code=status_code,
                               duration_ms=duration_ms,
                               error=error)
        except Exception:
            pass  # Debug tracking should never break the main flow

    def extract_guest_info(self, message_content: str) -> Dict[str, Any]:
        """
        Extract structured guest information from a message using AI.
        Also detects the language of the message for multilingual support.

        Args:
            message_content: The message text to analyze

        Returns:
            Dictionary with extracted information including detected_language
        """
        system = ("You are a JSON extraction assistant. You analyze messages and extract "
                  "structured guest information. Always respond with ONLY a valid JSON object, "
                  "no other text or markdown.")

        prompt = f"""Analyze this message and extract any guest information mentioned.
Also detect the language the message is written in.

Return ONLY a valid JSON object with these fields (use null for missing data):

{{
    "detected_language": string (e.g., "German", "English", "Spanish", "French", "Italian"),
    "guest_name": string or null,
    "family_members": [{{ "name": string, "relation": string }}] or [],
    "pets": [{{ "name": string, "type": string }}] or [],
    "preferences": [{{ "type": string, "value": string }}] or [],
    "allergies": [{{ "type": string, "value": string }}] or [],
    "check_in": string (date) or null,
    "check_out": string (date) or null,
    "num_guests": integer or null,
    "special_requests": [string] or [],
    "mentioned_interests": [string] or []
}}

Message to analyze:
"{message_content}"

Return ONLY the JSON object:"""

        try:
            response = self.generate_response(prompt, system=system, timeout=self.timeout)

            if not response:
                logger.warning("No response from AI for extraction")
                return self._empty_extraction()

            # Try to parse the JSON response
            try:
                # Strip think tags first (qwen3 chain-of-thought)
                clean_response = self._strip_think_tags(response)
                # Clean up response - sometimes AI adds markdown code blocks
                clean_response = clean_response.strip()
                if clean_response.startswith('```json'):
                    clean_response = clean_response[7:]
                if clean_response.startswith('```'):
                    clean_response = clean_response[3:]
                if clean_response.endswith('```'):
                    clean_response = clean_response[:-3]
                clean_response = clean_response.strip()

                try:
                    data = json.loads(clean_response)
                except json.JSONDecodeError:
                    # Fallback: search for JSON object in mixed text
                    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', clean_response, re.DOTALL)
                    if match:
                        data = json.loads(match.group())
                        logger.debug("Extracted JSON via regex fallback")
                    else:
                        raise

                data = self._validate_extraction(data)
                logger.info(f"Extraction successful: {self._summarize_extraction(data)}")
                return data

            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse AI response as JSON: {e}")
                logger.debug(f"Raw response: {response}")
                return self._empty_extraction()

        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return self._empty_extraction()

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
        """
        Generate a personalized AI response for a guest.
        Uses native chat format with proper user/assistant roles so the model
        understands the conversation structure.

        Args:
            guest_profile: Complete guest profile including all stored memories
            conversation_history: Recent messages in the conversation
            latest_message: The most recent message from the guest
            property_info: Optional property information for context
            tone: Response tone (friendly_professional, formal, casual, concise)
            host_instructions: Custom host instructions for AI context
            conversation_subject: Email subject or conversation topic
            max_history: Maximum number of history messages to include
            reservation_info: Optional Smoobu reservation details
            conversation_summary: Cached summary of older messages for context

        Returns:
            Generated response text or None on failure
        """
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

        # Log what the AI actually receives for debugging
        guest_name = guest_profile.get('name', '?') if guest_profile else '?'
        profile_details = []
        if guest_profile:
            for key in ('family', 'pets', 'preferences', 'allergies', 'interests', 'special_requests', 'booking'):
                items = guest_profile.get(key, [])
                if items:
                    profile_details.append(f"{key}({len(items)})")

        # Determine what the AI is responding to
        is_ack = self.is_acknowledgment(latest_message)
        logger.info(
            f"[AI CONTEXT] guest='{guest_name}' | "
            f"responding_to='{latest_message[:80]}' | "
            f"message_type={'acknowledgment' if is_ack else 'needs_response'} | "
            f"history={len(conversation_history)} msgs → {len(messages)} chat turns | "
            f"profile=[{', '.join(profile_details) or 'empty'}] | "
            f"property={'yes' if property_info else 'no'} | "
            f"reservation={'yes' if reservation_info else 'no'} | "
            f"tone={tone or 'default'}"
        )
        # Full prompt at DEBUG level — visible when FLASK_ENV=development
        for i, msg in enumerate(messages):
            role = msg['role']
            content = msg['content'][:200].replace('\n', '\\n')
            logger.debug(f"  [AI msg {i}] {role}: {content}")

        response = self._call_chat_api(messages, timeout=self.timeout)

        if not response:
            logger.warning(f"[AI FAILED] guest='{guest_name}' | No response from Ollama")
            return None

        response = self._clean_ai_response(response)
        if not response:
            logger.warning(f"[AI FAILED] guest='{guest_name}' | Response rejected by quality guards")
            return None

        logger.info(f"[AI RESPONSE] guest='{guest_name}' | length={len(response)} chars | preview='{response[:80]}'")
        return response

    def generate_conversation_summary(
            self,
            messages: List[Dict[str, str]],
            existing_summary: Optional[str] = None
    ) -> Optional[str]:
        """Generate or update a conversation summary for AI context.

        Args:
            messages: Message dicts to summarize (each has 'sender_type', 'content', 'sent_at')
            existing_summary: If provided, update this summary with the new messages

        Returns:
            Summary text (bullet points) or None on failure
        """
        if not messages:
            return existing_summary

        # Format messages for the prompt
        sender_labels = {'guest': 'Guest', 'owner': 'Host', 'ai': 'Host'}
        formatted = []
        for msg in messages:
            label = sender_labels.get(msg.get('sender_type', 'guest'), 'Guest')
            content = self._strip_html(msg.get('content', ''))
            content = self._strip_email_quotes(content)
            if content.strip():
                formatted.append(f"{label}: {content.strip()}")

        if not formatted:
            return existing_summary

        formatted_messages = "\n".join(formatted)

        system = "You are a summarization assistant. Be concise and factual."

        if existing_summary:
            prompt = (
                "Here is an existing summary of an ongoing conversation "
                "between a vacation rental host and a guest:\n\n"
                f"{existing_summary}\n\n"
                "New messages since the last summary:\n"
                f"{formatted_messages}\n\n"
                "Update the summary to include the new information.\n"
                "Keep the same bullet-point format. Keep it under 300 words.\n"
                "Write in the same language as the conversation.\n"
                "Remove items that are no longer pending. "
                "Add new decisions, promises, or open items."
            )
        else:
            prompt = (
                "Summarize this conversation between a vacation rental host and a guest.\n"
                "Write concise bullet points covering:\n"
                "- Key decisions made\n"
                "- Promises or commitments by either party\n"
                "- Questions that were answered (and the answers)\n"
                "- Pending or open items\n\n"
                "Keep it under 300 words. Write in the same language as the conversation.\n"
                "Do NOT include greetings, pleasantries, or filler.\n\n"
                f"Conversation:\n{formatted_messages}"
            )

        try:
            response = self.generate_response(prompt, system=system)
            if response:
                response = self._strip_think_tags(response).strip()
                if len(response) < 10:
                    logger.warning(f"[SUMMARY] Generated summary too short ({len(response)} chars), discarding")
                    return existing_summary
                logger.info(f"[SUMMARY] Generated summary: {len(response)} chars")
                return response
            logger.warning("[SUMMARY] No response from Ollama for summary generation")
            return existing_summary
        except Exception as e:
            logger.warning(f"[SUMMARY] Summary generation failed: {e}")
            return existing_summary

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

    # Tone mapping for AI prompt instructions
    TONE_INSTRUCTIONS = {
        'friendly_professional': "Be warm, helpful, and professional.",
        'formal': "Be polite, formal, and professional. Use formal language (Sie in German).",
        'casual': "Be relaxed and conversational, like chatting with a friend.",
        'concise': "Be brief and to the point. Short sentences, no filler.",
    }

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
        """Build chat messages array with proper roles for the Ollama chat API.

        Uses native user/assistant roles so the model understands the full
        conversation structure and can see what was already said/asked.

        Returns:
            List of {role, content} message dicts
        """
        messages = []

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

        # Get guest's preferred language if stored
        guest_language = guest_profile.get('language', None) if guest_profile else None

        # Resolve tone instruction
        tone_instruction = self.TONE_INSTRUCTIONS.get(tone, self.TONE_INSTRUCTIONS['friendly_professional'])

        # Clean latest message early so we can reference it in the system prompt
        clean_latest = self._strip_html(latest_message)
        clean_latest = self._strip_email_quotes(clean_latest)
        if not clean_latest.strip():
            clean_latest = latest_message.strip()

        # Pre-scan: count consecutive trailing guest messages for dynamic system prompt
        # Uses raw conversation_history (available from method params) since clean_history isn't built yet
        # Cap at max_history since truncation may reduce what actually appears in chat turns
        unanswered_count = min(
            self._count_trailing_guest_messages(conversation_history),
            max_history
        )

        # --- System message: role, rules, and context ---
        now = datetime.utcnow()
        system_parts = [
            "You are a vacation rental host writing a reply to a guest.",
            f"{tone_instruction}",
            f"Current date/time: {now.strftime('%A, %d %B %Y, %H:%M')} UTC.",
            "",
            "Rules:",
            "- Reply ONLY in the SAME LANGUAGE as the guest's latest message.",
            "- Write ONLY the reply text. No subject lines, no 'Subject:', no signatures.",
            "- NEVER re-ask questions the guest already answered.",
            "- NEVER repeat information you already provided.",
            "- If you don't know specific details (WiFi password, door code, prices), say you'll check — NEVER invent details.",
            "",
            "=== CONVERSATION FLOW ===",
            "The full conversation follows as user/assistant turns.",
            "Previous guest messages have ALREADY been answered by the host.",
        ]

        if unanswered_count >= 2:
            system_parts.extend([
                f"The guest has sent {unanswered_count} unanswered messages (numbered [1]-[{unanswered_count}] in their turn below).",
                "Address ALL of them in a single reply.",
            ])
        else:
            system_parts.extend([
                f'The guest\'s MOST RECENT message is: "{clean_latest[:300]}"',
                "Write a reply ONLY for this latest message above.",
            ])

        system_parts.extend([
            "Do NOT re-answer earlier questions that the host already addressed.",
            "===",
        ])
        if guest_language:
            system_parts.append(f"- The guest's preferred language is: {guest_language}.")

        # Embed context (guest profile + property) in the system message
        if guest_profile:
            profile_text = self._format_guest_profile(guest_profile)
            if profile_text:
                system_parts.append(f"\n=== GUEST PROFILE ===\n{profile_text}\n=== Do NOT ask for info already listed above. ===")

        if property_info:
            property_text = self._format_property_info(property_info)
            if property_text:
                system_parts.append(f"\nProperty details:\n{property_text}")

        if conversation_subject:
            system_parts.append(f"\nConversation topic: {conversation_subject}")

        if reservation_info:
            res_text = self._format_reservation_info(reservation_info)
            if res_text:
                system_parts.append(f"\n=== RESERVATION ===\n{res_text}\n===")

        if knowledge_entries:
            regular_entries = [e for e in knowledge_entries if e.get('category') != 'escalation']
            escalation_entries = [e for e in knowledge_entries if e.get('category') == 'escalation']

            if regular_entries:
                kb_text = self._format_knowledge_entries(regular_entries)
                if kb_text:
                    system_parts.append(f"\n=== HOST KNOWLEDGE BASE ===\n{kb_text}\n===")

            if escalation_entries:
                restricted_text = self._format_restricted_topics(escalation_entries)
                if restricted_text:
                    system_parts.append(f"\n=== RESTRICTED TOPICS ===\n{restricted_text}\n===")

        if host_instructions and host_instructions.strip():
            system_parts.append(f"\n=== HOST INSTRUCTIONS ===\n{host_instructions.strip()}\n===")

        if resolved_topics:
            topics_text = "\n".join(f"- {topic}" for topic in resolved_topics[:8])
            system_parts.append(
                f"\n=== ALREADY RESOLVED (do NOT address these topics again) ===\n"
                f"{topics_text}\n==="
            )

        if conversation_summary:
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

        if corrections:
            corrections_text = self._format_corrections(corrections)
            if corrections_text:
                system_parts.append(f"\n=== PAST CORRECTIONS (you made these mistakes before — don't repeat them) ===\n{corrections_text}\n===")

        messages.append({'role': 'system', 'content': "\n".join(system_parts)})

        # --- Conversation history as native user/assistant turns ---
        # Deduplicate by platform_message_id, clean content, keep recent turns
        seen_platform_ids = set()
        clean_history = []
        for msg in conversation_history:
            # Skip duplicate messages (same platform_message_id)
            pmid = msg.get('platform_message_id')
            if pmid:
                if pmid in seen_platform_ids:
                    continue
                seen_platform_ids.add(pmid)

            sender_type = msg.get('sender_type', 'guest')
            content = msg.get('content', '').strip()
            if not content:
                continue

            # Strip HTML tags (Smoobu wraps messages in HTML)
            content = self._strip_html(content)

            # Strip quoted replies and signatures from message content
            stripped_content = self._strip_email_quotes(content)
            # Use stripped version if it has content, otherwise keep original
            content = stripped_content if stripped_content.strip() else content

            # Skip empty-after-cleaning messages
            if not content.strip():
                continue

            role = 'user' if sender_type == 'guest' else 'assistant'

            # Add timestamp context for recency understanding
            sent_at = msg.get('sent_at')
            time_label = self._format_relative_time(sent_at, now) if sent_at else None

            clean_history.append({
                'role': role,
                'content': content,
                'sender_type': sender_type,
                'time_label': time_label,
            })

        # Keep last N messages for context
        recent_history = clean_history[-max_history:]

        # Deduplicate consecutive same-content messages
        deduped = []
        seen_content = set()
        for msg in recent_history:
            key = (msg['role'], msg['content'])
            if key not in seen_content:
                seen_content.add(key)
                deduped.append(msg)

        # Collapse consecutive AI-only messages to just the last one.
        # When auto_respond is off, multiple AI suggestions pile up — only
        # the most recent suggestion matters. Owner messages are always kept.
        collapsed = []
        for msg in deduped:
            if (collapsed and collapsed[-1]['role'] == 'assistant'
                    and msg['role'] == 'assistant'):
                prev_is_ai = collapsed[-1].get('sender_type') == 'ai'
                curr_is_ai = msg.get('sender_type') == 'ai'
                if prev_is_ai and curr_is_ai:
                    # Both are AI suggestions — keep only the newer one
                    collapsed[-1] = dict(msg)
                elif prev_is_ai and not curr_is_ai:
                    # Previous was AI suggestion, current is real owner message — keep owner
                    collapsed[-1] = dict(msg)
                else:
                    # Previous is owner, current is AI or owner — merge
                    collapsed[-1] = dict(collapsed[-1])
                    collapsed[-1]['content'] += "\n\n" + msg['content']
            else:
                collapsed.append(dict(msg))

        # Merge remaining consecutive same-role messages (Ollama requires alternating roles)
        # For consecutive user messages: NUMBER them [1], [2], [3] when 2+ consecutive
        # For consecutive assistant messages: merge them together
        # Add short relative timestamps as prefixes for temporal awareness
        merged = []
        # Track consecutive user messages for numbering
        _consecutive_user_count = 0

        for msg in collapsed:
            time_prefix = f"[{msg['time_label']}] " if msg.get('time_label') else ""
            content_with_time = f"{time_prefix}{msg['content']}"

            if merged and merged[-1]['role'] == msg['role']:
                if msg['role'] == 'user':
                    _consecutive_user_count += 1
                    if _consecutive_user_count == 2:
                        # Retroactively number the first message
                        merged[-1]['content'] = f"[1] {merged[-1]['content']}"
                    # Number this message
                    numbered = f"[{_consecutive_user_count}] {content_with_time}"
                    merged[-1]['content'] += "\n" + numbered
                else:
                    merged[-1]['content'] += "\n\n" + content_with_time
            else:
                if msg['role'] == 'user':
                    _consecutive_user_count = 1
                else:
                    _consecutive_user_count = 0
                merged.append({'role': msg['role'], 'content': content_with_time})

        # Ensure conversation starts with a user message (required by some models).
        # Instead of dropping the initial assistant turn (which loses owner context),
        # insert a synthetic user message as a bridge.
        if merged and merged[0]['role'] == 'assistant':
            merged.insert(0, {'role': 'user', 'content': '[Previous conversation:]'})

        # Ensure conversation ends with a user message (required by most models).
        # The system prompt already tells the model which message to respond to,
        # so we don't need inline instructions in the user turn.
        if merged and merged[-1]['role'] == 'user':
            # Latest guest message is already the final user turn. Nothing to add.
            pass
        elif merged and merged[-1]['role'] == 'assistant':
            # Host/AI already replied to the last guest message.
            # KEEP the assistant reply visible so the model knows what was already said
            # (previously we popped it, which caused the model to re-answer old questions).
            # Append the latest guest message as a new user turn for the model to respond to.
            merged.append({'role': 'user', 'content': clean_latest})
        else:
            # Empty conversation
            merged.append({'role': 'user', 'content': clean_latest})

        messages.extend(merged)

        return messages

    @staticmethod
    def _strip_html(text: str) -> str:
        """Strip HTML tags and decode common entities from message content."""
        if not text or '<' not in text:
            return text
        # Remove HTML tags
        text = re.sub(r'<br\s*/?\s*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', text)
        # Decode common HTML entities
        text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        text = text.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
        # Collapse excessive whitespace from HTML structure
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]{2,}', ' ', text)
        return text.strip()

    @staticmethod
    def _format_relative_time(sent_at_str, now: datetime) -> str:
        """Format a sent_at timestamp as a relative time label."""
        try:
            if isinstance(sent_at_str, str):
                # Handle ISO format timestamps
                sent_at = datetime.fromisoformat(sent_at_str.replace('Z', '+00:00'))
                if sent_at.tzinfo:
                    sent_at = sent_at.replace(tzinfo=None)
            elif isinstance(sent_at_str, datetime):
                sent_at = sent_at_str
            else:
                return ""

            diff = now - sent_at
            minutes = diff.total_seconds() / 60

            if minutes < 5:
                return "just now"
            elif minutes < 60:
                return f"{int(minutes)}min ago"
            elif minutes < 1440:
                hours = int(minutes / 60)
                return f"{hours}h ago"
            else:
                days = int(minutes / 1440)
                return f"{days}d ago"
        except (ValueError, TypeError):
            return ""

    @staticmethod
    def _strip_email_quotes(text: str) -> str:
        """Strip quoted replies, signatures, and email noise from message content.
        Keeps only the new content the person actually wrote."""
        if not text:
            return ""

        lines = text.splitlines()
        cleaned = []

        for line in lines:
            stripped = line.strip()

            # Stop at quoted reply markers
            if re.match(r'^On .+ wrote:\s*$', stripped):
                break
            if re.match(r'^Am .+ schrieb .+:\s*$', stripped):
                break
            if re.match(r'^-{2,}\s*(Original Message|Forwarded message|Urspr)', stripped, re.IGNORECASE):
                break
            if stripped.startswith('>'):
                break
            if stripped == '--':
                break

            cleaned.append(line)

        result = '\n'.join(cleaned).strip()
        # Collapse excessive whitespace
        result = re.sub(r'\n{3,}', '\n\n', result)
        result = re.sub(r'\r\n', '\n', result)

        return result

    @staticmethod
    def _count_trailing_guest_messages(history: list) -> int:
        """Count consecutive guest messages at the end of the history (no host/AI reply between them)."""
        count = 0
        for msg in reversed(history):
            if msg.get('sender_type') == 'guest':
                count += 1
            else:
                break
        return count

    @staticmethod
    def _strip_think_tags(text: str) -> str:
        """Strip <think>...</think> blocks from model output (qwen3 chain-of-thought)."""
        if not text or '<think>' not in text:
            return text
        # Strip closed think blocks
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        # Strip unclosed think tag (model stopped mid-thought)
        text = re.sub(r'<think>.*', '', text, flags=re.DOTALL)
        return text.strip()

    def _clean_ai_response(self, text: str) -> Optional[str]:
        """Clean AI response: strip artifacts, enforce length guards.

        Returns cleaned text, or None if response is broken/empty.
        """
        if not text:
            return None

        # Strip thinking blocks first (can be large)
        text = self._strip_think_tags(text)

        # Strip model artifacts
        artifact_patterns = [
            r'\[INST\]', r'\[/INST\]',
            r'<<SYS>>', r'<</SYS>>',
            r'<\|assistant\|>', r'<\|user\|>', r'<\|system\|>',
            r'<\|im_start\|>', r'<\|im_end\|>',
            r'<\|end\|>',
            r'<s>', r'</s>',
        ]
        for pattern in artifact_patterns:
            text = re.sub(pattern, '', text)

        # Clean up whitespace left by stripping
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()

        # Minimum length guard
        if len(text) < 10:
            logger.warning(f"[AI QUALITY] Response too short ({len(text)} chars), rejecting: '{text}'")
            return None

        # Maximum length guard — truncate at sentence boundary
        if len(text) > 2000:
            original_len = len(text)
            truncated = text[:2000]
            # Find last sentence boundary
            last_boundary = max(
                truncated.rfind('.'),
                truncated.rfind('!'),
                truncated.rfind('?')
            )
            if last_boundary > 100:  # Only use boundary if it leaves a reasonable response
                text = truncated[:last_boundary + 1]
            else:
                text = truncated
            logger.info(f"[AI QUALITY] Response truncated from {original_len} to {len(text)} chars")

        return text

    def _format_guest_profile(self, profile: Dict[str, Any]) -> str:
        """Format guest profile for the prompt"""
        lines = []

        if profile.get('name'):
            lines.append(f"- Name: {profile['name']}")

        if profile.get('total_stays', 0) > 0:
            lines.append(f"- Previous stays: {profile['total_stays']}")

        # Booking details (num_guests, check_in, check_out)
        booking = profile.get('booking', [])
        if booking:
            booking_map = {b['key']: b['value'] for b in booking}
            if booking_map.get('num_guests'):
                lines.append(f"- Number of guests: {booking_map['num_guests']}")
            if booking_map.get('check_in'):
                lines.append(f"- Check-in date: {booking_map['check_in']}")
            if booking_map.get('check_out'):
                lines.append(f"- Check-out date: {booking_map['check_out']}")

        # Family members
        family = profile.get('family', [])
        if family:
            family_str = ", ".join([f"{f['value']} ({f['key']})" for f in family])
            lines.append(f"- Family: {family_str}")

        # Pets
        pets = profile.get('pets', [])
        if pets:
            pets_str = ", ".join([f"{p['value']} ({p['key']})" for p in pets])
            lines.append(f"- Pets: {pets_str}")

        # Preferences
        prefs = profile.get('preferences', [])
        if prefs:
            prefs_str = ", ".join([f"{p['key']}: {p['value']}" for p in prefs])
            lines.append(f"- Preferences: {prefs_str}")

        # Allergies
        allergies = profile.get('allergies', [])
        if allergies:
            allergies_str = ", ".join([f"{a['key']}: {a['value']}" for a in allergies])
            lines.append(f"- ALLERGIES (CRITICAL - never ignore): {allergies_str}")

        # Interests
        interests = profile.get('interests', [])
        if interests:
            interests_str = ", ".join([i['value'] for i in interests])
            lines.append(f"- Interests: {interests_str}")

        # Special requests
        special_requests = profile.get('special_requests', [])
        if special_requests:
            requests_str = ", ".join([r['value'] for r in special_requests])
            lines.append(f"- Special requests: {requests_str}")

        return "\n".join(lines)

    def _format_property_info(self, property_info: Dict[str, Any]) -> str:
        """Format property information for the prompt"""
        lines = []

        if property_info.get('name'):
            lines.append(f"- Property: {property_info['name']}")
        if property_info.get('address'):
            lines.append(f"- Address: {property_info['address']}")
        if property_info.get('max_guests'):
            lines.append(f"- Max guests: {property_info['max_guests']}")
        if property_info.get('bedrooms'):
            lines.append(f"- Bedrooms: {property_info['bedrooms']}")
        if property_info.get('check_in_time'):
            lines.append(f"- Check-in: {property_info['check_in_time']}")
        if property_info.get('check_out_time'):
            lines.append(f"- Check-out: {property_info['check_out_time']}")
        if property_info.get('pet_friendly'):
            lines.append("- Pet-friendly: Yes")
        if property_info.get('amenities'):
            lines.append(f"- Amenities: {', '.join(property_info['amenities'])}")
        if property_info.get('house_rules'):
            lines.append(f"- House rules: {property_info['house_rules'][:200]}...")

        return "\n".join(lines)

    def _format_reservation_info(self, reservation_info: Dict[str, Any]) -> str:
        """Format Smoobu reservation details for the AI prompt"""
        lines = []
        if reservation_info.get('arrival') or reservation_info.get('check_in'):
            lines.append(f"- Check-in: {reservation_info.get('arrival') or reservation_info.get('check_in')}")
        if reservation_info.get('departure') or reservation_info.get('check_out'):
            lines.append(f"- Check-out: {reservation_info.get('departure') or reservation_info.get('check_out')}")
        if reservation_info.get('adults'):
            lines.append(f"- Adults: {reservation_info['adults']}")
        if reservation_info.get('children'):
            lines.append(f"- Children: {reservation_info['children']}")
        if reservation_info.get('price') or reservation_info.get('total_price'):
            lines.append(f"- Total price: {reservation_info.get('price') or reservation_info.get('total_price')}")
        if reservation_info.get('channel') or reservation_info.get('channel_name'):
            lines.append(f"- Booking channel: {reservation_info.get('channel') or reservation_info.get('channel_name')}")
        if reservation_info.get('apartment') and reservation_info['apartment'].get('name'):
            lines.append(f"- Property: {reservation_info['apartment']['name']}")
        return "\n".join(lines)

    @staticmethod
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

    def _format_knowledge_entries(entries: List[Dict[str, Any]], max_chars: int = 2000) -> str:
        """Format knowledge base entries for the AI prompt, grouped by category."""
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

    @staticmethod
    def _format_restricted_topics(escalation_entries: List[Dict[str, Any]]) -> str:
        """Format escalation KB entries as restricted topics for the AI prompt."""
        if not escalation_entries:
            return ""

        lines = [
            "You MUST NOT answer questions about these topics yourself.",
            'Instead, reply with something like: "I\'ll check with my colleague and get back to you shortly."',
            "(Always in the guest's language.)",
            "",
        ]
        for entry in escalation_entries:
            lines.append(f"- {entry['label']}")

        return "\n".join(lines)

    def _format_conversation(self, messages: List[Dict[str, str]], max_messages: int = 10) -> str:
        """Format conversation history for the prompt"""
        recent = messages[-max_messages:] if len(messages) > max_messages else messages

        sender_labels = {
            'guest': 'Guest',
            'owner': 'You (Host)',
            'ai': 'You (Host)',
        }

        lines = []
        for msg in recent:
            sender_type = msg.get('sender_type', 'unknown')
            label = sender_labels.get(sender_type, sender_type)
            content = msg.get('content', '')[:800]
            lines.append(f"{label}: {content}")

        return "\n".join(lines)

    def _validate_extraction(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize extracted data types.
        Ensures correct types and normalizes null-like strings to None."""
        null_values = {'null', 'none', 'n/a', 'na', 'nil', ''}

        def normalize_str(val):
            """Return None for null-like strings, else stripped string."""
            if val is None:
                return None
            if isinstance(val, str) and val.strip().lower() in null_values:
                return None
            return str(val).strip() if val else None

        def ensure_list_of_dicts(val):
            """Ensure value is a list of dicts."""
            if not isinstance(val, list):
                return []
            return [item for item in val if isinstance(item, dict)]

        def ensure_list_of_strings(val):
            """Ensure value is a list of strings."""
            if not isinstance(val, list):
                return []
            return [str(item).strip() for item in val if item and str(item).strip()]

        result = self._empty_extraction()

        # String fields
        result['detected_language'] = normalize_str(data.get('detected_language'))
        result['guest_name'] = normalize_str(data.get('guest_name'))
        result['check_in'] = normalize_str(data.get('check_in'))
        result['check_out'] = normalize_str(data.get('check_out'))

        # Integer field
        num_guests = data.get('num_guests')
        if num_guests is not None:
            try:
                result['num_guests'] = int(num_guests)
            except (ValueError, TypeError):
                result['num_guests'] = None

        # List of dicts fields
        result['family_members'] = ensure_list_of_dicts(data.get('family_members'))
        result['pets'] = ensure_list_of_dicts(data.get('pets'))
        result['preferences'] = ensure_list_of_dicts(data.get('preferences'))
        result['allergies'] = ensure_list_of_dicts(data.get('allergies'))

        # List of strings fields
        result['special_requests'] = ensure_list_of_strings(data.get('special_requests'))
        result['mentioned_interests'] = ensure_list_of_strings(data.get('mentioned_interests'))

        return result

    def _empty_extraction(self) -> Dict[str, Any]:
        """Return an empty extraction structure"""
        return {
            'detected_language': None,
            'guest_name': None,
            'family_members': [],
            'pets': [],
            'preferences': [],
            'allergies': [],
            'check_in': None,
            'check_out': None,
            'num_guests': None,
            'special_requests': [],
            'mentioned_interests': []
        }

    def _summarize_extraction(self, data: Dict[str, Any]) -> str:
        """Create a summary of extracted data for logging"""
        parts = []
        if data.get('guest_name'):
            parts.append(f"name:{data['guest_name']}")
        if data.get('family_members'):
            parts.append(f"family:{len(data['family_members'])}")
        if data.get('pets'):
            parts.append(f"pets:{len(data['pets'])}")
        if data.get('preferences'):
            parts.append(f"prefs:{len(data['preferences'])}")
        if data.get('allergies'):
            parts.append(f"allergies:{len(data['allergies'])}")
        if data.get('num_guests'):
            parts.append(f"guests:{data['num_guests']}")
        return ", ".join(parts) if parts else "no data extracted"


# Global instance for Flask app context
_ai_service: Optional[AIService] = None


def init_ai_service(app) -> AIService:
    """Initialize the AI service with Flask app configuration"""
    global _ai_service
    _ai_service = AIService(
        ollama_url=app.config.get('OLLAMA_URL', 'http://localhost:11434'),
        model=app.config.get('OLLAMA_MODEL', 'gemma2:9b'),
        timeout=app.config.get('OLLAMA_TIMEOUT', 120)
    )
    logger.info(f"AI Service initialized with model {_ai_service.model}")
    return _ai_service


def get_ai_service() -> Optional[AIService]:
    """Get the current AI service instance"""
    return _ai_service
