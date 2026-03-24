"""
Push Notification Service for ChatBotAI
Manages VAPID keys, Web Push subscriptions, and sending push notifications.
"""

import json
import logging
import base64
from typing import Optional

from pywebpush import webpush, WebPushException

logger = logging.getLogger(__name__)


class PushService:
    """Web Push notification service using VAPID"""

    def __init__(self, claim_email: str = 'mailto:admin@chatbotai.local'):
        self.claim_email = claim_email
        self._private_key = None
        self._public_key = None

    def _ensure_keys(self):
        """Load or generate VAPID keys (stored in AISettings table)."""
        if self._private_key and self._public_key:
            return

        from ..models import AISettings, db

        priv = AISettings.get('vapid_private_key')
        pub = AISettings.get('vapid_public_key')

        if priv and pub:
            self._private_key = priv
            self._public_key = pub
            logger.info("VAPID keys loaded from database")
            return

        # Generate new EC P-256 keypair
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization

        key = ec.generate_private_key(ec.SECP256R1())

        # Private key: raw 32-byte integer, base64url-encoded
        priv_numbers = key.private_numbers()
        priv_bytes = priv_numbers.private_value.to_bytes(32, byteorder='big')
        priv_b64 = base64.urlsafe_b64encode(priv_bytes).rstrip(b'=').decode('ascii')

        # Public key: uncompressed point (65 bytes), base64url-encoded
        pub_bytes = key.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint
        )
        pub_b64 = base64.urlsafe_b64encode(pub_bytes).rstrip(b'=').decode('ascii')

        AISettings.set('vapid_private_key', priv_b64, 'VAPID private key (auto-generated)')
        AISettings.set('vapid_public_key', pub_b64, 'VAPID public key (auto-generated)')

        self._private_key = priv_b64
        self._public_key = pub_b64
        logger.info("VAPID keys generated and saved")

    def get_public_key(self) -> str:
        """Return the VAPID public key (base64url-encoded) for the frontend."""
        self._ensure_keys()
        return self._public_key

    def send_notification_to_user(self, user_id: int, title: str, body: str, url: str = None, tag: str = None):
        """Send a push notification to all devices for a given user."""
        from ..models import PushSubscription, db

        self._ensure_keys()

        subscriptions = PushSubscription.query.filter_by(user_id=user_id).all()
        if not subscriptions:
            return

        payload = json.dumps({
            'title': title,
            'body': body,
            'url': url or '/chatbot/',
            'tag': tag or 'chatbotai'
        })

        vapid_claims = {
            'sub': self.claim_email
        }

        expired = []
        for sub in subscriptions:
            try:
                webpush(
                    subscription_info={
                        'endpoint': sub.endpoint,
                        'keys': {
                            'p256dh': sub.p256dh,
                            'auth': sub.auth
                        }
                    },
                    data=payload,
                    vapid_private_key=self._private_key,
                    vapid_claims=vapid_claims
                )
            except WebPushException as e:
                if e.response and e.response.status_code in (404, 410):
                    # Subscription expired or unsubscribed
                    expired.append(sub)
                    logger.info(f"Push subscription {sub.id} expired, will remove")
                else:
                    logger.warning(f"Push to subscription {sub.id} failed: {e}")
            except Exception as e:
                logger.warning(f"Push to subscription {sub.id} failed: {e}")

        # Clean up expired subscriptions
        if expired:
            for sub in expired:
                db.session.delete(sub)
            db.session.commit()

    def notify_new_guest_message(self, conversation, message_content: str, guest_name: str):
        """Send push notification for a new guest message.
        Assignment-aware: notifies assigned user or all users if unassigned."""
        from ..models import User

        title = guest_name or 'New message'
        body = message_content[:120] + ('...' if len(message_content) > 120 else '')
        url = f'/chatbot/conversation/{conversation.id}'
        tag = f'conv-{conversation.id}'

        if conversation.user_id:
            # Notify only the assigned user
            self.send_notification_to_user(conversation.user_id, title, body, url, tag)
        else:
            # Notify all users
            users = User.query.all()
            for user in users:
                self.send_notification_to_user(user.id, title, body, url, tag)

    def notify_escalation(self, conversation, guest_name: str):
        """Send push notification when a conversation is escalated.
        Assignment-aware: notifies assigned user or all users if unassigned."""
        from ..models import User

        title = 'Braucht Aufmerksamkeit'
        body = guest_name
        url = f'/chatbot/conversation/{conversation.id}'
        tag = f'escalation-{conversation.id}'

        if conversation.user_id:
            self.send_notification_to_user(conversation.user_id, title, body, url, tag)
        else:
            users = User.query.all()
            for user in users:
                self.send_notification_to_user(user.id, title, body, url, tag)


# Global instance
_push_service: Optional[PushService] = None


def init_push_service(app=None) -> PushService:
    """Initialize the push service"""
    global _push_service
    claim_email = 'mailto:admin@chatbotai.local'
    if app:
        claim_email = app.config.get('VAPID_CLAIM_EMAIL', claim_email)
    _push_service = PushService(claim_email=claim_email)
    logger.info("Push Service initialized")
    return _push_service


def get_push_service() -> Optional[PushService]:
    """Get the current push service instance"""
    return _push_service
