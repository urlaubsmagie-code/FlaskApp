"""Rule-based instant answers for Booking's templated guest messages.

Booking.com sends a canned arrival-time request on the guest's behalf
("Ich möchte einen Check-in um 15:00 - 16:00 Uhr"). It is a large, perfectly
predictable share of inbound traffic and needs no LLM to answer — a fixed
acknowledgement is correct every time, instant, and costs nothing.

Deliberately NOT an AI path: no model call, no prompt, no knowledge lookup.
Off by default — nothing reaches a guest until `checkin_autoreply_enabled` is
switched on in Settings.
"""
import logging
import re
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Booking's templated arrival-time request, German and English wordings. The
# time itself varies, so it is matched loosely; the surrounding template is what
# identifies the message.
_CHECKIN_PATTERNS = (
    # möchte / mochte / moechte — guests type all three.
    re.compile(r'ich\s+m(?:ö|oe|o)chte\s+einen\s+check[-\s]?in\s+um\s+\d{1,2}[:.]\d{2}', re.I),
    re.compile(r'i\s+would\s+like\s+to\s+check[-\s]?in\s+(?:at|around)\s+\d{1,2}[:.]\d{2}', re.I),
    re.compile(r'i\s+will\s+arrive\s+(?:at|around)\s+\d{1,2}[:.]\d{2}', re.I),
)

DEFAULT_TEXT_DE = (
    "Vielen Dank für die Info zu Ihrer Ankunftszeit — wir haben sie notiert. "
    "Der Check-in ist ab 15:00 Uhr möglich. Sollte sich etwas ändern, "
    "geben Sie uns gerne Bescheid."
)

# A backfill or a re-sync can replay months of old messages through the same
# code path. Without this guard, switching the feature on would blast canned
# replies at guests whose stay ended long ago.
MAX_MESSAGE_AGE_MINUTES = 30


def is_checkin_time_request(text: str) -> bool:
    """True if this is Booking's templated arrival-time message."""
    if not text:
        return False
    return any(p.search(text) for p in _CHECKIN_PATTERNS)


def checkin_autoreply_text() -> str:
    from ..models import AISettings
    return (AISettings.get('checkin_autoreply_text', '') or '').strip() or DEFAULT_TEXT_DE


def should_autoreply(message, conversation, now=None) -> bool:
    """Whether this stored guest message should get the canned check-in answer.

    Every condition here is a reason a real guest could be messaged wrongly, so
    they are all checked before anything is sent.
    """
    from ..models import AISettings

    if AISettings.get('checkin_autoreply_enabled', 'false') != 'true':
        return False
    if message.sender_type != 'guest' or not is_checkin_time_request(message.content):
        return False
    # Escalated chats are a human's problem; never talk over them.
    if getattr(conversation, 'escalated', False):
        return False
    if conversation.platform != 'smoobu' or not conversation.smoobu_reservation_id:
        return False

    now = now or datetime.utcnow()
    sent_at = message.sent_at or now
    if now - sent_at > timedelta(minutes=MAX_MESSAGE_AGE_MINUTES):
        logger.info("check-in autoreply skipped: message %s is older than %d min",
                    message.id, MAX_MESSAGE_AGE_MINUTES)
        return False
    return True


def send_checkin_autoreply(message, conversation) -> bool:
    """Send the canned answer through Smoobu. Returns True if it went out."""
    from .smoobu_service import get_smoobu_service_for

    smoobu = get_smoobu_service_for(conversation)
    if not smoobu or not smoobu.is_configured():
        return False

    text = checkin_autoreply_text()
    try:
        sent = smoobu.send_message(conversation.smoobu_reservation_id, text)
    except Exception:
        logger.exception("check-in autoreply: Smoobu send failed for conv %s", conversation.id)
        return False
    if not sent:
        return False

    smoobu_msg_id = None
    if isinstance(sent, dict):
        smoobu_msg_id = str(sent.get('id') or sent.get('message_id') or sent.get('messageId') or '')
    from .message_router import get_message_router
    get_message_router().process_owner_message(
        conversation_id=conversation.id,
        content=text,
        extract_memory=False,
        platform_message_id=(f"smoobu-{conversation.smoobu_reservation_id}-{smoobu_msg_id}"
                             if smoobu_msg_id else None),
        sent_via_app=True,
    )
    logger.info("check-in autoreply sent for conversation %s", conversation.id)
    return True
