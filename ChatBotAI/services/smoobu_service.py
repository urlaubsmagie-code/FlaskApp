"""
Smoobu Service for ChatBotAI
Handles all interactions with the Smoobu messaging and reservation API.
"""

import base64
import hashlib
import hmac
import json
import logging
import re
import uuid
from urllib.parse import urlparse
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional, Dict, List, Any

import requests
from sqlalchemy import or_ as db_or
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


# Subjects of our Smoobu automated messages (Buchungsbestätigung, Dein Check-in,
# WhatsApp Kanal, Checkout, Bewertung, …). These are scheduled host→guest sends,
# NOT replies to the guest, so they must not mark a conversation read — otherwise
# an unanswered guest message gets hidden from the unread list (the
# missing_message Problem-Report bug). Matched by normalized subject prefix so all
# "Buchungsbestätigung mit X" variants are covered without listing each.
# ponytail: hardcoded — these are stable core templates. If the list starts to
# churn, move it to an editable AISettings value.
AUTOMATED_SUBJECT_PREFIXES = (
    'buchungsbestätigung',   # all "Buchungsbestätigung …" variants
    'whatsapp kanal',        # WhatsApp Kanal (+ … Booking)
    'dein check-in',
    'guten morgen',
    'checkout',
    'bitte um bewertung',
    'bewertung booking',
    'verlängerung',          # Verlängerung - Aktion / Verlängerung Rechnung
    'rechnung ferienwohnung',
)


def _is_automated_smoobu_message(msg: dict) -> bool:
    """True if a Smoobu message is one of our configured automated templates,
    identified by its subject line. Manual chat replies have an empty subject."""
    subject = (msg.get('subject') or '').strip().casefold()
    return bool(subject) and any(
        subject.startswith(p) for p in AUTOMATED_SUBJECT_PREFIXES)


def _parse_smoobu_timestamp(raw) -> 'datetime | None':
    """Parse a Smoobu timestamp string to a naive UTC datetime.

    Smoobu returns timestamps in Europe/Berlin local time without timezone info.
    We assume Europe/Berlin, convert to UTC, then strip tzinfo so all stored
    datetimes are consistently naive UTC — matching ``datetime.utcnow()`` used
    elsewhere.
    """
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
        if dt.tzinfo is not None:
            # Explicit timezone provided — convert to UTC
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            # No timezone — Smoobu gives Europe/Berlin local time
            dt = dt.replace(tzinfo=ZoneInfo('Europe/Berlin'))
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return None


def _normalize_content(text: str) -> str:
    """Normalize message content for dedup comparison.

    Smoobu wraps outbox messages in an HTML document structure.  Strip all HTML
    tags first, then collapse whitespace and lower-case for robust comparison.
    """
    # Strip HTML tags (Smoobu wraps outbox messages in <p>, <br>, <html> etc.)
    text = re.sub(r'<[^>]+>', ' ', text)
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


def _res_guest_counts(res):
    """Extract (adults, children) ints from a Smoobu reservation dict, or (None, None)."""
    if not isinstance(res, dict):
        return None, None

    def _int(v):
        try:
            return int(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    return _int(res.get('adults')), _int(res.get('children'))


class SmoobuService:
    """Service for interacting with the Smoobu API"""

    def __init__(self, api_url: str = 'https://login.smoobu.com/api', api_key: str = '',
                 slot: int = 1):
        self.api_url = api_url.rstrip('/')
        self._api_key = api_key
        # Which account slot this instance serves (1 = the original account).
        self.slot = slot
        # In-memory cache for the DB-stored key. Loaded on first access,
        # invalidated by reload_api_key() when the user updates the setting.
        self._cached_api_key: Optional[str] = None
        self._api_key_cache_loaded: bool = False
        self._cached_account_id: Optional[str] = None
        self._account_id_cache_loaded: bool = False
        self._cached_secret: Optional[str] = None
        self._secret_cache_loaded: bool = False
        self._cached_sync_from: Optional[datetime] = None
        self._sync_from_cache_loaded: bool = False

    @property
    def api_key(self) -> str:
        """Get API key — DB-stored value preferred, cached in memory after first read."""
        if not self._api_key_cache_loaded:
            try:
                from ..models import AISettings
                db_key = AISettings.get(settings_key(self.slot))
                self._cached_api_key = db_key or None
            except Exception:
                self._cached_api_key = None
            self._api_key_cache_loaded = True

        return self._cached_api_key or self._api_key

    @property
    def api_secret(self) -> Optional[str]:
        """HMAC secret for this key, if the key uses Smoobu's new token auth.

        Empty for legacy keys, which authenticate with the single Api-Key header.
        """
        if not self._secret_cache_loaded:
            try:
                from ..models import AISettings
                self._cached_secret = AISettings.get(secret_settings_key(self.slot)) or None
            except Exception:
                self._cached_secret = None
            self._secret_cache_loaded = True
        return self._cached_secret

    @property
    def sync_from(self) -> Optional[datetime]:
        """Only import messages newer than this (None = import everything)."""
        if not self._sync_from_cache_loaded:
            self._cached_sync_from = None
            try:
                from ..models import AISettings
                raw = AISettings.get(sync_from_settings_key(self.slot))
                if raw:
                    self._cached_sync_from = datetime.fromisoformat(raw.replace('Z', ''))
            except Exception:
                logger.warning("Bad smoobu sync_from value for slot %s", self.slot)
            self._sync_from_cache_loaded = True
        return self._cached_sync_from

    def _too_old(self, when) -> bool:
        """True when a message/thread predates this account's cutoff."""
        cutoff = self.sync_from
        return bool(cutoff and when and when < cutoff)

    @property
    def account_id(self) -> Optional[str]:
        """Smoobu account id for this key — the same number webhooks send as 'user'.

        Stored at connect time (see fetch_account_id); read-through cached here.
        """
        if not self._account_id_cache_loaded:
            try:
                from ..models import AISettings
                self._cached_account_id = AISettings.get(account_settings_key(self.slot)) or None
            except Exception:
                self._cached_account_id = None
            self._account_id_cache_loaded = True
        return self._cached_account_id

    def fetch_account_id(self) -> Optional[str]:
        """Ask Smoobu who this key belongs to (GET /me) and persist the id."""
        resp = self._request('GET', '/me')
        if resp is None or resp.status_code != 200:
            return None
        try:
            account_id = str((resp.json() or {}).get('id') or '')
        except ValueError:
            return None
        if not account_id:
            return None
        try:
            from ..models import AISettings
            AISettings.set(account_settings_key(self.slot), account_id,
                           description=f'Smoobu account id (slot {self.slot})')
        except Exception:
            logger.exception("Failed to store Smoobu account id for slot %s", self.slot)
        self._cached_account_id = account_id
        self._account_id_cache_loaded = True
        return account_id

    def ensure_account_id(self) -> Optional[str]:
        """Resolve and store this key's account id if we don't have it yet.

        Self-heal for the account connected before multi-account existed: its key
        was saved without ever calling /me. Called at the start of each daemon
        cycle (never on a request path). For the primary account it also stamps
        the rows that predate the tag, so they stop relying on the NULL fallback.
        """
        if self.account_id or not self.is_configured():
            return self.account_id
        account_id = self.fetch_account_id()
        if account_id and self.slot == 1:
            self._backfill_untagged_rows(account_id)
        return account_id

    @staticmethod
    def _backfill_untagged_rows(account_id: str) -> None:
        from ..models import db, Conversation, Property
        try:
            Conversation.query.filter(
                Conversation.smoobu_reservation_id.isnot(None),
                Conversation.smoobu_account_id.is_(None),
            ).update({'smoobu_account_id': account_id}, synchronize_session=False)
            Property.query.filter(
                Property.smoobu_apartment_id.isnot(None),
                Property.smoobu_account_id.is_(None),
            ).update({'smoobu_account_id': account_id}, synchronize_session=False)
            db.session.commit()
            logger.info("Tagged pre-existing Smoobu rows with account %s", account_id)
        except Exception:
            db.session.rollback()
            logger.exception("Failed to backfill Smoobu account tags")

    def reload_api_key(self) -> None:
        """Invalidate the cached API key so the next access re-reads from the DB.

        Called by routes that update the smoobu_api_key setting (connect/disconnect).
        """
        self._cached_api_key = None
        self._api_key_cache_loaded = False
        self._cached_account_id = None
        self._account_id_cache_loaded = False
        self._cached_secret = None
        self._secret_cache_loaded = False
        self._cached_sync_from = None
        self._sync_from_cache_loaded = False

    # Track rate-limit state across requests
    _rate_limit_remaining: Optional[int] = None
    _rate_limit_retry_after: Optional[float] = None

    @staticmethod
    def _hmac_headers(method: str, url: str, body: bytes, key: str, secret: str) -> Dict[str, str]:
        """Smoobu HMAC auth headers.

        Canonical string, newline separated:
            METHOD \n PATH \n QUERY \n TIMESTAMP \n NONCE \n SHA256(body) \n API_KEY
        signed with HMAC-SHA256 (the secret is used as the literal string Smoobu
        showed, NOT base64-decoded) and Base64 encoded. PATH includes the /api
        prefix; QUERY is the alphabetically sorted query string.
        """
        parsed = urlparse(url)
        query = '&'.join(sorted(parsed.query.split('&'))) if parsed.query else ''
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        nonce = str(uuid.uuid4())
        canonical = '\n'.join([
            method.upper(), parsed.path, query, timestamp, nonce,
            hashlib.sha256(body).hexdigest(), key,
        ])
        signature = base64.b64encode(
            hmac.new(secret.encode('utf-8'), canonical.encode('utf-8'), hashlib.sha256).digest()
        ).decode('ascii')
        return {'X-API-Key': key, 'X-Timestamp': timestamp,
                'X-Nonce': nonce, 'X-Signature': signature}

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
        headers.setdefault('Content-Type', 'application/json')

        # Body is serialized here (not by requests) so the signature is computed
        # over the exact bytes that go on the wire.
        body_json = kwargs.pop('json', None)
        if body_json is not None:
            kwargs['data'] = json.dumps(body_json)
        body_bytes = (kwargs.get('data') or '')
        if isinstance(body_bytes, str):
            body_bytes = body_bytes.encode('utf-8')

        secret = self.api_secret
        if secret:
            headers.update(self._hmac_headers(method, url, body_bytes, key, secret))
        else:
            # Legacy single-header auth. Smoobu sunsets it on 2026-09-25.
            headers['Api-Key'] = key

        timeout = kwargs.pop('timeout', 30)
        # Non-idempotent calls (message send) opt out of the 429 retry: re-POSTing
        # a send that Smoobu already delivered would double-message the guest.
        allow_retry = kwargs.pop('allow_retry', True)
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
                # X-RateLimit-Retry-After is sent on EVERY response — it is the
                # window reset time (~60s out), not a "you are blocked" signal.
                # Only a 429 (or an exhausted quota) may make us wait, otherwise
                # every single call would sleep up to a minute first.
                retry_after = response.headers.get('X-RateLimit-Retry-After')
                if retry_after and (response.status_code == 429
                                    or (remaining is not None and int(remaining) <= 0)):
                    self._rate_limit_retry_after = float(retry_after)
                else:
                    self._rate_limit_retry_after = None

                if remaining is not None and int(remaining) < 50:
                    logger.warning(f"Smoobu rate limit low: {remaining} requests remaining")

                # Record API call for debug dashboard
                self._track_api_call(method, endpoint, response.status_code, duration_ms)

                # Handle 429 Too Many Requests
                if response.status_code == 429:
                    if allow_retry and attempt < max_retries:
                        wait = 10  # default backoff
                        if retry_after:
                            try:
                                val = float(retry_after)
                                now = time.time()
                                # Heuristic: if the value looks like a unix
                                # timestamp (>= 1e9 ~ year 2001) treat as absolute,
                                # otherwise treat as relative seconds. The previous
                                # code assumed absolute always — a relative "60" would
                                # become 60 - 1.7e9 = huge negative, clamped to 1s,
                                # producing a retry storm.
                                if val >= 1_000_000_000:
                                    wait = max(val - now, 1)
                                else:
                                    wait = max(val, 1)
                            except (TypeError, ValueError):
                                pass
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
            'slot': self.slot,
            'account_id': self.account_id,
            'auth': 'hmac' if self.api_secret else 'legacy',
            'configured': bool(key),
            'authenticated': self.is_authenticated() if key else False,
            'api_key_masked': f"...{key[-4:]}" if key and len(key) > 4 else ''
        }

    def disconnect(self):
        """Clear stored API key."""
        try:
            from ..models import AISettings
            AISettings.set(settings_key(self.slot), '',
                           description=f'Smoobu API key (slot {self.slot})')
            AISettings.set(secret_settings_key(self.slot), '',
                           description=f'Smoobu HMAC secret (slot {self.slot})')
            AISettings.set(account_settings_key(self.slot), '',
                           description=f'Smoobu account id (slot {self.slot})')
            AISettings.set(sync_from_settings_key(self.slot), '',
                           description=f'Smoobu sync cutoff (slot {self.slot})')
            self.reload_api_key()
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
        from .delivery_audit import record_delivery_event
        import hashlib
        import uuid
        attempt_id = uuid.uuid4().hex
        record_delivery_event(attempt_id, 'started', platform='smoobu',
                              reservation_id=str(reservation_id), account_slot=self.slot,
                              content_sha256=hashlib.sha256(message_text.encode('utf-8')).hexdigest(),
                              content_length=len(message_text))
        status = None
        try:
            resp = self._request('POST',
                                 f'/reservations/{reservation_id}/messages/send-message-to-guest',
                                 json=body, allow_retry=False)
            status = resp.status_code if resp is not None else None
            if status in (200, 201):
                result = resp.json()
                record_delivery_event(attempt_id, 'finished', outcome='accepted', http_status=status)
                return result
            # No response / a server failure cannot prove the guest did not
            # receive it. Keep that ambiguity visible rather than auto-retrying.
            outcome = 'rejected' if status is not None and 400 <= status < 500 else 'unknown'
            record_delivery_event(attempt_id, 'finished', outcome=outcome, http_status=status)
            return None
        except Exception as exc:
            record_delivery_event(attempt_id, 'finished', outcome='unknown', http_status=status,
                                  error_type=type(exc).__name__)
            raise

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
        import time as _t
        _t0 = _t.monotonic()
        resp = self._request('GET', f'/reservations/{reservation_id}')
        _el = _t.monotonic() - _t0
        # Diagnostic: this runs synchronously before every AI suggestion. If it's
        # slow (Smoobu cold/network), it adds straight onto the felt reply time.
        if _el > 2:
            logger.warning(f"[SMOOBU SLOW] get_reservation({reservation_id}) took {_el:.1f}s")
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
    _FULL_SYNC_COOLDOWN = 30  # seconds — ignore duplicate full-sync requests within this window

    # Per-reservation throttle for sync_conversation_messages. Lets multiple
    # users sync DIFFERENT conversations concurrently without blocking each other,
    # while still suppressing duplicate clicks on the SAME conversation.
    _last_sync_by_reservation: Dict[str, float] = {}
    _PER_RESERVATION_COOLDOWN = 10  # seconds

    # Discovery window: how many days back to walk /reservations each cycle.
    # Bookings outside this window still get caught when first created (their
    # created_at will be recent), or when their reservation is updated.
    DISCOVERY_DAYS_BACK = 90

    def _heal_conv_fields(self, conv, thread):
        """Fill check_in/out + property_id from reservation-list data we already
        hold (no extra Smoobu API call). Fixes bare 'Reservation N' inbox labels,
        and runs on the fast-path skip where we never fetch messages."""
        from ..models import db
        changed = False
        if not conv.check_in:
            ci = _parse_smoobu_date(thread.get('arrival'))
            if ci:
                conv.check_in = ci
                changed = True
        if not conv.check_out:
            co = _parse_smoobu_date(thread.get('departure'))
            if co:
                conv.check_out = co
                changed = True
        if conv.property_id is None:
            pid = self._resolve_property_id(thread)
            if pid:
                conv.property_id = pid
                changed = True
        if changed:
            db.session.commit()

    def sync_messages(self, force: bool = False,
                      days_back: Optional[int] = None) -> Dict[str, Any]:
        """Discover Smoobu reservations in the last N days and sync their messages.

        Replaces the previous /threads-based discovery which only ever saw the
        most recent 25 threads per cycle (Smoobu caps page_size at 25 and there
        are ~14k total threads). Walking /reservations?from=<today-N> paginated
        guarantees we see every booking with or without messages, including
        owner-only conversations that generate no webhook.

        Args:
            force: If True, bypass the 30s global cooldown. Set by manual button.
            days_back: Override DISCOVERY_DAYS_BACK for a single call (e.g., wider
                window for a manual catch-up). Defaults to 90.

        Returns:
            Dict with imported count and errors.
        """
        import time
        from datetime import datetime, timedelta
        from .message_router import get_message_router
        from ..models import db, Conversation, Property

        result = {'success': False, 'imported': 0, 'errors': []}

        now = time.time()
        if not force and self._last_full_sync and (now - self._last_full_sync) < self._FULL_SYNC_COOLDOWN:
            logger.debug("Smoobu full sync skipped — cooldown active")
            result['success'] = True
            return result

        # Discovery via /reservations (paginated). Smoobu returns 50/page here
        # (vs 25 on /threads) and lists every booking — including ones with
        # zero messages yet, or owner-only messaging.
        window_days = days_back if days_back is not None else self.DISCOVERY_DAYS_BACK
        from_date = (datetime.utcnow() - timedelta(days=window_days)).strftime('%Y-%m-%d')

        reservations: List[Dict[str, Any]] = []
        page = 1
        page_cap = 500  # safety: well above any realistic window
        while page <= page_cap:
            data = self.get_reservations(page=page, from_date=from_date)
            if not data:
                if page == 1:
                    result['errors'].append('Failed to fetch reservations from Smoobu')
                    return result
                break
            batch: List[Dict[str, Any]] = []
            page_count = None
            if isinstance(data, list):
                batch = data
            elif isinstance(data, dict):
                batch = (data.get('bookings') or data.get('reservations')
                         or data.get('data') or [])
                page_count = data.get('page_count')
            if not batch:
                break
            reservations.extend(batch)
            # Authoritative stop: page_count from API. Smoobu returns 25/page
            # for /reservations, so a length check would terminate prematurely.
            if page_count and page >= page_count:
                break
            if not page_count and len(batch) == 0:
                break
            page += 1

        logger.info(
            f"Smoobu sync: {len(reservations)} reservation(s) found in last {window_days} days "
            f"(walked {page} page(s))"
        )

        # Adapt reservation rows into the thread-shaped dicts the per-thread
        # processing loop below expects. Keeps the well-tested message handling
        # path unchanged; only discovery is new.
        threads: List[Dict[str, Any]] = []
        for res in reservations:
            res_id = res.get('id')
            if not res_id:
                continue
            firstname = res.get('first-name') or res.get('firstname') or ''
            lastname = res.get('last-name') or res.get('lastname') or ''
            guest_name = f"{firstname} {lastname}".strip() or (res.get('guest-name') or '')
            apt = res.get('apartment')
            if not isinstance(apt, dict):
                apt = {'id': res.get('apartment-id') or res.get('apartmentId')}
            threads.append({
                'booking': {
                    'id': res_id,
                    'guest_name': guest_name,
                    'email': res.get('email') or '',
                },
                'guest_name': guest_name,
                'email': res.get('email') or '',
                'apartment': apt,
                'subject': f"Reservation {res_id}",
                'reservation_id': str(res_id),
                # Carry guest counts from the reservation row so the AI suggest path
                # can read them locally (no per-suggest live Smoobu call).
                'adults': res.get('adults'),
                'children': res.get('children'),
                # modifiedAt drives the fast-path skip; arrival/departure let us
                # heal check_in/out without a per-reservation get_reservation call.
                'modified_at': res.get('modifiedAt') or res.get('modified-at'),
                'arrival': res.get('arrival') or res.get('check-in'),
                'departure': res.get('departure') or res.get('check-out'),
            })

        router = get_message_router()
        if not router:
            result['errors'].append('MessageRouter not available')
            return result

        logger.info(f"Smoobu found {len(threads)} threads/reservations to process")

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
        # Newest stored message time per conversation — the watermark the
        # modifiedAt fast-path compares against to skip unchanged reservations.
        last_msg_by_conv: Dict[int, Any] = {}
        if all_smoobu_convs:
            from sqlalchemy import func as _func
            for cid, last_at in db.session.query(
                    MsgModel.conversation_id, _func.max(MsgModel.sent_at)).filter(
                    MsgModel.conversation_id.in_(conv_ids),
                    MsgModel.sent_at.isnot(None)).group_by(
                    MsgModel.conversation_id).all():
                last_msg_by_conv[cid] = last_at
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

                existing_conv = conv_by_platform_id.get(f"smoobu-{reservation_id}")

                # Unknown reservation older than the account cutoff: don't fetch
                # its messages every cycle just to throw them all away.
                if not existing_conv and self._too_old(
                        _parse_smoobu_timestamp(thread.get('modified_at'))):
                    continue

                # Fast-path skip: for a conversation we already have, only pay the
                # per-reservation message API call if Smoobu says the reservation
                # changed since our newest stored message. Re-fetching every
                # in-window reservation each cycle blew past Smoobu's rate limit and
                # wedged the sweep for 40+ min. modifiedAt bumps on new guest
                # messages and booking edits; it does NOT bump on owner-sent Smoobu
                # messages, so those rely on the webhook / per-chat manual sync.
                # New reservations (no existing_conv) are never skipped, so
                # owner-only "outbound-first" chats still get created here.
                if existing_conv:
                    modified_at = _parse_smoobu_timestamp(thread.get('modified_at'))
                    watermark = last_msg_by_conv.get(existing_conv.id)
                    if modified_at and watermark and modified_at <= watermark:
                        self._heal_conv_fields(existing_conv, thread)  # cheap, no API
                        continue

                # Fetch page 1 first for quick-check, then all pages if needed
                # (Smoobu returns 25/page oldest-first; new messages land on last page)
                msg_data = self.get_reservation_messages(reservation_id)
                if not msg_data:
                    logger.debug(f"No message data for reservation {reservation_id}")
                    continue

                # Quick check: if we already know all messages, skip this thread
                total_from_api = msg_data.get('total_items', 0) if isinstance(msg_data, dict) else len(msg_data if isinstance(msg_data, list) else [])
                if existing_conv:
                    # One-time heals (check_in/out + "Reservation N" property label)
                    # straight from reservation-list data — no extra get_reservation.
                    self._heal_conv_fields(existing_conv, thread)

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
                property_id = self._resolve_property_id(thread)

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
                                    conv.smoobu_account_id = self.account_id
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
                            from sqlalchemy.exc import IntegrityError
                            from .guest_matching import find_existing_guest

                            guest = find_existing_guest(
                                email=guest_email or None,
                                name=guest_name or None,
                            )
                            if not guest:
                                guest = Guest(
                                    name=guest_name or f"Guest {reservation_id}",
                                    email=guest_email or None,
                                )
                                db.session.add(guest)
                                try:
                                    db.session.flush()
                                except IntegrityError:
                                    # Concurrent webhook beat us to it (email is unique).
                                    db.session.rollback()
                                    guest = find_existing_guest(
                                        email=guest_email or None,
                                        name=guest_name or None,
                                    )
                                    if not guest:
                                        raise

                            conv = Conversation(
                                guest_id=guest.id,
                                platform='smoobu',
                                platform_id=f"smoobu-{reservation_id}",
                                subject=thread.get('subject') or f"Reservation {reservation_id}",
                                smoobu_reservation_id=reservation_id,
                                smoobu_account_id=self.account_id,
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
                            try:
                                db.session.flush()  # get owner_msg.id
                                # updated_at: polling tripwire — bump on any
                                # new owner message so clients refresh.
                                conv.updated_at = datetime.utcnow()
                                # last_message_at: sort key — only advance
                                # when this is genuinely the newest message.
                                if not conv.last_message_at or owner_msg.sent_at > conv.last_message_at:
                                    conv.last_message_at = owner_msg.sent_at
                                # Update sync watermark
                                if not conv.last_synced_message_at or owner_msg.sent_at > conv.last_synced_message_at:
                                    conv.last_synced_message_at = owner_msg.sent_at
                                # Mark as read — someone already replied outside the
                                # app. Skip automated templates: they are not a reply,
                                # so they must not hide an unread guest message.
                                if not _is_automated_smoobu_message(msg):
                                    conv.is_read = True
                                    if not conv.last_read_message_id or owner_msg.id > conv.last_read_message_id:
                                        conv.last_read_message_id = owner_msg.id
                                db.session.commit()
                                result['imported'] += 1
                            except IntegrityError:
                                # Another concurrent sync path inserted the same message first.
                                # The unique index on platform_message_id rejected our insert.
                                db.session.rollback()
                                logger.debug(
                                    "Concurrent insert detected for platform_msg_id=%s, skipping",
                                    platform_msg_id,
                                )

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

                    # Populate guest counts from the reservation row carried on the
                    # thread (already in the list response — no extra API call). Runs
                    # every sync so existing conversations self-heal within one cycle.
                    t_ad, t_ch = _res_guest_counts(thread)
                    counts_changed = False
                    if t_ad is not None and final_conv.adults != t_ad:
                        final_conv.adults = t_ad
                        counts_changed = True
                    if t_ch is not None and final_conv.children != t_ch:
                        final_conv.children = t_ch
                        counts_changed = True
                    if counts_changed:
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

    def sync_recent_threads(self, max_pages: Optional[int] = 5) -> Dict[str, Any]:
        """Sync the most-recent Smoobu message threads (mirrors the Smoobu inbox).

        Smoobu's own inbox is backed by GET /threads, ordered by most-recent
        activity. The /reservations-based daemon sweep can miss freshly-created,
        owner-outbound-only threads (welcome / invoice / marketing sends) because
        their discovery depends on reservation timing. Walking the first N pages
        of /threads each cycle catches exactly those, cheaply: a per-reservation
        message fetch is only paid for a thread whose newest message we have NOT
        stored yet.

        Args:
            max_pages: How many /threads pages to walk (Smoobu returns 25/page).
                Small number (default 5 = 125 newest threads) for the steady-state
                daemon sweep; pass None to walk ALL pages (one-time backfill).

        Returns:
            Dict with threads_seen, synced (threads that needed a fetch) and
            imported (new messages stored).
        """
        from ..models import Conversation, Message

        result = {'success': False, 'threads_seen': 0, 'synced': 0,
                  'imported': 0, 'errors': []}

        PAGE_CAP = 800  # hard safety cap for the "all pages" backfill
        threads: List[Dict[str, Any]] = []
        page = 1
        while True:
            data = self.get_threads(page=page, page_size=100)
            if not data:
                break
            if isinstance(data, dict):
                page_threads = (data.get('threads') or data.get('data')
                                or data.get('entries') or [])
                page_count = data.get('page_count')
            elif isinstance(data, list):
                page_threads = data
                page_count = None
            else:
                break
            if not page_threads:
                break
            threads.extend(page_threads)

            if max_pages is not None and page >= max_pages:
                break
            if page_count and page >= page_count:
                break
            if page >= PAGE_CAP:
                break
            page += 1

        result['threads_seen'] = len(threads)

        for t in threads:
            rid = ''
            try:
                booking = t.get('booking') if isinstance(t.get('booking'), dict) else {}
                rid = str(booking.get('id') or t.get('reservationId')
                          or t.get('reservation_id') or t.get('id') or '')
                if not rid:
                    continue

                # Smoobu nests the newest message under latest_message.id. If we
                # already stored that exact message, the thread is in sync and we
                # skip the per-reservation fetch entirely (DB lookup only).
                latest = t.get('latest_message') or t.get('lastMessage') or {}
                latest_id = str(latest.get('id') or '') if isinstance(latest, dict) else ''

                # Below this account's cutoff the thread is history — skip before
                # paying for the per-reservation fetch.
                if isinstance(latest, dict) and self._too_old(
                        _parse_smoobu_timestamp(latest.get('created_at'))):
                    continue

                conv = Conversation.query.filter_by(
                    platform_id=f"smoobu-{rid}"
                ).first()

                if conv and latest_id:
                    pmid = f"smoobu-{rid}-{latest_id}"
                    already = Message.query.filter_by(
                        conversation_id=conv.id, platform_message_id=pmid
                    ).first()
                    if already:
                        continue  # newest message already stored

                # New thread, or newest message not yet stored -> sync. Reuses the
                # battle-tested per-reservation path (dedup + conversation creation
                # + last_message_at / is_read handling).
                res = self.sync_conversation_messages(rid)
                result['synced'] += 1
                result['imported'] += res.get('imported', 0)
            except Exception as e:
                logger.exception("sync_recent_threads: error on thread rid=%s", rid)
                result['errors'].append(f"thread {rid}: {e}")

        result['success'] = True
        logger.info(
            "Smoobu /threads sweep: %d threads seen, %d synced, %d new message(s) imported",
            result['threads_seen'], result['synced'], result['imported'])
        return result

    def _resolve_property_id(self, thread: Dict[str, Any]) -> Optional[int]:
        """Resolve our Property.id from a thread/reservation's apartment ref.

        Smoobu nests the apartment as ``apartment: {id, name}`` on reservations
        and threads; some payloads use a flat ``apartment_id``/``apartmentId``.
        Returns None when no apartment is present or no Property matches — the
        caller then leaves property_id unset (inbox falls back to subject).
        """
        from ..models import Property
        apt = thread.get('apartment') or {}
        apartment_id = ''
        if isinstance(apt, dict):
            apartment_id = str(apt.get('id', '') or '')
        if not apartment_id:
            apartment_id = str(thread.get('apartment_id')
                               or thread.get('apartmentId') or '')
        if not apartment_id:
            return None
        prop = self._property_for_apartment(apartment_id)
        return prop.id if prop else None

    def _property_for_apartment(self, apartment_id: str):
        """Property for an apartment id **within this account**.

        Apartment ids are only unique per Smoobu account, so an account-blind
        lookup could hand back another account's apartment. Rows synced before
        multi-account existed have a NULL tag and belong to the primary account.
        """
        from ..models import Property
        q = Property.query.filter_by(smoobu_apartment_id=str(apartment_id))
        account_id = self.account_id
        if self.slot == 1:
            q = q.filter(db_or(Property.smoobu_account_id == account_id,
                               Property.smoobu_account_id.is_(None)))
        else:
            q = q.filter(Property.smoobu_account_id == account_id)
        return q.first()

    def sync_conversation_messages(self, reservation_id: str,
                                   force: bool = False) -> Dict[str, Any]:
        """Sync messages for a single reservation — lightweight alternative to full sync.

        Per-reservation cooldown suppresses duplicate clicks on the same
        conversation without blocking parallel syncs of other conversations.

        Args:
            reservation_id: Smoobu reservation/booking ID.
            force: If True, bypass the per-reservation cooldown.

        Returns:
            Dict with imported count and errors.
        """
        import time
        from .message_router import get_message_router
        from ..models import db, Conversation, Message, Guest, Property

        result = {'success': False, 'imported': 0, 'errors': []}

        res_key = str(reservation_id)
        now = time.time()
        last = self._last_sync_by_reservation.get(res_key)
        if not force and last and (now - last) < self._PER_RESERVATION_COOLDOWN:
            logger.debug(f"Per-reservation cooldown active for {res_key}, skipping")
            result['success'] = True
            return result
        self._last_sync_by_reservation[res_key] = now

        conv = Conversation.query.filter_by(
            platform_id=f"smoobu-{reservation_id}"
        ).first()

        # When the webhook fires sync_conversation_messages for a reservation
        # we've never seen before (guest's first message arrives before any
        # daemon cycle has imported the reservation), we have no guest context.
        # Without this prefetch, process_incoming_message receives sender_name
        # and sender_email as None, find_or_create_guest creates a Guest row
        # with all NULL fields, and the inbox shows "Unknown Guest" with no
        # check-in dates. Fetch the reservation detail up front so the first
        # message arrives with proper guest identity and we can backfill
        # check_in/check_out + enrich after the loop.
        res_detail: Optional[Dict[str, Any]] = None
        prefetched_guest_name = ''
        prefetched_guest_email = ''
        prefetched_property_id: Optional[int] = None
        if not conv:
            res_detail = self.get_reservation(reservation_id)
            if res_detail:
                firstname = res_detail.get('first-name') or res_detail.get('firstname') or ''
                lastname = res_detail.get('last-name') or res_detail.get('lastname') or ''
                prefetched_guest_name = f"{firstname} {lastname}".strip() or (
                    res_detail.get('guest-name') or '')
                prefetched_guest_email = (res_detail.get('email')
                                          or res_detail.get('guest-email') or '')
                # Resolve the apartment now so the conversation is born linked
                # to its property — otherwise the inbox shows "Reservation <id>".
                prefetched_property_id = self._resolve_property_id(res_detail)

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

                # Account cutoff: a newly connected account starts fresh instead
                # of pulling its whole history into the inbox.
                if self._too_old(msg_time):
                    continue

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
                    else:
                        # First-touch via webhook: use the values fetched from
                        # /reservations/<id> at the top of this function so the
                        # Guest row gets created with proper identity.
                        guest_name = prefetched_guest_name
                        guest_email = prefetched_guest_email

                    proc_result = router.process_incoming_message(
                        platform='smoobu',
                        platform_conversation_id=f"smoobu-{reservation_id}",
                        sender_email=guest_email or None,
                        sender_name=guest_name or None,
                        message_content=msg_content,
                        subject=f"Reservation {reservation_id}",
                        platform_message_id=platform_msg_id,
                        property_id=prefetched_property_id,
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
                    # Owner/host message. Create the conversation if this is an
                    # owner-outbound-only thread we've never seen (welcome /
                    # invoice / marketing send on a brand-new booking, before any
                    # guest reply). Previously this did `if not conv: continue`,
                    # which silently dropped these threads when they arrived via
                    # the webhook / /threads sweep — they only appeared if the
                    # /reservations daemon happened to discover them. Mirror
                    # sync_messages so owner-only chats are created here too.
                    if not conv:
                        from .guest_matching import find_existing_guest
                        guest = find_existing_guest(
                            email=prefetched_guest_email or None,
                            name=prefetched_guest_name or None,
                        )
                        if not guest:
                            guest = Guest(
                                name=prefetched_guest_name or f"Guest {reservation_id}",
                                email=prefetched_guest_email or None,
                            )
                            db.session.add(guest)
                            try:
                                db.session.flush()
                            except IntegrityError:
                                # Concurrent webhook beat us to it (email unique).
                                db.session.rollback()
                                guest = find_existing_guest(
                                    email=prefetched_guest_email or None,
                                    name=prefetched_guest_name or None,
                                )
                                if not guest:
                                    raise
                        conv = Conversation(
                            guest_id=guest.id,
                            platform='smoobu',
                            platform_id=f"smoobu-{reservation_id}",
                            subject=f"Reservation {reservation_id}",
                            smoobu_reservation_id=reservation_id,
                            smoobu_account_id=self.account_id,
                            property_id=prefetched_property_id,
                        )
                        db.session.add(conv)
                        db.session.commit()

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
                        try:
                            db.session.flush()  # get owner_msg.id
                            # updated_at: polling tripwire — bump on any
                            # new owner message so clients refresh.
                            conv.updated_at = datetime.utcnow()
                            # last_message_at: sort key — only advance
                            # when this is genuinely the newest message.
                            if not conv.last_message_at or owner_msg.sent_at > conv.last_message_at:
                                conv.last_message_at = owner_msg.sent_at
                            # Update sync watermark
                            if not conv.last_synced_message_at or owner_msg.sent_at > conv.last_synced_message_at:
                                conv.last_synced_message_at = owner_msg.sent_at
                            # Mark as read — someone already replied outside the
                            # app. Skip automated templates: they are not a reply,
                            # so they must not hide an unread guest message.
                            if not _is_automated_smoobu_message(msg):
                                conv.is_read = True
                                if not conv.last_read_message_id or owner_msg.id > conv.last_read_message_id:
                                    conv.last_read_message_id = owner_msg.id
                            db.session.commit()
                            result['imported'] += 1
                        except IntegrityError:
                            # Another concurrent sync path inserted the same message first.
                            db.session.rollback()
                            logger.debug(
                                "Concurrent insert detected for platform_msg_id=%s, skipping",
                                platform_msg_id,
                            )

                    if platform_msg_id:
                        known_ids.add(platform_msg_id)

            except Exception as e:
                logger.error(f"Error syncing message for reservation {reservation_id}: {e}")
                result['errors'].append(str(e))

        # If the conversation was just created by the first guest message above,
        # backfill check_in/check_out from the reservation detail we already
        # fetched, and enrich the new Guest with phone/channel/etc. Without
        # this, webhook-first conversations show no stay dates in the inbox.
        final_conv = conv if conv else Conversation.query.filter_by(
            platform_id=f"smoobu-{reservation_id}"
        ).first()
        if final_conv and res_detail:
            changed = False
            if not final_conv.check_in:
                ci = _parse_smoobu_date(
                    res_detail.get('arrival') or res_detail.get('check-in'))
                if ci:
                    final_conv.check_in = ci
                    changed = True
            if not final_conv.check_out:
                co = _parse_smoobu_date(
                    res_detail.get('departure') or res_detail.get('check-out'))
                if co:
                    final_conv.check_out = co
                    changed = True
            ad, ch = _res_guest_counts(res_detail)
            if ad is not None and final_conv.adults != ad:
                final_conv.adults = ad
                changed = True
            if ch is not None and final_conv.children != ch:
                final_conv.children = ch
                changed = True
            if not final_conv.smoobu_reservation_id:
                final_conv.smoobu_reservation_id = reservation_id
                changed = True
            if not final_conv.smoobu_account_id and self.account_id:
                final_conv.smoobu_account_id = self.account_id
                changed = True
            if final_conv.property_id is None and prefetched_property_id:
                final_conv.property_id = prefetched_property_id
                changed = True
            if final_conv.guest:
                try:
                    self._enrich_guest_from_reservation(
                        final_conv.guest, res_detail, reservation_id)
                except Exception as e:
                    logger.warning(
                        f"Guest enrichment failed for conv {final_conv.id}: {e}")
            if changed:
                db.session.commit()

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
        if street:
            fields['street'] = street

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

    def mark_reservation_cancelled(self, reservation_id) -> bool:
        """Mark the Conversation linked to this Smoobu reservation as cancelled.

        Called only from the webhook dispatcher on `cancelReservation` events.
        Idempotent: re-setting cancelled_at on an already-cancelled Conversation
        is a no-op (returns True without re-committing).

        Returns True if the Conversation was found (and is now marked cancelled),
        False if no matching Conversation exists yet — that's normal for a
        reservation whose guest never sent a message.

        Spec-reference: WEBHOOK_IMPLEMENTATION.md Step 8 (2026-05-19).
        """
        from ..models import db, Conversation

        rid = str(reservation_id) if reservation_id is not None else ''
        if not rid:
            logger.warning("mark_reservation_cancelled: empty reservation_id")
            return False

        conv = Conversation.query.filter_by(
            platform_id=f"smoobu-{rid}"
        ).first()
        if not conv:
            logger.info(
                "mark_reservation_cancelled %s: no Conversation found (guest never messaged)",
                rid,
            )
            return False

        if conv.cancelled_at:
            logger.debug(
                "mark_reservation_cancelled %s: already cancelled at %s",
                rid, conv.cancelled_at,
            )
            return True

        try:
            conv.cancelled_at = datetime.utcnow()
            # Bump updated_at so the inbox poller's tripwire fires and the
            # frontend refreshes the card with the new label.
            conv.updated_at = datetime.utcnow()
            db.session.commit()
            logger.info("mark_reservation_cancelled %s: marked conv_id=%s", rid, conv.id)
            return True
        except Exception:
            logger.exception("mark_reservation_cancelled %s failed", rid)
            try:
                db.session.rollback()
            except Exception:
                pass
            return False

    def update_reservation_from_webhook(self, res_data: Dict) -> bool:
        """Silently update Conversation + GuestDetail when a reservation changes.

        Called only from the webhook dispatcher on `updateReservation` events.
        Smoobu's payload mirrors newReservation (full reservation inline), so
        we can reuse the same enrichment helper. Updates:
          - Conversation.check_in / check_out (if present in payload)
          - GuestDetail via existing _enrich_guest_from_reservation upsert
            (adults, children, language, channel, guest note)

        Does NOT notify the team or change any visible status — the user
        wants silent updates ("just have the right information").

        Returns True if anything was found/updated, False if no Conversation
        or Guest exists yet for this reservation.

        Spec-reference: WEBHOOK_IMPLEMENTATION.md Step 8 (2026-05-19).
        """
        from ..models import db, Conversation

        rid = res_data.get('id')
        if not rid:
            logger.warning("update_reservation_from_webhook: payload missing id")
            return False

        rid_str = str(rid)
        conv = Conversation.query.filter_by(
            platform_id=f"smoobu-{rid_str}"
        ).first()

        try:
            changed = False

            # 1. Refresh Conversation.check_in / check_out if the Conversation
            #    exists. Use the same date parser as the daemon's enrichment
            #    code path to stay consistent.
            if conv:
                ci = _parse_smoobu_date(
                    res_data.get('arrival') or res_data.get('check-in')
                )
                co = _parse_smoobu_date(
                    res_data.get('departure') or res_data.get('check-out')
                )
                if ci and conv.check_in != ci:
                    conv.check_in = ci
                    changed = True
                if co and conv.check_out != co:
                    conv.check_out = co
                    changed = True
                ad, ch = _res_guest_counts(res_data)
                if ad is not None and conv.adults != ad:
                    conv.adults = ad
                    changed = True
                if ch is not None and conv.children != ch:
                    conv.children = ch
                    changed = True
                if changed:
                    # Tripwire so inbox/conversation pages refresh
                    conv.updated_at = datetime.utcnow()
                    db.session.commit()

            # 2. Refresh Guest + GuestDetail via the existing upsert.
            #    Reuses process_new_reservation (find_or_create_guest +
            #    _enrich_guest_from_reservation). Safe to re-call.
            guest = self.process_new_reservation(res_data)

            if changed or guest:
                logger.info(
                    "update_reservation_from_webhook %s: conv_changed=%s guest_id=%s",
                    rid_str, changed, guest.id if guest else None,
                )
                return True

            logger.debug(
                "update_reservation_from_webhook %s: nothing to update (no conv, no guest)",
                rid_str,
            )
            return False
        except Exception:
            logger.exception("update_reservation_from_webhook %s failed", rid_str)
            try:
                db.session.rollback()
            except Exception:
                pass
            return False

    def process_new_reservation(self, res_data: Dict) -> Optional['Guest']:
        """Pre-populate Guest + GuestDetail enrichment from a Smoobu `newReservation` webhook payload.

        Called only from the webhook dispatcher. The payload contains the FULL
        reservation inline (dates, party size, channel, language, phone, notice,
        property), so no extra Smoobu API call is needed.

        We deliberately do NOT create a Conversation here — that's created by
        MessageRouter when the first message arrives. Pre-creating an empty
        Conversation would clutter the inbox listing (which sorts by
        last_message_at). Pre-creating the Guest is enough: when the first
        message arrives, MessageRouter's find_or_create_guest matches by
        phone/email and reuses this record, so the very first AI response
        already has full guest context.

        Returns the Guest object on success, or None if the payload is
        unusable (no phone/email/name → can't safely identify a guest).

        Spec-reference: WEBHOOK_IMPLEMENTATION.md Step 6 (2026-05-18).
        """
        from ..models import db
        from .memory_service import get_memory_service

        reservation_id = res_data.get('id')
        if not reservation_id:
            logger.warning("process_new_reservation: payload missing id")
            return None

        email = (res_data.get('email') or '').strip() or None
        phone = (res_data.get('phone') or res_data.get('phone-number')
                 or res_data.get('guestPhone') or '').strip() or None
        name = (res_data.get('guest-name') or res_data.get('firstname')
                or res_data.get('lastname') or '').strip() or None

        # Bail if there's nothing to match on. Without ANY of email/phone/name
        # we'd create a totally anonymous Guest record that the first message
        # could never reliably match against.
        if not (email or phone or name):
            logger.warning(
                "process_new_reservation %s: no email/phone/name in payload — skipping pre-enrichment",
                reservation_id,
            )
            return None

        memory = get_memory_service()
        if not memory:
            logger.warning("process_new_reservation: MemoryService not available")
            return None

        try:
            guest = memory.find_or_create_guest(
                email=email,
                phone=phone,
                platform='smoobu',
                platform_id=None,
                name=name,
            )
            if not guest:
                logger.warning("process_new_reservation %s: find_or_create_guest returned None", reservation_id)
                return None

            # Reuse the existing enrichment helper — exact same code path the
            # daemon sync uses when it discovers a new reservation, just
            # triggered seconds earlier by the webhook instead of minutes
            # later by the polling loop.
            self._enrich_guest_from_reservation(guest, res_data, str(reservation_id))
            db.session.commit()
            logger.info(
                "process_new_reservation %s: pre-enriched guest_id=%s name=%s",
                reservation_id, guest.id, (guest.name or '')[:60],
            )
            return guest
        except Exception:
            logger.exception("process_new_reservation %s failed", reservation_id)
            try:
                db.session.rollback()
            except Exception:
                pass
            return None

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
                existing = self._property_for_apartment(apt_id)
                if existing:
                    # Update all fields
                    changed = False
                    if existing.name != name:
                        existing.name = name
                        changed = True
                    # Stamp legacy rows (synced before multi-account) with their account
                    if not existing.smoobu_account_id and self.account_id:
                        existing.smoobu_account_id = self.account_id
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
                        smoobu_account_id=self.account_id,
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


# =============================================================================
# Account registry
#
# UMI talks to more than one Smoobu account (the Sonnenhof apartment lives in a
# separate one). Each account is one SmoobuService with its own API key. The
# account is never typed in by hand: the key identifies itself via GET /me, and
# every webhook carries the same id in its "user" field.
#
# Settings keys: slot 1 is the original 'smoobu_api_key' (unchanged, so the
# existing setup keeps working); further slots are 'smoobu_api_key_2', ...
# =============================================================================

MAX_SMOOBU_ACCOUNTS = 3  # ponytail: fixed slots beat an accounts table for 2-3 keys

# Global instances, one per configured slot (slot number -> service)
_smoobu_services: Dict[int, SmoobuService] = {}


def settings_key(slot: int) -> str:
    """AISettings key holding the API key for a slot (slot 1 = legacy name)."""
    return 'smoobu_api_key' if slot == 1 else f'smoobu_api_key_{slot}'


def secret_settings_key(slot: int) -> str:
    """AISettings key holding the HMAC secret for a slot (empty = legacy auth)."""
    return 'smoobu_api_secret' if slot == 1 else f'smoobu_api_secret_{slot}'


def sync_from_settings_key(slot: int) -> str:
    """AISettings key holding the 'ignore messages older than this' cutoff.

    Set when a *new* account is connected so it starts with the messages that
    arrive from then on, instead of importing years of history into the inbox.
    """
    return 'smoobu_sync_from' if slot == 1 else f'smoobu_sync_from_{slot}'


def account_settings_key(slot: int) -> str:
    """AISettings key holding the resolved Smoobu account id for a slot."""
    return 'smoobu_account_id' if slot == 1 else f'smoobu_account_id_{slot}'


def init_smoobu_service(app) -> SmoobuService:
    """Initialize all configured Smoobu accounts. Returns slot 1 (back-compat)."""
    global _smoobu_services
    api_url = app.config.get('SMOOBU_API_URL', 'https://login.smoobu.com/api')
    _smoobu_services = {
        slot: SmoobuService(
            api_url=api_url,
            # Only slot 1 inherits the env/config key; extra slots are DB-only.
            api_key=app.config.get('SMOOBU_API_KEY', '') if slot == 1 else '',
            slot=slot,
        )
        for slot in range(1, MAX_SMOOBU_ACCOUNTS + 1)
    }
    logger.info("Smoobu Service initialized (%d slots)", len(_smoobu_services))
    return _smoobu_services[1]


def get_smoobu_service() -> Optional[SmoobuService]:
    """Get the primary (slot 1) Smoobu service instance.

    Kept for the many call sites that are not conversation-scoped. Anything
    that sends or syncs for a specific chat must use get_smoobu_service_for().
    """
    return _smoobu_services.get(1)


def get_smoobu_services() -> List[SmoobuService]:
    """Every configured account, primary first. Used by the sync daemon."""
    return [svc for _, svc in sorted(_smoobu_services.items()) if svc.is_configured()]


def get_smoobu_service_by_account(account_id) -> Optional[SmoobuService]:
    """Find the service for a Smoobu account id (the webhook 'user' field)."""
    if not account_id:
        return None
    wanted = str(account_id)
    for _, svc in sorted(_smoobu_services.items()):
        if svc.is_configured() and str(svc.account_id or '') == wanted:
            return svc
    return None


def get_smoobu_service_for(obj) -> Optional[SmoobuService]:
    """Service for a Conversation/Property, by its smoobu_account_id tag.

    Falls back to slot 1 for rows written before multi-account existed (their
    tag is NULL) — that is exactly the old single-account behaviour.
    """
    svc = get_smoobu_service_by_account(getattr(obj, 'smoobu_account_id', None))
    return svc or get_smoobu_service()
