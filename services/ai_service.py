"""
AI Service for ChatBotAI
Handles all interactions with Ollama for response generation and information extraction
"""

import json
import logging
import requests
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)


class AIService:
    """Service for interacting with Ollama AI"""

    def __init__(self, ollama_url: str = 'http://localhost:11434', model: str = 'mistral:7b-instruct', timeout: int = 30):
        self.ollama_url = ollama_url
        self.model = model
        self.timeout = timeout
        self.api_endpoint = f"{ollama_url}/api/generate"

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

    def generate_response(self, prompt: str, timeout: Optional[int] = None) -> Optional[str]:
        """
        Generate a response from the AI model.

        Args:
            prompt: The prompt to send to the model
            timeout: Optional timeout override

        Returns:
            Generated response text or None on failure
        """
        try:
            response = requests.post(
                self.api_endpoint,
                json={
                    'model': self.model,
                    'prompt': prompt,
                    'stream': False
                },
                timeout=timeout or self.timeout
            )

            if response.status_code == 200:
                result = response.json()
                return result.get('response', '').strip()
            else:
                logger.error(f"Ollama API error: {response.status_code} - {response.text}")
                return None

        except requests.exceptions.Timeout:
            logger.warning(f"Ollama request timed out after {timeout or self.timeout}s")
            return None
        except requests.exceptions.ConnectionError:
            logger.error("Could not connect to Ollama server")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama request failed: {e}")
            return None

    def extract_guest_info(self, message_content: str) -> Dict[str, Any]:
        """
        Extract structured guest information from a message using AI.
        Also detects the language of the message for multilingual support.

        Args:
            message_content: The message text to analyze

        Returns:
            Dictionary with extracted information including detected_language
        """
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

Return ONLY the JSON object, no other text:"""

        try:
            response = self.generate_response(prompt, timeout=self.timeout)

            if not response:
                logger.warning("No response from AI for extraction")
                return self._empty_extraction()

            # Try to parse the JSON response
            try:
                # Clean up response - sometimes AI adds markdown code blocks
                clean_response = response.strip()
                if clean_response.startswith('```json'):
                    clean_response = clean_response[7:]
                if clean_response.startswith('```'):
                    clean_response = clean_response[3:]
                if clean_response.endswith('```'):
                    clean_response = clean_response[:-3]
                clean_response = clean_response.strip()

                data = json.loads(clean_response)
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
            property_info: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Generate a personalized AI response for a guest.

        Args:
            guest_profile: Complete guest profile including all stored memories
            conversation_history: Recent messages in the conversation
            latest_message: The most recent message from the guest
            property_info: Optional property information for context

        Returns:
            Generated response text or None on failure
        """
        # Build the prompt with full context
        prompt = self._build_response_prompt(
            guest_profile,
            conversation_history,
            latest_message,
            property_info
        )

        response = self.generate_response(prompt, timeout=self.timeout)

        if response:
            logger.info(f"Generated response for guest {guest_profile.get('id', 'unknown')}")
            return response
        else:
            logger.warning("Failed to generate guest response")
            return None

    def _build_response_prompt(
            self,
            guest_profile: Dict[str, Any],
            conversation_history: List[Dict[str, str]],
            latest_message: str,
            property_info: Optional[Dict[str, Any]]
    ) -> str:
        """Build the complete prompt for response generation"""

        # Get guest's preferred language if stored, otherwise detect from message
        guest_language = guest_profile.get('language', None) if guest_profile else None

        prompt_parts = [
            "You are a helpful, friendly vacation rental host assistant.",
            "Respond in a warm, professional tone. Be helpful and personalized.",
            "",
            "## CRITICAL LANGUAGE INSTRUCTION:",
            "IMPORTANT: You MUST detect the language of the guest's message and respond in THE SAME LANGUAGE.",
            "- If the guest writes in German, respond in German.",
            "- If the guest writes in English, respond in English.",
            "- If the guest writes in Spanish, respond in Spanish.",
            "- If the guest writes in French, respond in French.",
            "- If the guest writes in Italian, respond in Italian.",
            "- For any other language, respond in that same language.",
        ]

        if guest_language:
            prompt_parts.append(f"- The guest's preferred language is: {guest_language}. Use this language.")

        prompt_parts.append("")

        # Add guest profile if available
        if guest_profile:
            profile_text = self._format_guest_profile(guest_profile)
            if profile_text:
                prompt_parts.append("## Guest Information (use this to personalize your response):")
                prompt_parts.append(profile_text)
                prompt_parts.append("")

        # Add property info if available
        if property_info:
            property_text = self._format_property_info(property_info)
            if property_text:
                prompt_parts.append("## Property Information:")
                prompt_parts.append(property_text)
                prompt_parts.append("")

        # Add conversation history
        if conversation_history:
            prompt_parts.append("## Recent Conversation:")
            prompt_parts.append(self._format_conversation(conversation_history))
            prompt_parts.append("")

        # Add the latest message
        prompt_parts.append("## Latest Guest Message:")
        prompt_parts.append(f'"{latest_message}"')
        prompt_parts.append("")
        prompt_parts.append("## Your Response (be helpful, warm, and personalized):")

        return "\n".join(prompt_parts)

    def _format_guest_profile(self, profile: Dict[str, Any]) -> str:
        """Format guest profile for the prompt"""
        lines = []

        if profile.get('name'):
            lines.append(f"- Name: {profile['name']}")

        if profile.get('total_stays', 0) > 0:
            lines.append(f"- Previous stays: {profile['total_stays']}")

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
            lines.append(f"- Allergies (IMPORTANT): {allergies_str}")

        # Interests
        interests = profile.get('interests', [])
        if interests:
            interests_str = ", ".join([i['value'] for i in interests])
            lines.append(f"- Interests: {interests_str}")

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

    def _format_conversation(self, messages: List[Dict[str, str]], max_messages: int = 10) -> str:
        """Format conversation history for the prompt"""
        recent = messages[-max_messages:] if len(messages) > max_messages else messages

        lines = []
        for msg in recent:
            sender = msg.get('sender_type', 'unknown').upper()
            content = msg.get('content', '')[:500]  # Limit content length
            lines.append(f"[{sender}]: {content}")

        return "\n".join(lines)

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
        model=app.config.get('OLLAMA_MODEL', 'mistral:7b-instruct'),
        timeout=app.config.get('OLLAMA_TIMEOUT', 30)
    )
    logger.info(f"AI Service initialized with model {_ai_service.model}")
    return _ai_service


def get_ai_service() -> Optional[AIService]:
    """Get the current AI service instance"""
    return _ai_service
