"""
Message Router for ChatBotAI
Central orchestrator that handles the complete message flow:
1. Message arrives (from any platform)
2. Identify/create guest
3. Create/update conversation
4. Store message
5. Extract memory (background)
6. Generate AI response (if enabled)
7. Return response
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from sqlalchemy.exc import IntegrityError

from ..models import db, Guest, Conversation, Message, Property, AISettings, KnowledgeEntry
from .ai_service import get_ai_service
from .memory_service import get_memory_service, MemoryService

logger = logging.getLogger(__name__)

from .playtest_events import playtest_log


class MessageRouter:
    """Central message routing and processing service"""

    def __init__(self):
        self.ai_service = None
        self.memory_service = None

    def _get_services(self):
        """Lazy load services"""
        if not self.ai_service:
            self.ai_service = get_ai_service()
        if not self.memory_service:
            self.memory_service = get_memory_service()

    def process_incoming_message(
            self,
            platform: str,
            platform_conversation_id: str,
            sender_email: Optional[str] = None,
            sender_phone: Optional[str] = None,
            sender_name: Optional[str] = None,
            platform_user_id: Optional[str] = None,
            message_content: str = "",
            subject: Optional[str] = None,
            platform_message_id: Optional[str] = None,
            property_id: Optional[int] = None,
            auto_respond: bool = True,
            sent_at: Optional[datetime] = None,
            skip_push: bool = False
    ) -> Dict[str, Any]:
        """
        Process an incoming message from any platform.

        This is the main entry point for all incoming messages.

        Args:
            platform: Source platform (email, whatsapp, airbnb, booking)
            platform_conversation_id: Platform's conversation/thread ID
            sender_email: Guest's email address
            sender_phone: Guest's phone number
            sender_name: Guest's name (if known)
            platform_user_id: Platform-specific user ID
            message_content: The message text
            subject: Email subject or conversation topic
            platform_message_id: Platform's message ID
            property_id: Associated property (if known)
            auto_respond: Whether to generate AI response

        Returns:
            Dict with processing results including any AI response
        """
        self._get_services()

        result = {
            'success': False,
            'guest_id': None,
            'conversation_id': None,
            'message_id': None,
            'ai_response': None,
            'ai_response_id': None,
            'extracted_info': None,
            'error': None
        }

        try:
            # Step 1: Find or create guest
            guest = self._find_or_create_guest(
                email=sender_email,
                phone=sender_phone,
                name=sender_name,
                platform=platform,
                platform_id=platform_user_id
            )
            result['guest_id'] = guest.id
            logger.info(f"Guest identified: {guest.id} ({guest.name or guest.email or 'Unknown'})")

            # Step 2: Find or create conversation
            conversation = self._find_or_create_conversation(
                guest_id=guest.id,
                platform=platform,
                platform_id=platform_conversation_id,
                subject=subject,
                property_id=property_id
            )
            result['conversation_id'] = conversation.id
            logger.info(f"Conversation: {conversation.id} ({platform})")

            # Step 3: Store the incoming message (returns existing if duplicate)
            message, is_new = self._store_message(
                conversation_id=conversation.id,
                sender_type='guest',
                content=message_content,
                platform_message_id=platform_message_id,
                sent_at=sent_at
            )
            result['message_id'] = message.id

            if not is_new:
                logger.info(f"Duplicate message skipped: {message.id} (platform_message_id={platform_message_id})")
                if conversation.platform == 'playtest':
                    playtest_log(conversation.id, 'dedup_check',
                                 f'Duplicate skipped — existing message #{message.id} '
                                 f'(platform_message_id={platform_message_id})')
                result['success'] = True
                result['is_new'] = False
                return result

            logger.info(f"Message stored: {message.id}")

            if conversation.platform == 'playtest':
                playtest_log(conversation.id, 'guest_message_stored',
                             f'Message #{message.id}: "{message_content[:80]}"')

            # Step 4: Update conversation timestamps and unread state
            msg_ts = message.sent_at or datetime.utcnow()
            now_ts = datetime.utcnow()
            old_updated_at = conversation.updated_at
            is_forward = not old_updated_at or msg_ts > old_updated_at

            # Update sync watermark to the newest message timestamp
            if not conversation.last_synced_message_at or msg_ts > conversation.last_synced_message_at:
                conversation.last_synced_message_at = msg_ts

            # updated_at remains the polling tripwire — always bump it so
            # clients refresh, even for out-of-order deliveries.
            conversation.updated_at = msg_ts if is_forward else max(old_updated_at, now_ts)

            # last_message_at is the sort key — only advance it when this
            # message is genuinely the newest one we've seen for this
            # conversation. Out-of-order syncs MUST NOT push older threads
            # to the top of the inbox.
            if not conversation.last_message_at or msg_ts > conversation.last_message_at:
                conversation.last_message_at = msg_ts

            if is_forward:
                # Genuinely new message — mark unread
                conversation.is_read = False
            else:
                # Out-of-order delivery — recompute unread from the read cursor
                # rather than blindly marking unread
                conversation.recompute_is_read()
            guest.last_contact = datetime.utcnow()
            db.session.commit()

            # Step 5: Send push notification (skip if AI is auto-responding or caller requested skip)
            if skip_push:
                logger.debug(f"Skipping push notification — caller requested skip for conversation {conversation.id}")
            elif not conversation.auto_respond:
                try:
                    from .push_service import get_push_service
                    push = get_push_service()
                    if push:
                        push.notify_new_guest_message(
                            conversation, message_content,
                            guest.name or guest.email or 'Guest'
                        )
                except Exception as e:
                    logger.warning(f"Push notification failed: {e}")
            else:
                logger.debug(f"Skipping push notification — AI auto-respond active for conversation {conversation.id}")

            # Step 6: Process message for memory extraction (async-friendly)
            if self.memory_service:
                try:
                    self.memory_service.process_message_for_memory(message)
                    logger.info(f"Memory extraction completed for message {message.id}")
                    if conversation.platform == 'playtest':
                        playtest_log(conversation.id, 'memory_extraction',
                                     f'Memory extraction completed for message #{message.id}')
                except Exception as e:
                    logger.warning(f"Memory extraction failed: {e}")
                    if conversation.platform == 'playtest':
                        playtest_log(conversation.id, 'memory_extraction',
                                     f'Memory extraction failed: {e}')

            # Step 7: Generate AI response if enabled
            # Master switch overrides everything — when OFF, no auto-responses anywhere
            master_ai = AISettings.get('master_ai_enabled', 'true') == 'true'
            # auto_respond parameter = caller explicitly requests it (e.g. test routes)
            # conversation.auto_respond = per-conversation toggle set by user
            should_auto_respond = master_ai and (auto_respond or conversation.auto_respond) and conversation.ai_enabled
            if should_auto_respond:
                ai_result = self._generate_ai_response(conversation, message)
                if ai_result:
                    if ai_result.get('approval_status') == 'pending':
                        result['ai_response'] = None
                        result['ai_response_id'] = None
                        result['pending_approval'] = True
                        logger.info(f"AI response saved as pending draft: {ai_result['message_id']}")
                    else:
                        result['ai_response'] = ai_result.get('content')
                        result['ai_response_id'] = ai_result.get('message_id')
                        logger.info(f"AI response generated: {ai_result['message_id']}")

            result['success'] = True

        except Exception as e:
            logger.error(f"Error processing incoming message: {e}")
            result['error'] = str(e)
            db.session.rollback()

        return result

    def process_owner_message(
            self,
            conversation_id: int,
            content: str,
            extract_memory: bool = True,
            platform_message_id: Optional[str] = None,
            sent_via_app: bool = False
    ) -> Dict[str, Any]:
        """
        Process an outgoing message from the owner.

        Args:
            conversation_id: The conversation to add message to
            content: Message text
            extract_memory: Whether to extract guest info from this message
            platform_message_id: Optional platform message ID for duplicate detection

        Returns:
            Dict with message details
        """
        self._get_services()

        result = {
            'success': False,
            'message_id': None,
            'error': None
        }

        try:
            conversation = Conversation.query.get(conversation_id)
            if not conversation:
                result['error'] = 'Conversation not found'
                return result

            # Store owner message
            message, _ = self._store_message(
                conversation_id=conversation_id,
                sender_type='owner',
                content=content,
                platform_message_id=platform_message_id,
                sent_via_app=sent_via_app
            )
            result['message_id'] = message.id

            if conversation.platform == 'playtest':
                playtest_log(conversation.id, 'owner_message_stored',
                             f'Owner message #{message.id}: "{content[:80]}"')

            # Update conversation timestamps. updated_at = tripwire, bumped
            # every time. last_message_at = sort key, set to this message's
            # real sent_at.
            now_ts = datetime.utcnow()
            conversation.updated_at = now_ts
            msg_sent_at = message.sent_at or now_ts
            if not conversation.last_message_at or msg_sent_at > conversation.last_message_at:
                conversation.last_message_at = msg_sent_at
            db.session.commit()

            # Extract memory from owner message (owners often mention guest details)
            if extract_memory and self.memory_service:
                try:
                    self.memory_service.process_message_for_memory(message)
                except Exception as e:
                    logger.warning(f"Memory extraction from owner message failed: {e}")

            result['success'] = True

        except Exception as e:
            logger.error(f"Error processing owner message: {e}")
            result['error'] = str(e)
            db.session.rollback()

        return result

    def generate_ai_response_for_conversation(
            self,
            conversation_id: int,
            save_message: bool = True
    ) -> Dict[str, Any]:
        """
        Generate an AI response for a conversation.

        Args:
            conversation_id: The conversation to respond to
            save_message: Whether to save the AI response as a message

        Returns:
            Dict with AI response details
        """
        self._get_services()

        result = {
            'success': False,
            'response': None,
            'message_id': None,
            'error': None
        }

        try:
            conversation = Conversation.query.get(conversation_id)
            if not conversation:
                result['error'] = 'Conversation not found'
                return result

            if not conversation.ai_enabled:
                result['error'] = 'AI is disabled for this conversation'
                return result

            # Get the last guest message
            last_guest_message = Message.query.filter_by(
                conversation_id=conversation_id,
                sender_type='guest'
            ).order_by(Message.sent_at.desc()).first()

            if not last_guest_message:
                result['error'] = 'No guest message to respond to'
                return result

            # Generate response
            ai_result = self._generate_ai_response(conversation, last_guest_message)

            if ai_result:
                result['success'] = True
                result['response'] = ai_result['content']
                result['message_id'] = ai_result['message_id']
            else:
                result['error'] = 'Failed to generate AI response'

        except Exception as e:
            logger.error(f"Error generating AI response: {e}")
            result['error'] = str(e)

        return result

    def _find_or_create_guest(
            self,
            email: Optional[str] = None,
            phone: Optional[str] = None,
            name: Optional[str] = None,
            platform: Optional[str] = None,
            platform_id: Optional[str] = None
    ) -> Guest:
        """Find existing guest or create new one. Delegates to MemoryService."""
        if self.memory_service:
            return self.memory_service.find_or_create_guest(
                email=email,
                phone=phone,
                platform=platform,
                platform_id=platform_id,
                name=name
            )

        # Fallback if memory service unavailable
        guest = None
        if email:
            guest = Guest.query.filter_by(email=email).first()
        if not guest and phone:
            guest = Guest.query.filter_by(phone=phone).first()
        if not guest:
            guest = Guest(name=name, email=email, phone=phone)
            db.session.add(guest)
            db.session.commit()
        return guest

    def _find_or_create_conversation(
            self,
            guest_id: int,
            platform: str,
            platform_id: str,
            subject: Optional[str] = None,
            property_id: Optional[int] = None
    ) -> Conversation:
        """Find existing conversation or create new one"""

        # Try to find existing conversation
        conversation = Conversation.query.filter_by(
            platform_id=platform_id
        ).first()

        if not conversation:
            auto_respond_default = AISettings.get('auto_respond_new_conversations', 'true') == 'true'
            auto_approve_default = AISettings.get('auto_approve_new_conversations', 'false') == 'true'
            conversation = Conversation(
                guest_id=guest_id,
                platform=platform,
                platform_id=platform_id,
                subject=subject,
                property_id=property_id,
                status='active',
                ai_enabled=True,
                auto_respond=auto_respond_default,
                auto_approve=auto_approve_default,
                is_read=False
            )
            db.session.add(conversation)
            db.session.commit()
            logger.info(f"Created new conversation: {conversation.id}")
        else:
            # Update conversation metadata (unread state set later after dedup check)
            if subject and not conversation.subject:
                conversation.subject = subject
            db.session.commit()

        return conversation

    def _store_message(
            self,
            conversation_id: int,
            sender_type: str,
            content: str,
            platform_message_id: Optional[str] = None,
            sent_at: Optional[datetime] = None,
            sent_via_app: bool = False
    ) -> Tuple[Message, bool]:
        """Store a message in the database, skipping duplicates by platform_message_id.

        Returns:
            Tuple of (message, is_new) - is_new is False if duplicate was detected
        """

        # Check for duplicate by platform_message_id
        if platform_message_id:
            existing = Message.query.filter_by(
                conversation_id=conversation_id,
                platform_message_id=platform_message_id
            ).first()
            if existing:
                logger.debug(f"Skipping duplicate message: platform_message_id={platform_message_id}")
                return existing, False

        message = Message(
            conversation_id=conversation_id,
            sender_type=sender_type,
            content=content,
            platform_message_id=platform_message_id,
            sent_at=sent_at or datetime.utcnow(),
            is_processed=False,
            sent_via_app=sent_via_app
        )
        db.session.add(message)
        try:
            db.session.commit()
        except IntegrityError:
            # Another concurrent path inserted the same platform_message_id first.
            # Roll back, fetch the row that won the race, return it as the existing.
            db.session.rollback()
            if platform_message_id:
                existing = Message.query.filter_by(
                    conversation_id=conversation_id,
                    platform_message_id=platform_message_id,
                ).first()
                if existing:
                    logger.debug(
                        "Concurrent insert detected for platform_message_id=%s, returning existing #%s",
                        platform_message_id, existing.id,
                    )
                    return existing, False
            # No platform_message_id (rare) — re-raise so the caller sees the error
            raise

        return message, True

    @staticmethod
    def _is_escalation_response(response_text: str) -> bool:
        """Check if AI response contains escalation phrases.

        Detects when the AI has used the escalation holding response
        (e.g. "I'll check with my colleague"). Uses only high-specificity
        phrases to avoid false positives.
        """
        if not response_text:
            return False
        text_lower = response_text.lower()
        escalation_phrases = ['kollegen', 'kollegin', 'colleague']
        return any(phrase in text_lower for phrase in escalation_phrases)

    def _generate_ai_response(
            self,
            conversation: Conversation,
            trigger_message: Message
    ) -> Optional[Dict[str, Any]]:
        """Generate and store an AI response"""

        if not self.ai_service:
            logger.warning("AI service not available")
            return None

        # Check if the trigger message is a pure acknowledgment (Ok, Gut, etc.)
        if self.ai_service.is_acknowledgment(trigger_message.content):
            logger.info(f"[AI SKIP] Acknowledgment detected in auto-respond: "
                        f"'{trigger_message.content[:50]}' — skipping AI response")
            if conversation.platform == 'playtest':
                playtest_log(conversation.id, 'acknowledgment_skipped',
                             f'Acknowledgment detected: "{trigger_message.content[:50]}" — skipping AI')
            return None

        if conversation.platform == 'playtest':
            playtest_log(conversation.id, 'ai_generation_start',
                         f'Generating AI response for: "{trigger_message.content[:80]}"')

        # Delete any existing pending draft for this conversation.
        # with_for_update() is a no-op on SQLite but locks the row on Postgres
        # to prevent two concurrent regen calls from both reading the same
        # draft and both proceeding to create replacements.
        try:
            existing_pending = Message.query.filter_by(
                conversation_id=conversation.id,
                approval_status='pending'
            ).with_for_update(skip_locked=True).first()
        except Exception:
            # SQLite (or older drivers) may not support with_for_update — fall back.
            existing_pending = Message.query.filter_by(
                conversation_id=conversation.id,
                approval_status='pending'
            ).first()
        if existing_pending:
            try:
                db.session.delete(existing_pending)
                db.session.commit()
                logger.info(f"Replaced existing pending draft (message_id={existing_pending.id})")
            except Exception as e:
                # Another worker may have already deleted it — that's fine.
                db.session.rollback()
                logger.info(f"Pending draft delete race (already gone): {e}")

        # Read AI settings from DB
        tone = AISettings.get('ai_response_tone', 'friendly_professional')
        host_instructions = AISettings.get('host_instructions', '')
        max_history = int(AISettings.get('max_conversation_history', '10'))

        # --- Conversation summary for long conversations ---
        conversation_summary = conversation.ai_summary  # Use cached by default
        total_msg_count = Message.query.filter_by(conversation_id=conversation.id).count()

        if total_msg_count > max_history:
            # Find the cutoff message (the oldest message that WON'T be in recent history)
            cutoff_msg = Message.query.filter_by(
                conversation_id=conversation.id
            ).order_by(Message.sent_at.desc()).offset(max_history).first()

            if cutoff_msg:
                summary_is_stale = (
                    conversation.ai_summary_through_id is None
                    or cutoff_msg.id > conversation.ai_summary_through_id
                )

                if summary_is_stale and self.ai_service:
                    try:
                        # Fetch messages to summarize (between last summary and cutoff)
                        summary_query = Message.query.filter_by(
                            conversation_id=conversation.id
                        ).filter(
                            Message.id <= cutoff_msg.id
                        )
                        if conversation.ai_summary_through_id:
                            summary_query = summary_query.filter(
                                Message.id > conversation.ai_summary_through_id
                            )
                        msgs_to_summarize = summary_query.order_by(
                            Message.sent_at.asc()
                        ).limit(50).all()

                        if msgs_to_summarize:
                            summary_result = self.ai_service.generate_conversation_summary(
                                [m.to_dict() for m in msgs_to_summarize],
                                existing_summary=conversation.ai_summary
                            )
                            if summary_result:
                                conversation.ai_summary = summary_result
                                # Track through the last message actually summarized
                                # (not cutoff_msg.id - the .limit(50) may not reach it)
                                conversation.ai_summary_through_id = msgs_to_summarize[-1].id
                                conversation_summary = summary_result
                                db.session.commit()
                                logger.info(f"[SUMMARY] Updated summary for conversation {conversation.id} "
                                            f"(through msg {msgs_to_summarize[-1].id})")
                    except Exception as e:
                        logger.warning(f"[SUMMARY] Failed to update summary for conversation {conversation.id}: {e}")
                        # Proceed with existing cached summary (or None)

        # Get conversation history (exclude pending/rejected drafts)
        messages = Message.query.filter_by(
            conversation_id=conversation.id
        ).filter(
            db.or_(Message.approval_status.is_(None), Message.approval_status == 'approved')
        ).order_by(Message.sent_at.desc()).limit(max_history).all()
        messages.reverse()

        # Get guest profile
        profile = {}
        if self.memory_service:
            profile = self.memory_service.get_guest_profile(conversation.guest_id)

        # Get property info
        property_info = None
        if conversation.property_id:
            prop = Property.query.get(conversation.property_id)
            if prop:
                property_info = prop.to_dict()

        # Fetch Smoobu reservation details if applicable
        reservation_info = None
        if conversation.platform == 'smoobu' and conversation.smoobu_reservation_id:
            try:
                from .smoobu_service import get_smoobu_service
                smoobu = get_smoobu_service()
                if smoobu and smoobu.is_configured():
                    reservation_info = smoobu.get_reservation(conversation.smoobu_reservation_id)
            except Exception as e:
                logger.warning(f"Failed to fetch Smoobu reservation: {e}")

        # Load knowledge base entries for AI context (exclude corrections)
        knowledge_entries = []
        try:
            if conversation.property_id:
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
        except Exception as e:
            logger.warning(f"Failed to load knowledge entries: {e}")

        # Load past corrections for AI context
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

        if conversation.platform == 'playtest':
            playtest_log(conversation.id, 'context_filter',
                         f'Context filter: {filtered.filter_log}')

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

        if not response_text:
            return None

        if conversation.platform == 'playtest':
            playtest_log(conversation.id, 'ai_response_generated',
                         f'AI response generated ({len(response_text)} chars): '
                         f'"{response_text[:100]}"')

        # Store AI response in a dedicated transaction so a commit failure
        # surfaces explicitly (escalates the conversation) instead of being
        # silently swallowed by the outer process_incoming_message handler.
        ai_message = Message(
            conversation_id=conversation.id,
            sender_type='ai',
            content=response_text,
            sent_at=datetime.utcnow(),
            is_processed=True,  # AI messages don't need memory extraction
            sent_via_app=True
        )
        db.session.add(ai_message)
        now_ts = datetime.utcnow()
        conversation.updated_at = now_ts
        ai_sent_at = ai_message.sent_at or now_ts
        if not conversation.last_message_at or ai_sent_at > conversation.last_message_at:
            conversation.last_message_at = ai_sent_at
        try:
            db.session.commit()
        except Exception as commit_err:
            db.session.rollback()
            logger.exception(
                f"[AI PERSIST FAIL] Could not store AI draft for conversation "
                f"{conversation.id}: {commit_err}"
            )
            # Escalate so the team sees the conversation needs attention
            # rather than silently dropping the response.
            try:
                conversation.escalated = True
                conversation.escalated_at = datetime.utcnow()
                db.session.commit()
            except Exception:
                db.session.rollback()
                logger.exception("[AI PERSIST FAIL] Escalation flag write failed too")
            if conversation.platform == 'playtest':
                playtest_log(conversation.id, 'ai_persist_failed',
                             f'AI response could not be saved: {commit_err}')
            return None

        # Check if this should be a pending draft
        approval_queue_enabled = AISettings.get('approval_queue_enabled', 'true') == 'true'

        if approval_queue_enabled and not conversation.auto_approve:
            # Save as pending draft — do NOT send
            ai_message.approval_status = 'pending'
            db.session.commit()
            logger.info(f"AI response saved as pending draft (message_id={ai_message.id})")
            if conversation.platform == 'playtest':
                playtest_log(conversation.id, 'approval_status',
                             f'Saved as PENDING draft (message #{ai_message.id}) — approval queue active')
            return {
                'content': response_text,
                'message_id': ai_message.id,
                'approval_status': 'pending'
            }
        else:
            # Auto-approve path: send immediately (existing behavior)
            if conversation.platform == 'playtest':
                playtest_log(conversation.id, 'approval_status',
                             f'Auto-approved (message #{ai_message.id}) — '
                             f'platform delivery skipped (playtest mode)')

            # Send via Smoobu for smoobu conversations (auto-respond flow)
            smoobu_sent = False
            if conversation.platform == 'smoobu' and conversation.auto_respond and conversation.smoobu_reservation_id:
                try:
                    from .smoobu_service import get_smoobu_service
                    smoobu = get_smoobu_service()
                    if smoobu and smoobu.is_configured():
                        send_result = smoobu.send_message(conversation.smoobu_reservation_id, response_text)
                        smoobu_sent = bool(send_result)
                        if smoobu_sent:
                            logger.info(f"Auto-respond Smoobu message sent for conversation {conversation.id}")
                        else:
                            logger.warning(f"Failed to send auto-respond Smoobu message for conversation {conversation.id}")
                except Exception as e:
                    logger.error(f"Error sending auto-respond Smoobu message: {e}")

            # Send via Gmail for email conversations (auto-respond flow)
            email_sent = False
            if conversation.platform == 'email' and conversation.auto_respond:
                try:
                    from .gmail_service import get_gmail_service
                    gmail = get_gmail_service()
                    if gmail.is_authenticated():
                        guest = conversation.guest
                        send_result = gmail.send_email(
                            to=guest.email,
                            subject=conversation.subject or 'Re: Your inquiry',
                            body=response_text,
                            thread_id=conversation.platform_id,
                            reply_to_message_id=trigger_message.platform_message_id
                        )
                        email_sent = bool(send_result)
                        if email_sent:
                            logger.info(f"Auto-respond email sent for conversation {conversation.id}")
                        else:
                            logger.warning(f"Failed to send auto-respond email for conversation {conversation.id}")
                except Exception as e:
                    logger.error(f"Error sending auto-respond email: {e}")

            # Check for escalation response — AFTER platform send, so the holding
            # message reaches the guest before we pause auto-respond
            if self._is_escalation_response(response_text):
                conversation.escalated = True
                conversation.escalated_at = datetime.utcnow()
                conversation.auto_respond = False
                db.session.commit()
                logger.info(f"[ESCALATION] Conversation {conversation.id} escalated — auto-respond paused")
                if conversation.platform == 'playtest':
                    playtest_log(conversation.id, 'escalation_check',
                                 'Escalation TRIGGERED — auto-respond paused')

                # Send escalation push notification
                try:
                    from .push_service import get_push_service
                    push = get_push_service()
                    if push:
                        guest = conversation.guest
                        push.notify_escalation(
                            conversation,
                            guest.name or guest.email or 'Guest'
                        )
                except Exception as e:
                    logger.warning(f"Escalation push notification failed: {e}")

            return {
                'content': response_text,
                'message_id': ai_message.id,
                'email_sent': email_sent
            }

    def create_test_conversation(
            self,
            guest_name: str = "Test Guest",
            guest_email: str = "test@example.com",
            platform: str = "email",
            subject: str = "Test Conversation",
            initial_message: str = "Hello, I'm interested in booking your property."
    ) -> Dict[str, Any]:
        """
        Create a test conversation with sample data.
        Useful for testing the UI without real integrations.
        """
        import uuid

        result = self.process_incoming_message(
            platform=platform,
            platform_conversation_id=f"test-{uuid.uuid4().hex[:8]}",
            sender_email=guest_email,
            sender_name=guest_name,
            message_content=initial_message,
            subject=subject,
            auto_respond=True
        )

        return result


# Global instance
_message_router: Optional[MessageRouter] = None


def init_message_router() -> MessageRouter:
    """Initialize the message router"""
    global _message_router
    _message_router = MessageRouter()
    logger.info("Message Router initialized")
    return _message_router


def get_message_router() -> Optional[MessageRouter]:
    """Get the current message router instance"""
    global _message_router
    if not _message_router:
        _message_router = MessageRouter()
    return _message_router
