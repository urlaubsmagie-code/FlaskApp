"""
Smoobu Service for ChatBotAI
Handles all interactions with the Smoobu messaging and reservation API.
"""

import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Dict, List, Any

import requests

logger = logging.getLogger(__name__)


def _parse_smoobu_timestamp(raw) -> 'datetime | None':
    """Parse a Smoobu timestamp string to a naive UTC datetime.

    Smoobu may return timestamps with timezone offsets (e.g. +01:00 for CET).
    We convert to UTC before stripping tzinfo so all stored datetimes are
    consistently UTC — matching ``datetime.utcnow()`` used elsewhere.
    """
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return None


def _normalize_content(text: str) -> str:
    """Normalize message content for dedup comparison.

    Smoobu wraps outbox messages in an HTML document structure.  The plain-text
    ``message`` field retains the structural whitespace (newlines, indentation)
    from the HTML skeleton.  Stripping alone may not collapse internal runs of
    whitespace, so we additionally collapse all whitespace sequences to a single
    space and lower-case the result for a robust comparison.
    """
    text = re.sub(r'\s+', ' ', text).strip().lower()
    return text


def _parse_smoobu_date(value):
    """Parse a Smoobu date string (YYYY-MM-DD) into a date object, or None."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except (ValueError, TypeError):
        return None


class SmoobuService:
    """Service for interacting with the Smoobu API"""

    def __init__(self, api_url: str = 'https://login.smoobu.com/api', api_key: str = ''):
        self.api_url = api_url.rstrip('/')
        self._api_key = api_key

    @property
    def api_key(self) -> str:
        """Get API key — prefer DB-stored value over config."""
        try:
            from ..models import AISettings
            db_key = AISettings.get('smoobu_api_key')
            if db_key:
                return db_key
        except Exception:
            pass
        return self._api_key

    # Track rate-limit state across requests
    _rate_limit_remaining: Optional[int] = None
    _rate_limit_retry_after: Optional[float] = None

    def _request(self, method: str, endpoint: str, **kwargs) -> Optional[requests.Response]:
        """Centralized HTTP request with Api-Key header, rate-limit handling, and retry."""
        key = self.api_key
        if not key:
            logger.warning("Smoobu API key not configured")
            return None

        # Respect rate-limit: wait if we know we're blocked
        import time
        if self._rate_limit_retry_after and time.time() < self._rate_limit_retry_after:
            wait = self._rate_limit_retry_after - time.time()
            logger.info(f"Smoobu rate limit: waiting {wait:.1f}s before {method} {endpoint}")
            time.sleep(min(wait, 60))  # Cap wait at 60s

        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        headers = kwargs.pop('headers', {})
        headers['Api-Key'] = key
        headers.setdefault('Content-Type', 'application/json')

        timeout = kwargs.pop('timeout', 30)
        max_retries = 2

        for attempt in range(max_retries + 1):
            t0 = time.time()
            try:
                response = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
                duration_ms = (time.time() - t0) * 1000

                # Track rate-limit headers
                remaining = response.headers.get('X-RateLimit-Remaining')
                if remaining is not None:
                    self._rate_limit_remaining = int(remaining)
                retry_after = response.headers.get('X-RateLimit-Retry-After')
                if retry_after:
                    self._rate_limit_retry_after = float(retry_after)

                if remaining is not None and int(remaining) < 50:
                    logger.warning(f"Smoobu rate limit low: {remaining} requests remaining")

                # Record API call for debug dashboard
                self._track_api_call(method, endpoint, response.status_code, duration_ms)

                # Handle 429 Too Many Requests
                if response.status_code == 429:
                    if attempt < max_retries:
                        wait = 10  # default backoff
                        if retry_after:
                            wait = max(float(retry_after) - time.time(), 1)
                        logger.warning(f"Smoobu 429 rate limited, retrying in {wait:.0f}s (attempt {attempt + 1})")
                        time.sleep(min(wait, 60))
                        continue
                    logger.error(f"Smoobu 429 rate limited, no retries left: {method} {endpoint}")
                    return response

                if response.status_code >= 400:
                    logger.error(f"Smoobu API error: {method} {endpoint} → {response.status_code}: {response.text[:300]}")
                return response
            except requests.exceptions.RequestException as e:
                duration_ms = (time.time() - t0) * 1000
                self._track_api_call(method, endpoint, error=str(e), duration_ms=duration_ms)
                logger.error(f"Smoobu API request failed: {method} {endpoint} → {e}")
                return None

        return None

    @staticmethod
    def _track_api_call(method, endpoint, status_code=None, duration_ms=0, error=None):
        try:
            from .debug_service import get_api_tracker
            tracker = get_api_tracker()
            if tracker:
                tracker.record('smoobu', method, endpoint, status_code, duration_ms, error)
        except Exception:
            pass

    def is_configured(self) -> bool:
        """Check if API key is set."""
        return bool(self.api_key)

    def is_authenticated(self) -> bool:
        """Verify API key by making a test request."""
        if not self.is_configured():
            return False
        resp = self._request('GET', '/apartments')
        return resp is not None and resp.status_code == 200

    def get_status(self) -> Dict[str, Any]:
        """Get connection status."""
        key = self.api_key
        return {
            'configured': bool(key),
            'authenticated': self.is_authenticated() if key else False,
            'api_key_masked': f"...{key[-4:]}" if key and len(key) > 4 else ''
        }

    def disconnect(self):
        """Clear stored API key."""
        try:
            from ..models import AISettings
            AISettings.set('smoobu_api_key', '', description='Smoobu API key')
        except Exception as e:
            logger.error(f"Failed to clear Smoobu API key: {e}")

    # =========================================================================
    # Messaging API
    # =========================================================================

    def get_threads(self, page: int = 1, page_size: int = 50,
                    apartment_ids: Optional[List[str]] = None) -> Optional[Dict]:
        """GET /threads — list messaging threads.

        Args:
            page: Page number (1-based).
            page_size: Results per page.
            apartment_ids: Optional list of apartment IDs to filter by.
        """
        params = f'page_number={page}&page_size={page_size}'
        if apartment_ids:
            for apt_id in apartment_ids:
                params += f'&apartments[]={apt_id}'
        resp = self._request('GET', f'/threads?{params}')
        if resp and resp.status_code == 200:
            return resp.json()
        return None

    def get_reservation_messages(self, reservation_id, page: int = 1,
                                 only_guest: bool = False) -> Optional[Dict]:
        """GET /reservations/{id}/messages — messages for a reservation.

        Args:
            reservation_id: Smoobu booking/reservation ID.
            page: Page number for pagination.
            only_guest: If True, only return guest-related messages.
                        Smoobu defaults to True, so we explicitly set False to get all messages.
        """
        only_guest_val = 'true' if only_guest else 'false'
        params = f'page={page}&onlyRelatedToGuest={only_guest_val}'
        resp = self._request('GET', f'/reservations/{reservation_id}/messages?{params}')
        if resp and resp.status_code == 200:
            return resp.json()
        return None

    def get_all_reservation_messages(self, reservation_id,
                                     only_guest: bool = False) -> Optional[Dict]:
        """Fetch ALL message pages for a reservation (not just page 1).

        Smoobu returns 25 messages per page in chronological order, so new
        messages land on the last page.  This method paginates through all
        pages and returns a merged response with the complete message list.

        Returns:
            Dict with 'messages' (all pages merged), 'total_items', and
            'page_count', or None on failure.
        """
        first_page = self.get_reservation_messages(reservation_id, page=1,
                                                   only_guest=only_guest)
        if not first_page:
            return None

        # If response is a plain list, no pagination info — return as-is
        if not isinstance(first_page, dict):
            return first_page

        page_count = first_page.get('page_count', 1)
        if page_count <= 1:
            return first_page

        # Merge all pages
        all_messages = list(first_page.get('messages') or first_page.get('data')
                            or first_page.get('entries') or [])
        for page_num in range(2, min(page_count + 1, 21)):  # safety cap
            next_page = self.get_reservation_messages(reservation_id,
                                                      page=page_num,
                                                      only_guest=only_guest)
            if not next_page:
                break
            page_msgs = []
            if isinstance(next_page, dict):
                page_msgs = (next_page.get('messages') or next_page.get('data')
                             or next_page.get('entries') or [])
            elif isinstance(next_page, list):
                page_msgs = next_page
            if not page_msgs:
                break
            all_messages.extend(page_msgs)

        # Return merged response preserving the dict structure
        first_page['messages'] = all_messages
        return first_page

    def send_message(self, reservation_id, message_text: str,
                     subject: Optional[str] = None) -> Optional[Dict]:
        """POST /reservations/{id}/messages/send-message-to-guest — send a message to guest.

        Note: Smoobu's send response does NOT include a message ID.  Callers
        store the message with ``platform_message_id=None``; the next sync
        cycle uses the normalized-content fallback dedup to match and backfill
        the ID, preventing duplicates.

        Args:
            reservation_id: Smoobu booking/reservation ID.
            message_text: Message content (HTML or plain text).
            subject: Optional subject line.
        """
        body: Dict[str, Any] = {'messageBody': message_text}
        if subject:
            body['subject'] = subject
        resp = self._request('POST',
                             f'/reservations/{reservation_id}/messages/send-message-to-guest',
                             json=body)
        if resp and resp.status_code in (200, 201):
            return resp.json()
        return None

    # =========================================================================
    # Reservations API
    # =========================================================================

    def get_reservations(self, page: int = 1, from_date: Optional[str] = None) -> Optional[Dict]:
        """GET /reservations — list reservations."""
        params = f'page={page}&page_size=50'
        if from_date:
            params += f'&from={from_date}'
        resp = self._request('GET', f'/reservations?{params}')
        if resp and resp.status_code == 200:
            return resp.json()
        return None

    def get_reservation(self, reservation_id) -> Optional[Dict]:
        """GET /reservations/{id} — single reservation details."""
        resp = self._request('GET', f'/reservations/{reservation_id}')
        if resp and resp.status_code == 200:
            return resp.json()
        return None

    # =========================================================================
    # Apartments API
    # =========================================================================

    def get_apartments(self) -> Optional[Dict]:
        """GET /apartments — list all apartments."""
        resp = self._request('GET', '/apartments')
        if resp and resp.status_code == 200:
            return resp.json()
        return None

    def get_apartment(self, apartment_id) -> Optional[Dict]:
        """GET /apartments/{id} — single apartment details."""
        resp = self._request('GET', f'/apartments/{apartment_id}')
        if resp and resp.status_code == 200:
            return resp.json()
        return None

    # =========================================================================
    # Sync Operations
    # =========================================================================

    # Server-side throttle: prevent multiple users triggering overlapping full syncs
    _last_full_sync: Optional[float] = None
    _FULL_SYNC_COOLDOWN = 30  # seconds — ignore duplicate sync requests within this window

    def sync_messages(self) -> Dict[str, Any]:
        """Fetch Smoobu messaging threads and import new messages via MessageRouter.

        Returns:
            Dict with imported count and errors.
        """
        import time
        from .message_router import get_message_router
        from ..models import db, Conversation, Property

        result = {'success': False, 'imported': 0, 'errors': []}

        # Throttle: skip if another sync completed less than 30s ago
        now = time.time()
        if self._last_full_sync and (now - self._last_full_sync) < self._FULL_SYNC_COOLDOWN:
            logger.debug("Smoobu full sync skipped — cooldown active")
            result['success'] = True
            return result

        # Try messaging/threads first, fall back to reservations
        threads_data = self.get_threads(page_size=100)
        if threads_data:
            logger.info(f"Smoobu threads response keys: {list(threads_data.keys()) if isinstance(threads_data, dict) else 'list'}")
        else:
            logger.warning("Smoobu /threads failed, falling back to /reservations")

        # If threads endpoint failed, use reservations as the source
        if not threads_data:
            threads_data = self.get_reservations()
            if not threads_data:
                result['errors'].append('Failed to fetch messages from Smoobu')
                return result
            logger.info(f"Smoobu reservations response keys: {list(threads_data.keys()) if isinstance(threads_data, dict) else 'list'}")

        router = get_message_router()
        if not router:
            result['errors'].append('MessageRouter not available')
            return result

        # Try all known response structures
        threads = []
        if isinstance(threads_data, list):
            threads = threads_data
        elif isinstance(threads_data, dict):
            threads = (threads_data.get('threads') or threads_data.get('data')
                       or threads_data.get('bookings') or threads_data.get('reservations') or [])

        logger.info(f"Smoobu found {len(threads)} threads/reservations to process")
        if threads and len(threads) > 0:
            logger.info(f"First thread keys: {list(threads[0].keys()) if isinstance(threads[0], dict) else type(threads[0])}")

        # Pre-load all known Smoobu message IDs in one query to avoid per-message DB lookups
        from ..models import Message as MsgModel
        all_smoobu_convs = Conversation.query.filter_by(platform='smoobu').all()
        known_ids_by_conv: Dict[int, set] = {}
        if all_smoobu_convs:
            conv_ids = [c.id for c in all_smoobu_convs]
            rows = db.session.query(MsgModel.conversation_id, MsgModel.platform_message_id).filter(
                MsgModel.conversation_id.in_(conv_ids),
                MsgModel.platform_message_id.isnot(None)
            ).all()
            for conv_id, pmid in rows:
                known_ids_by_conv.setdefault(conv_id, set()).add(pmid)
        # Map platform_id to conversation for quick lookup
        conv_by_platform_id = {c.platform_id: c for c in all_smoobu_convs}

        for thread in threads:
            try:
                # Extract reservation ID: threads nest it as booking.id
                booking = thread.get('booking') or {}
                reservation_id = str(
                    booking.get('id', '') or thread.get('reservation_id')
                    or thread.get('id', '')
                )
                if not reservation_id:
                    continue

                # Fetch page 1 first for quick-check, then all pages if needed
                # (Smoobu returns 25/page oldest-first; new messages land on last page)
                msg_data = self.get_reservation_messages(reservation_id)
                if not msg_data:
                    logger.debug(f"No message data for reservation {reservation_id}")
                    continue

                # Quick check: if we already know all messages, skip this thread
                existing_conv = conv_by_platform_id.get(f"smoobu-{reservation_id}")
                total_from_api = msg_data.get('total_items', 0) if isinstance(msg_data, dict) else len(msg_data if isinstance(msg_data, list) else [])
                if existing_conv:
                    known_ids = known_ids_by_conv.get(existing_conv.id, set())
                    if total_from_api <= len(known_ids):
                        continue

                # New messages exist — fetch remaining pages if any
                page_count = msg_data.get('page_count', 1) if isinstance(msg_data, dict) else 1
                if page_count > 1:
                    msg_data = self.get_all_reservation_messages(reservation_id)
                    if not msg_data:
                        continue

                messages = []
                if isinstance(msg_data, list):
                    messages = msg_data
                elif isinstance(msg_data, dict):
                    messages = (msg_data.get('messages') or msg_data.get('data')
                                or msg_data.get('entries') or [])

                # Track reservation detail fetch (reused for guest enrichment)
                res_detail = None

                # Get guest info: threads nest guest name in booking.guest_name
                guest_name = (booking.get('guest_name') or booking.get('guestName')
                              or thread.get('guest-name') or thread.get('guest_name') or '')
                # Try to get email from reservation detail if not in thread
                guest_email = (thread.get('email') or thread.get('guest_email')
                               or booking.get('email') or '')
                if not guest_email:
                    # Fetch reservation detail which may contain guest email
                    res_detail = self.get_reservation(reservation_id)
                    if res_detail:
                        guest_email = (res_detail.get('email') or res_detail.get('guest-email')
                                       or res_detail.get('guestEmail') or '')
                        # Also fill in guest name from reservation if still empty
                        if not guest_name:
                            firstname = res_detail.get('firstname') or res_detail.get('guest-name') or ''
                            lastname = res_detail.get('lastname') or ''
                            guest_name = f"{firstname} {lastname}".strip()

                # Find property by apartment_id (threads nest it as apartment.id)
                apt = thread.get('apartment') or {}
                apartment_id = str(apt.get('id', '') if isinstance(apt, dict) else
                                   thread.get('apartment_id') or thread.get('apartmentId') or '')
                property_id = None
                if apartment_id:
                    prop = Property.query.filter_by(smoobu_apartment_id=apartment_id).first()
                    if prop:
                        property_id = prop.id

                # Get known IDs for this conversation (for fast duplicate skip)
                conv_known_ids = set()
                if existing_conv:
                    conv_known_ids = known_ids_by_conv.get(existing_conv.id, set())

                for msg in messages:
                    msg_id = str(msg.get('id', ''))
                    platform_msg_id = f"smoobu-{reservation_id}-{msg_id}" if msg_id else None

                    # Skip already imported messages (in-memory check, no DB query)
                    if platform_msg_id and platform_msg_id in conv_known_ids:
                        continue

                    # Smoobu uses 'message' for plain text, 'htmlMessage' for HTML
                    msg_content = (msg.get('message') or msg.get('htmlMessage')
                                   or msg.get('message_body') or msg.get('body') or msg.get('content', ''))
                    if not msg_content or not msg_content.strip():
                        continue
                    msg_content = msg_content.strip()

                    # Determine sender type: Smoobu message type 1=inbox (guest→host), 2=outbox (host→guest)
                    msg_type = msg.get('type')
                    is_from_guest = (msg_type == 1 or msg_type == 'inbox'
                                     or msg.get('is_guest', False) or msg.get('direction') == 'in')

                    # Parse Smoobu timestamp (convert to UTC)
                    msg_time = _parse_smoobu_timestamp(
                        msg.get('created_at') or msg.get('createdAt') or msg.get('date')
                    )

                    # Skip messages older than our sync watermark (already imported)
                    if existing_conv and existing_conv.last_synced_message_at and msg_time:
                        if msg_time <= existing_conv.last_synced_message_at:
                            if platform_msg_id and platform_msg_id in conv_known_ids:
                                continue  # Definitely already imported

                    if is_from_guest:
                        proc_result = router.process_incoming_message(
                            platform='smoobu',
                            platform_conversation_id=f"smoobu-{reservation_id}",
                            sender_email=guest_email or None,
                            sender_name=guest_name or None,
                            message_content=msg_content,
                            subject=thread.get('subject') or f"Reservation {reservation_id}",
                            platform_message_id=platform_msg_id,
                            property_id=property_id,
                            auto_respond=False,
                            sent_at=msg_time,
                            skip_push=True  # Push handled after full thread sync
                        )
                        if proc_result.get('success') and proc_result.get('is_new', True):
                            result['imported'] += 1
                            # Link conversation to Smoobu reservation
                            conv_id = proc_result.get('conversation_id')
                            if conv_id:
                                conv = Conversation.query.get(conv_id)
                                if conv and not conv.smoobu_reservation_id:
                                    conv.smoobu_reservation_id = reservation_id
                                    db.session.commit()
                    else:
                        # Store owner/host messages (type=2, outbox)
                        conv = Conversation.query.filter_by(
                            platform_id=f"smoobu-{reservation_id}"
                        ).first()

                        # Create conversation if it doesn't exist yet
                        # (host may have sent messages before any guest message)
                        if not conv:
                            from ..models import Guest
                            guest = None
                            if guest_email:
                                guest = Guest.query.filter_by(email=guest_email).first()
                            if not guest and guest_name:
                                guest = Guest.query.filter_by(name=guest_name).first()
                            if not guest:
                                guest = Guest(
                                    name=guest_name or f"Guest {reservation_id}",
                                    email=guest_email or None,
                                    smoobu_guest_id=reservation_id
                                )
                                db.session.add(guest)
                                db.session.flush()

                            conv = Conversation(
                                guest_id=guest.id,
                                platform='smoobu',
                                platform_id=f"smoobu-{reservation_id}",
                                subject=thread.get('subject') or f"Reservation {reservation_id}",
                                smoobu_reservation_id=reservation_id,
                                property_id=property_id
                            )
                            db.session.add(conv)
                            db.session.commit()

                        from ..models import Message
                        existing = Message.query.filter_by(
                            conversation_id=conv.id,
                            platform_message_id=platform_msg_id
                        ).first() if platform_msg_id else None

                        # Fallback: detect messages sent from our app without platform_message_id.
                        # Uses normalized content comparison because Smoobu wraps outbox messages
                        # in HTML structure, adding whitespace that differs from what we stored.
                        if not existing and platform_msg_id and conv:
                            from sqlalchemy import and_
                            window = timedelta(hours=2)
                            ref_time = msg_time or datetime.utcnow()
                            normalized = _normalize_content(msg_content)
                            candidates = Message.query.filter(
                                and_(
                                    Message.conversation_id == conv.id,
                                    Message.sender_type.in_(['owner', 'ai']),
                                    Message.platform_message_id.is_(None),
                                    Message.sent_at >= ref_time - window,
                                    Message.sent_at <= ref_time + window
                                )
                            ).all()
                            for candidate in candidates:
                                if _normalize_content(candidate.content or '') == normalized:
                                    existing = candidate
                                    break
                            if existing:
                                existing.platform_message_id = platform_msg_id
                                db.session.commit()

                        if not existing:
                            owner_msg = Message(
                                conversation_id=conv.id,
                                sender_type='owner',
                                content=msg_content,
                                platform_message_id=platform_msg_id,
                                sent_at=msg_time or datetime.utcnow(),
                                is_processed=True
                            )
                            db.session.add(owner_msg)
                            # Update conversation timestamp for inbox ordering
                            if not conv.updated_at or owner_msg.sent_at > conv.updated_at:
                                conv.updated_at = owner_msg.sent_at
                            # Update sync watermark
                            if not conv.last_synced_message_at or owner_msg.sent_at > conv.last_synced_message_at:
                                conv.last_synced_message_at = owner_msg.sent_at
                            db.session.commit()
                            result['imported'] += 1

                # Enrich guest data and stay dates from reservation
                final_conv = Conversation.query.filter_by(
                    platform_id=f"smoobu-{reservation_id}"
                ).first()
                if final_conv:
                    # Backfill check_in/check_out if missing
                    if not final_conv.check_in or not final_conv.check_out:
                        if not res_detail:
                            res_detail = self.get_reservation(reservation_id)
                        if res_detail:
                            ci = _parse_smoobu_date(
                                res_detail.get('arrival') or res_detail.get('check-in'))
                            co = _parse_smoobu_date(
                                res_detail.get('departure') or res_detail.get('check-out'))
                            if ci and not final_conv.check_in:
                                final_conv.check_in = ci
                            if co and not final_conv.check_out:
                                final_conv.check_out = co
                            db.session.commit()

                    # Enrich guest details (only for new conversations)
                    if not existing_conv and final_conv.guest:
                        if not res_detail:
                            res_detail = self.get_reservation(reservation_id)
                        if res_detail:
                            self._enrich_guest_from_reservation(
                                final_conv.guest, res_detail, reservation_id)

                # Send push notification only if last message is from guest (unanswered)
                conv_for_push = Conversation.query.filter_by(
                    platform_id=f"smoobu-{reservation_id}"
                ).first()
                if conv_for_push and not conv_for_push.auto_respond:
                    last_msg = Message.query.filter_by(
                        conversation_id=conv_for_push.id
                    ).order_by(Message.sent_at.desc()).first()
                    if last_msg and last_msg.sender_type == 'guest':
                        try:
                            from .push_service import get_push_service
                            push = get_push_service()
                            if push:
                                guest_name = (conv_for_push.guest.name or
                                              conv_for_push.guest.email or 'Guest') if conv_for_push.guest else 'Guest'
                                push.notify_new_guest_message(
                                    conv_for_push, last_msg.content, guest_name
                                )
                        except Exception as e:
                            logger.warning(f"Push notification failed for conv {conv_for_push.id}: {e}")

            except Exception as e:
                error_msg = f"Error processing thread {thread.get('reservation_id', '?')}: {e}"
                logger.error(error_msg)
                result['errors'].append(error_msg)

        result['success'] = True
        SmoobuService._last_full_sync = time.time()
        logger.info(f"Smoobu sync complete: {result['imported']} new messages imported")
        return result

    def sync_conversation_messages(self, reservation_id: str) -> Dict[str, Any]:
        """Sync messages for a single reservation — lightweight alternative to full sync.

        Optimized: pre-loads known message IDs in one query, compares counts
        with Smoobu to skip the API call when nothing is new.

        Args:
            reservation_id: Smoobu reservation/booking ID.

        Returns:
            Dict with imported count and errors.
        """
        from .message_router import get_message_router
        from ..models import db, Conversation, Message, Guest, Property

        result = {'success': False, 'imported': 0, 'errors': []}

        conv = Conversation.query.filter_by(
            platform_id=f"smoobu-{reservation_id}"
        ).first()

        # Pre-load all known platform_message_ids in one query
        known_ids: set = set()
        if conv:
            rows = db.session.query(Message.platform_message_id).filter(
                Message.conversation_id == conv.id,
                Message.platform_message_id.isnot(None)
            ).all()
            known_ids = {r[0] for r in rows}

        # Fetch ALL message pages from Smoobu
        # (Smoobu returns 25/page oldest-first; new messages are on the last page)
        msg_data = self.get_all_reservation_messages(reservation_id)
        if not msg_data:
            result['errors'].append(f'Failed to fetch messages for reservation {reservation_id}')
            return result

        messages = []
        if isinstance(msg_data, list):
            messages = msg_data
        elif isinstance(msg_data, dict):
            messages = msg_data.get('messages') or msg_data.get('data') or []

        # Quick check: if total matches known count, nothing new
        total_from_api = msg_data.get('total_items', len(messages)) if isinstance(msg_data, dict) else len(messages)
        if conv and total_from_api <= len(known_ids):
            result['success'] = True
            return result

        router = get_message_router()

        for msg in messages:
            try:
                msg_id = str(msg.get('id', ''))
                msg_content = (msg.get('message') or msg.get('htmlMessage')
                               or msg.get('message_body') or msg.get('body') or '')
                if not msg_content or not msg_content.strip():
                    continue
                msg_content = msg_content.strip()

                platform_msg_id = f"smoobu-{reservation_id}-{msg_id}" if msg_id else None

                # Skip if already imported (in-memory check, no DB query)
                if platform_msg_id and platform_msg_id in known_ids:
                    continue

                # Parse timestamp (convert to UTC)
                msg_time = _parse_smoobu_timestamp(
                    msg.get('created_at') or msg.get('createdAt') or msg.get('date')
                )

                # Skip messages older than sync watermark
                if conv and conv.last_synced_message_at and msg_time:
                    if msg_time <= conv.last_synced_message_at:
                        if platform_msg_id and platform_msg_id in known_ids:
                            continue

                msg_type = msg.get('type')
                is_from_guest = (msg_type == 1 or msg_type == 'inbox')

                if is_from_guest and router:
                    guest_name = ''
                    guest_email = ''
                    if conv and conv.guest:
                        guest_name = conv.guest.name or ''
                        guest_email = conv.guest.email or ''

                    proc_result = router.process_incoming_message(
                        platform='smoobu',
                        platform_conversation_id=f"smoobu-{reservation_id}",
                        sender_email=guest_email or None,
                        sender_name=guest_name or None,
                        message_content=msg_content,
                        subject=f"Reservation {reservation_id}",
                        platform_message_id=platform_msg_id,
                        auto_respond=False,
                        sent_at=msg_time,
                        skip_push=True  # Push handled after full thread sync
                    )
                    if proc_result.get('success'):
                        result['imported'] += 1
                        if platform_msg_id:
                            known_ids.add(platform_msg_id)
                        if not conv:
                            conv = Conversation.query.filter_by(
                                platform_id=f"smoobu-{reservation_id}"
                            ).first()
                else:
                    # Owner/host message
                    if not conv:
                        continue

                    # Check for existing by platform_message_id
                    existing = Message.query.filter_by(
                        conversation_id=conv.id,
                        platform_message_id=platform_msg_id
                    ).first() if platform_msg_id else None

                    # Fallback: detect messages sent from our app without platform_message_id.
                    # Uses normalized content comparison (Smoobu wraps outbox in HTML whitespace).
                    if not existing and platform_msg_id:
                        from sqlalchemy import and_
                        window = timedelta(hours=2)
                        ref_time = msg_time or datetime.utcnow()
                        normalized = _normalize_content(msg_content)
                        candidates = Message.query.filter(
                            and_(
                                Message.conversation_id == conv.id,
                                Message.sender_type.in_(['owner', 'ai']),
                                Message.platform_message_id.is_(None),
                                Message.sent_at >= ref_time - window,
                                Message.sent_at <= ref_time + window
                            )
                        ).all()
                        for candidate in candidates:
                            if _normalize_content(candidate.content or '') == normalized:
                                existing = candidate
                                break
                        if existing:
                            existing.platform_message_id = platform_msg_id
                            db.session.commit()

                    if not existing:
                        owner_msg = Message(
                            conversation_id=conv.id,
                            sender_type='owner',
                            content=msg_content,
                            platform_message_id=platform_msg_id,
                            sent_at=msg_time or datetime.utcnow(),
                            is_processed=True
                        )
                        db.session.add(owner_msg)
                        # Update conversation timestamp for inbox ordering
                        if not conv.updated_at or owner_msg.sent_at > conv.updated_at:
                            conv.updated_at = owner_msg.sent_at
                        # Update sync watermark
                        if not conv.last_synced_message_at or owner_msg.sent_at > conv.last_synced_message_at:
                            conv.last_synced_message_at = owner_msg.sent_at
                        db.session.commit()
                        result['imported'] += 1

                    if platform_msg_id:
                        known_ids.add(platform_msg_id)

            except Exception as e:
                logger.error(f"Error syncing message for reservation {reservation_id}: {e}")
                result['errors'].append(str(e))

        # Send push notification only if last message is from guest (unanswered)
        if conv and not conv.auto_respond:
            last_msg = Message.query.filter_by(
                conversation_id=conv.id
            ).order_by(Message.sent_at.desc()).first()
            if last_msg and last_msg.sender_type == 'guest':
                try:
                    from .push_service import get_push_service
                    push = get_push_service()
                    if push:
                        guest_name = (conv.guest.name or conv.guest.email or 'Guest') if conv.guest else 'Guest'
                        push.notify_new_guest_message(conv, last_msg.content, guest_name)
                except Exception as e:
                    logger.warning(f"Push notification failed for conv {conv.id}: {e}")

        result['success'] = True
        return result

    def _extract_property_fields(self, apt: Dict) -> Dict[str, Any]:
        """Extract Property model fields from a Smoobu apartment API response.

        Handles varying API response structures flexibly.
        """
        fields = {}

        # Address: try nested location object, then flat fields
        location = apt.get('location') or {}
        street = location.get('street') or apt.get('street', '')
        city = location.get('city') or apt.get('city', '')
        zip_code = location.get('zip') or apt.get('zip', '')
        country = location.get('country') or apt.get('country', '')
        address_parts = [p for p in [street, zip_code, city, country] if p]
        if address_parts:
            fields['address'] = ', '.join(address_parts)

        # Rooms: try nested rooms object, then flat fields
        rooms = apt.get('rooms') or {}
        bedrooms = rooms.get('bedrooms') or apt.get('bedrooms') or apt.get('numberOfBedrooms')
        bathrooms = rooms.get('bathrooms') or apt.get('bathrooms') or apt.get('numberOfBathrooms')
        max_guests = (rooms.get('maxOccupancy') or apt.get('maxOccupancy')
                      or apt.get('maxGuests') or apt.get('max_guests')
                      or apt.get('personCount'))

        if bedrooms is not None:
            try:
                fields['bedrooms'] = int(bedrooms)
            except (ValueError, TypeError):
                pass
        if bathrooms is not None:
            try:
                fields['bathrooms'] = float(bathrooms)
            except (ValueError, TypeError):
                pass
        if max_guests is not None:
            try:
                fields['max_guests'] = int(max_guests)
            except (ValueError, TypeError):
                pass

        # Description
        description = apt.get('description') or apt.get('internationalDescription')
        if isinstance(description, dict):
            description = description.get('en') or description.get('de') or next(iter(description.values()), '')
        if description:
            fields['description'] = str(description)[:2000]

        return fields

    def _enrich_guest_from_reservation(self, guest, res_detail: Dict, reservation_id: str):
        """Extract additional guest data from Smoobu reservation details.

        Stores phone on Guest record. Stores arrival, departure, adults,
        children, language, channel, and guest notes as GuestDetail entries
        so the AI memory system picks them up automatically.

        Uses upsert logic: updates existing details rather than creating
        duplicates, so re-calling is safe (but avoided by the caller).
        """
        from ..models import db, GuestDetail

        changed = False

        # Phone → Guest.phone (permanent, set once)
        phone = (res_detail.get('phone') or res_detail.get('phone-number')
                 or res_detail.get('guestPhone') or '').strip()
        if phone and not guest.phone:
            guest.phone = phone
            changed = True

        # Collect detail entries to upsert
        details = []

        arrival = res_detail.get('arrival') or res_detail.get('check-in') or ''
        if arrival:
            details.append(('reservation', 'check_in', str(arrival)))

        departure = res_detail.get('departure') or res_detail.get('check-out') or ''
        if departure:
            details.append(('reservation', 'check_out', str(departure)))

        adults = res_detail.get('adults')
        if adults is not None:
            details.append(('reservation', 'adults', str(adults)))

        children = res_detail.get('children')
        if children is not None:
            try:
                if int(children) > 0:
                    details.append(('reservation', 'children', str(children)))
            except (ValueError, TypeError):
                pass

        notice = (res_detail.get('notice') or res_detail.get('note')
                  or res_detail.get('guestNote') or '').strip()
        if notice:
            details.append(('special_request', 'guest_note', notice[:500]))

        language = res_detail.get('language') or ''
        if language:
            details.append(('preference', 'language', str(language)))

        channel = res_detail.get('channel') or {}
        channel_name = (channel.get('name') if isinstance(channel, dict)
                        else str(channel) if channel else '')
        if channel_name:
            details.append(('reservation', 'booking_channel', channel_name))

        # Upsert: update existing or create new
        for detail_type, detail_key, detail_value in details:
            existing = GuestDetail.query.filter_by(
                guest_id=guest.id,
                detail_type=detail_type,
                detail_key=detail_key
            ).first()
            if existing:
                if existing.detail_value != detail_value:
                    existing.detail_value = detail_value
                    changed = True
            else:
                db.session.add(GuestDetail(
                    guest_id=guest.id,
                    detail_type=detail_type,
                    detail_key=detail_key,
                    detail_value=detail_value,
                    confidence=1.0
                ))
                changed = True

        if changed:
            db.session.commit()
            logger.info(f"Enriched guest {guest.id} ({guest.name}) from reservation {reservation_id}")

    def sync_properties(self) -> Dict[str, Any]:
        """Import Smoobu apartments as Property records with full details.

        Fetches each apartment's detail endpoint to get rooms, max guests, etc.

        Returns:
            Dict with imported/updated counts.
        """
        from ..models import db, Property

        result = {'success': False, 'imported': 0, 'updated': 0, 'errors': []}

        apt_data = self.get_apartments()
        if not apt_data:
            result['errors'].append('Failed to fetch apartments from Smoobu')
            return result

        apartments = apt_data.get('apartments') or apt_data.get('data') or []
        if isinstance(apt_data, list):
            apartments = apt_data

        for apt in apartments:
            try:
                apt_id = str(apt.get('id', ''))
                if not apt_id:
                    continue

                name = apt.get('name') or f"Apartment {apt_id}"

                # Fetch detailed apartment data for rooms/guests info
                detail = self.get_apartment(apt_id)
                if detail:
                    fields = self._extract_property_fields(detail)
                else:
                    fields = self._extract_property_fields(apt)

                # Check if property already exists
                existing = Property.query.filter_by(smoobu_apartment_id=apt_id).first()
                if existing:
                    # Update all fields
                    changed = False
                    if existing.name != name:
                        existing.name = name
                        changed = True
                    for key, value in fields.items():
                        if getattr(existing, key, None) != value:
                            setattr(existing, key, value)
                            changed = True
                    if changed:
                        existing.updated_at = datetime.utcnow()
                        db.session.commit()
                    result['updated'] += 1
                else:
                    # Create new property with all available fields
                    prop = Property(
                        name=name,
                        smoobu_apartment_id=apt_id,
                        **fields
                    )
                    db.session.add(prop)
                    db.session.commit()
                    result['imported'] += 1

            except Exception as e:
                error_msg = f"Error syncing apartment {apt.get('id', '?')}: {e}"
                logger.error(error_msg)
                result['errors'].append(error_msg)

        result['success'] = True
        logger.info(f"Smoobu property sync: {result['imported']} imported, {result['updated']} updated")
        return result


# Global instance
_smoobu_service: Optional[SmoobuService] = None


def init_smoobu_service(app) -> SmoobuService:
    """Initialize the Smoobu service with Flask app configuration."""
    global _smoobu_service
    _smoobu_service = SmoobuService(
        api_url=app.config.get('SMOOBU_API_URL', 'https://login.smoobu.com/api'),
        api_key=app.config.get('SMOOBU_API_KEY', '')
    )
    logger.info("Smoobu Service initialized")
    return _smoobu_service


def get_smoobu_service() -> Optional[SmoobuService]:
    """Get the current Smoobu service instance."""
    return _smoobu_service
