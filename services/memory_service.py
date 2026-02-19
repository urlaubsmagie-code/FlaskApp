"""
Memory Service for ChatBotAI
CRITICAL FEATURE: Persistent guest memory that makes ChatBotAI special!
Handles extraction, storage, and retrieval of guest information.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, List, Any

from ..models import db, Guest, GuestDetail, Message
from .ai_service import get_ai_service

logger = logging.getLogger(__name__)


class MemoryService:
    """Service for managing persistent guest memory"""

    def __init__(self):
        pass

    def process_message_for_memory(self, message: Message) -> bool:
        """
        Main entry point for memory extraction.
        Processes a message and extracts guest information.

        This processes EVERY message (guest AND owner messages) because
        owners often mention guest details in their responses.

        Args:
            message: The message to process

        Returns:
            True if processing was successful
        """
        if message.is_processed:
            logger.debug(f"Message {message.id} already processed")
            return True

        try:
            ai_service = get_ai_service()
            if not ai_service:
                logger.warning("AI service not available for memory extraction")
                message.is_processed = True
                db.session.commit()
                return False

            # Extract information using AI
            extracted = ai_service.extract_guest_info(message.content)

            if not extracted:
                message.is_processed = True
                db.session.commit()
                return True

            # Get the guest from the conversation
            guest_id = message.conversation.guest_id

            # Store all extracted information
            self._store_extracted_info(guest_id, extracted, message.id)

            # Update guest name if found
            if extracted.get('guest_name'):
                guest = Guest.query.get(guest_id)
                if guest and not guest.name:
                    guest.name = extracted['guest_name']
                    logger.info(f"Updated guest {guest_id} name to: {extracted['guest_name']}")

            # Mark message as processed
            message.is_processed = True
            db.session.commit()

            logger.info(f"Successfully processed message {message.id} for memory extraction")
            return True

        except Exception as e:
            logger.error(f"Error processing message {message.id} for memory: {e}")
            db.session.rollback()
            return False

    def _store_extracted_info(self, guest_id: int, extracted: Dict[str, Any], message_id: int) -> None:
        """Store all extracted information from AI analysis"""

        # Store detected language (update if found, helps AI respond in correct language)
        detected_language = extracted.get('detected_language')
        if detected_language:
            self.store_detail(
                guest_id=guest_id,
                detail_type='language',
                detail_key='preferred',
                detail_value=detected_language,
                source_message_id=message_id,
                confidence=0.95
            )
            logger.info(f"Stored guest {guest_id} language preference: {detected_language}")

        # Store family members
        for member in extracted.get('family_members', []):
            if member.get('name') and member.get('relation'):
                self.store_detail(
                    guest_id=guest_id,
                    detail_type='family',
                    detail_key=member['relation'].lower(),
                    detail_value=member['name'],
                    source_message_id=message_id,
                    confidence=0.9
                )

        # Store pets
        for pet in extracted.get('pets', []):
            if pet.get('name') and pet.get('type'):
                self.store_detail(
                    guest_id=guest_id,
                    detail_type='pet',
                    detail_key=pet['type'].lower(),
                    detail_value=pet['name'],
                    source_message_id=message_id,
                    confidence=0.9
                )

        # Store preferences
        for pref in extracted.get('preferences', []):
            if pref.get('type') and pref.get('value'):
                self.store_detail(
                    guest_id=guest_id,
                    detail_type='preference',
                    detail_key=pref['type'].lower(),
                    detail_value=pref['value'],
                    source_message_id=message_id,
                    confidence=0.85
                )

        # Store allergies
        for allergy in extracted.get('allergies', []):
            if allergy.get('type') and allergy.get('value'):
                self.store_detail(
                    guest_id=guest_id,
                    detail_type='allergy',
                    detail_key=allergy['type'].lower(),
                    detail_value=allergy['value'],
                    source_message_id=message_id,
                    confidence=0.95  # High confidence for allergies - safety critical
                )

        # Store special requests
        for request in extracted.get('special_requests', []):
            if request:
                self.store_detail(
                    guest_id=guest_id,
                    detail_type='special_request',
                    detail_key='request',
                    detail_value=request,
                    source_message_id=message_id,
                    confidence=0.85
                )

        # Store interests
        for interest in extracted.get('mentioned_interests', []):
            if interest:
                self.store_detail(
                    guest_id=guest_id,
                    detail_type='interest',
                    detail_key='interest',
                    detail_value=interest,
                    source_message_id=message_id,
                    confidence=0.8
                )

    def store_detail(
            self,
            guest_id: int,
            detail_type: str,
            detail_key: str,
            detail_value: str,
            source_message_id: Optional[int] = None,
            confidence: float = 1.0
    ) -> bool:
        """
        Store a single guest detail with deduplication.

        Args:
            guest_id: Which guest this belongs to
            detail_type: Category (family, pet, preference, allergy, interest, special_request)
            detail_key: Specific attribute (e.g., "son", "dog", "floor")
            detail_value: Actual data (e.g., "Lucas", "Max", "ground")
            source_message_id: Optional message where this was found
            confidence: AI confidence score (0.0-1.0)

        Returns:
            True if stored, False if duplicate or error
        """
        # Normalize values
        detail_key = detail_key.strip().lower() if detail_key else ''
        detail_value = detail_value.strip() if detail_value else ''

        if not detail_key or not detail_value:
            return False

        try:
            # Check for exact duplicate
            existing = GuestDetail.query.filter_by(
                guest_id=guest_id,
                detail_type=detail_type,
                detail_key=detail_key,
                detail_value=detail_value
            ).first()

            if existing:
                logger.debug(f"Duplicate detail skipped: {detail_type}:{detail_key}={detail_value}")
                return False

            # Store new detail
            detail = GuestDetail(
                guest_id=guest_id,
                detail_type=detail_type,
                detail_key=detail_key,
                detail_value=detail_value,
                source_message_id=source_message_id,
                confidence=confidence
            )
            db.session.add(detail)
            db.session.commit()

            logger.info(f"Stored guest detail: {detail_type}:{detail_key}={detail_value} for guest {guest_id}")
            return True

        except Exception as e:
            logger.error(f"Error storing detail: {e}")
            db.session.rollback()
            return False

    def get_guest_profile(self, guest_id: int) -> Dict[str, Any]:
        """
        Build a complete guest profile from stored details.
        Used before AI response generation.

        Args:
            guest_id: The guest ID to get profile for

        Returns:
            Complete organized profile dictionary
        """
        guest = Guest.query.get(guest_id)
        if not guest:
            return {}

        # Get all details for this guest
        details = GuestDetail.query.filter_by(guest_id=guest_id).all()

        # Organize details by type
        profile = {
            'id': guest.id,
            'name': guest.name,
            'email': guest.email,
            'phone': guest.phone,
            'whatsapp_id': guest.whatsapp_id,
            'airbnb_id': guest.airbnb_id,
            'booking_id': guest.booking_id,
            'total_stays': guest.total_stays,
            'first_contact': guest.first_contact.isoformat() if guest.first_contact else None,
            'last_contact': guest.last_contact.isoformat() if guest.last_contact else None,
            'language': None,  # Guest's preferred language for AI responses
            'family': [],
            'pets': [],
            'preferences': [],
            'allergies': [],
            'interests': [],
            'special_requests': []
        }

        # Categorize details
        for detail in details:
            detail_dict = {
                'key': detail.detail_key,
                'value': detail.detail_value,
                'confidence': detail.confidence,
                'extracted_at': detail.extracted_at.isoformat() if detail.extracted_at else None
            }

            if detail.detail_type == 'language':
                # Store the most recent language preference
                profile['language'] = detail.detail_value
            elif detail.detail_type == 'family':
                profile['family'].append(detail_dict)
            elif detail.detail_type == 'pet':
                profile['pets'].append(detail_dict)
            elif detail.detail_type == 'preference':
                profile['preferences'].append(detail_dict)
            elif detail.detail_type == 'allergy':
                profile['allergies'].append(detail_dict)
            elif detail.detail_type == 'interest':
                profile['interests'].append(detail_dict)
            elif detail.detail_type == 'special_request':
                profile['special_requests'].append(detail_dict)

        return profile

    def find_or_create_guest(
            self,
            email: Optional[str] = None,
            phone: Optional[str] = None,
            platform: Optional[str] = None,
            platform_id: Optional[str] = None,
            name: Optional[str] = None
    ) -> Guest:
        """
        Smart guest identification across platforms.
        Finds existing guest or creates new one.

        Matching priority:
        1. Email (most reliable)
        2. Phone number
        3. Platform-specific ID

        Args:
            email: Guest email address
            phone: Guest phone number
            platform: Platform name (whatsapp, airbnb, booking)
            platform_id: Platform-specific user ID
            name: Guest name (optional)

        Returns:
            Guest object (existing or newly created)
        """
        guest = None

        # Try to find by email first (most reliable)
        if email:
            guest = Guest.query.filter_by(email=email).first()
            if guest:
                logger.info(f"Found guest by email: {guest.id}")

        # Try phone if no email match
        if not guest and phone:
            guest = Guest.query.filter_by(phone=phone).first()
            if guest:
                logger.info(f"Found guest by phone: {guest.id}")

        # Try platform-specific ID
        if not guest and platform and platform_id:
            if platform == 'whatsapp':
                guest = Guest.query.filter_by(whatsapp_id=platform_id).first()
            elif platform == 'airbnb':
                guest = Guest.query.filter_by(airbnb_id=platform_id).first()
            elif platform == 'booking':
                guest = Guest.query.filter_by(booking_id=platform_id).first()

            if guest:
                logger.info(f"Found guest by {platform} ID: {guest.id}")

        # Create new guest if not found
        if not guest:
            guest = Guest(
                name=name,
                email=email,
                phone=phone
            )

            # Set platform-specific ID
            if platform and platform_id:
                if platform == 'whatsapp':
                    guest.whatsapp_id = platform_id
                elif platform == 'airbnb':
                    guest.airbnb_id = platform_id
                elif platform == 'booking':
                    guest.booking_id = platform_id

            db.session.add(guest)
            db.session.commit()
            logger.info(f"Created new guest: {guest.id}")

        # Update contact info if we have new data
        else:
            updated = False
            if email and not guest.email:
                guest.email = email
                updated = True
            if phone and not guest.phone:
                guest.phone = phone
                updated = True
            if name and not guest.name:
                guest.name = name
                updated = True

            # Update platform IDs
            if platform and platform_id:
                if platform == 'whatsapp' and not guest.whatsapp_id:
                    guest.whatsapp_id = platform_id
                    updated = True
                elif platform == 'airbnb' and not guest.airbnb_id:
                    guest.airbnb_id = platform_id
                    updated = True
                elif platform == 'booking' and not guest.booking_id:
                    guest.booking_id = platform_id
                    updated = True

            if updated:
                db.session.commit()
                logger.info(f"Updated guest {guest.id} with new contact info")

        return guest

    def update_guest_last_contact(self, guest_id: int) -> None:
        """Update the last_contact timestamp for a guest"""
        try:
            guest = Guest.query.get(guest_id)
            if guest:
                guest.last_contact = datetime.utcnow()
                db.session.commit()
        except Exception as e:
            logger.error(f"Error updating last_contact: {e}")
            db.session.rollback()

    def get_guest_memory_summary(self, guest_id: int) -> str:
        """
        Get a human-readable summary of guest memories.

        Args:
            guest_id: The guest ID

        Returns:
            Formatted summary string
        """
        profile = self.get_guest_profile(guest_id)
        if not profile:
            return "No guest profile found"

        parts = []

        if profile.get('name'):
            parts.append(f"Name: {profile['name']}")

        if profile.get('language'):
            parts.append(f"Language: {profile['language']}")

        if profile.get('family'):
            family_str = ", ".join([f"{f['value']} ({f['key']})" for f in profile['family']])
            parts.append(f"Family: {family_str}")

        if profile.get('pets'):
            pets_str = ", ".join([f"{p['value']} ({p['key']})" for p in profile['pets']])
            parts.append(f"Pets: {pets_str}")

        if profile.get('preferences'):
            prefs_str = ", ".join([f"{p['key']}: {p['value']}" for p in profile['preferences']])
            parts.append(f"Preferences: {prefs_str}")

        if profile.get('allergies'):
            allergies_str = ", ".join([f"{a['value']}" for a in profile['allergies']])
            parts.append(f"Allergies: {allergies_str}")

        if profile.get('total_stays', 0) > 0:
            parts.append(f"Total stays: {profile['total_stays']}")

        return " | ".join(parts) if parts else "No details stored"

    def delete_guest_detail(self, detail_id: int) -> bool:
        """Delete a specific guest detail by ID"""
        try:
            detail = GuestDetail.query.get(detail_id)
            if detail:
                db.session.delete(detail)
                db.session.commit()
                logger.info(f"Deleted guest detail {detail_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting detail: {e}")
            db.session.rollback()
            return False

    def get_all_guest_details(self, guest_id: int, detail_type: Optional[str] = None) -> List[GuestDetail]:
        """
        Get all details for a guest, optionally filtered by type.

        Args:
            guest_id: The guest ID
            detail_type: Optional filter by type

        Returns:
            List of GuestDetail objects
        """
        query = GuestDetail.query.filter_by(guest_id=guest_id)
        if detail_type:
            query = query.filter_by(detail_type=detail_type)
        return query.order_by(GuestDetail.extracted_at.desc()).all()


# Global instance
_memory_service: Optional[MemoryService] = None


def init_memory_service() -> MemoryService:
    """Initialize the memory service"""
    global _memory_service
    _memory_service = MemoryService()
    logger.info("Memory Service initialized")
    return _memory_service


def get_memory_service() -> Optional[MemoryService]:
    """Get the current memory service instance"""
    return _memory_service
