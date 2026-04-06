"""
Gmail Service for ChatBotAI
Handles Gmail API integration for receiving and sending emails.

Setup Requirements:
1. Go to Google Cloud Console (https://console.cloud.google.com)
2. Create a new project or select existing
3. Enable Gmail API
4. Create OAuth 2.0 credentials (Web application)
5. Add authorized redirect URI(s): http://localhost/chatbot/gmail/callback
   (and your Cloudflare tunnel URL if using one, e.g. https://yourdomain/chatbot/gmail/callback)
6. Download credentials.json and place in ChatBotAI folder

Email Filtering:
- Only processes emails from allowed domains (Airbnb, Booking.com, etc.)
- Filters by subject keywords related to vacation rentals
- Prevents processing personal/unrelated emails
"""

import os
import re
import base64
import logging
import json
from datetime import datetime, timedelta

# Allow OAuth over HTTP for local development (localhost)
# This is required because google-auth-oauthlib rejects http:// redirect URIs by default
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, List, Any, Tuple
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# Scopes required for Gmail access
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify'
]

# Base directory for credentials
CHATBOT_DIR = Path(__file__).resolve().parent.parent


class GmailService:
    """Service for Gmail API integration"""

    def __init__(self, credentials_file: str = None, token_file: str = None):
        """
        Initialize Gmail service.

        Args:
            credentials_file: Path to OAuth credentials JSON file
            token_file: Path to store/load user tokens
        """
        self.credentials_file = credentials_file or str(CHATBOT_DIR / 'credentials.json')
        self.token_file = token_file or str(CHATBOT_DIR / 'instance' / 'gmail_token.json')
        self.credentials: Optional[Credentials] = None
        self.service = None
        self._user_email = None

        # Email filtering settings (loaded from config)
        self._load_filter_settings()

    def _load_filter_settings(self):
        """Load email filter settings from database (saved settings) or config (defaults)"""
        import json

        # Default values from config
        try:
            from flask import current_app
            default_domains = current_app.config.get('EMAIL_ALLOWED_DOMAINS', [])
            default_keywords = current_app.config.get('EMAIL_SUBJECT_KEYWORDS', [])
            default_mode = current_app.config.get('EMAIL_FILTER_MODE', 'either')
        except RuntimeError:
            from ..config import Config
            default_domains = getattr(Config, 'EMAIL_ALLOWED_DOMAINS', [])
            default_keywords = getattr(Config, 'EMAIL_SUBJECT_KEYWORDS', [])
            default_mode = getattr(Config, 'EMAIL_FILTER_MODE', 'either')

        # Try to load saved settings from database
        try:
            from ..models import AISettings
            saved_domains = AISettings.get('email_allowed_domains')
            saved_keywords = AISettings.get('email_subject_keywords')
            saved_mode = AISettings.get('email_filter_mode')

            self.allowed_domains = json.loads(saved_domains) if saved_domains else default_domains
            self.subject_keywords = json.loads(saved_keywords) if saved_keywords else default_keywords
            self.filter_mode = saved_mode if saved_mode else default_mode
        except Exception:
            # Database not available or no saved settings - use defaults
            self.allowed_domains = default_domains
            self.subject_keywords = default_keywords
            self.filter_mode = default_mode

    def get_filter_settings(self) -> Dict[str, Any]:
        """Get current email filter settings"""
        return {
            'allowed_domains': self.allowed_domains,
            'subject_keywords': self.subject_keywords,
            'filter_mode': self.filter_mode
        }

    def update_filter_settings(self, allowed_domains: List[str] = None,
                                subject_keywords: List[str] = None,
                                filter_mode: str = None):
        """Update email filter settings"""
        if allowed_domains is not None:
            self.allowed_domains = [d.lower().strip() for d in allowed_domains if d.strip()]
        if subject_keywords is not None:
            self.subject_keywords = [k.lower().strip() for k in subject_keywords if k.strip()]
        if filter_mode is not None:
            if filter_mode in ('domain', 'keyword', 'both', 'either'):
                self.filter_mode = filter_mode

    def _matches_domain_filter(self, sender_email: str) -> bool:
        """Check if sender email matches allowed domains"""
        if not self.allowed_domains:
            return True  # No filter = allow all

        sender_email = sender_email.lower()
        for domain in self.allowed_domains:
            if sender_email.endswith(f'@{domain}') or sender_email.endswith(f'.{domain}'):
                return True
        return False

    def _matches_keyword_filter(self, subject: str) -> bool:
        """Check if subject contains allowed keywords"""
        if not self.subject_keywords:
            return True  # No filter = allow all

        subject_lower = subject.lower()
        for keyword in self.subject_keywords:
            if keyword in subject_lower:
                return True
        return False

    def email_matches_filter(self, email: Dict[str, Any]) -> bool:
        """
        Check if an email matches the configured filters.

        Args:
            email: Parsed email dictionary with 'sender_email' and 'subject'

        Returns:
            True if email should be processed, False if filtered out
        """
        sender_email = email.get('sender_email', '')
        subject = email.get('subject', '')

        domain_match = self._matches_domain_filter(sender_email)
        keyword_match = self._matches_keyword_filter(subject)

        if self.filter_mode == 'domain':
            return domain_match
        elif self.filter_mode == 'keyword':
            return keyword_match
        elif self.filter_mode == 'both':
            return domain_match and keyword_match
        else:  # 'either' (default)
            return domain_match or keyword_match

    def is_configured(self) -> bool:
        """Check if Gmail credentials file exists"""
        return os.path.exists(self.credentials_file)

    def is_authenticated(self) -> bool:
        """Check if we have valid credentials, refreshing if needed"""
        if not self.credentials or not self.credentials.valid:
            self._load_credentials()
        return self.credentials is not None and self.credentials.valid

    def _load_credentials(self) -> bool:
        """Load credentials from token file and refresh if expired"""
        if not os.path.exists(self.token_file):
            return False

        try:
            self.credentials = Credentials.from_authorized_user_file(
                self.token_file, SCOPES
            )
        except Exception as e:
            logger.error(f"Error reading token file: {e}")
            self.credentials = None
            return False

        # Try to refresh expired credentials
        if self.credentials and self.credentials.expired and self.credentials.refresh_token:
            try:
                self.credentials.refresh(Request())
                self._save_credentials()
                logger.info("Gmail token refreshed successfully")
            except Exception as e:
                logger.warning(f"Gmail token refresh failed: {e}")
                # Token is no longer usable - clear stale state
                self.credentials = None
                self.service = None
                self._user_email = None
                return False

        return self.credentials is not None and self.credentials.valid

    def _save_credentials(self):
        """Save credentials to token file"""
        if self.credentials:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.token_file), exist_ok=True)
            with open(self.token_file, 'w') as f:
                f.write(self.credentials.to_json())

    def get_authorization_url(self, redirect_uri: str) -> Tuple[str, str]:
        """
        Get the OAuth authorization URL.

        Args:
            redirect_uri: The callback URL after authorization

        Returns:
            Tuple of (authorization_url, state)
        """
        if not self.is_configured():
            raise ValueError("Gmail credentials file not found. Please configure OAuth credentials.")

        flow = Flow.from_client_secrets_file(
            self.credentials_file,
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )

        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )

        return authorization_url, state

    def handle_oauth_callback(self, authorization_response: str, redirect_uri: str, state: str = None) -> bool:
        """
        Handle the OAuth callback and store credentials.

        Args:
            authorization_response: The full callback URL with code
            redirect_uri: The redirect URI used in authorization
            state: The state parameter (optional)

        Returns:
            True if successful
        """
        try:
            flow = Flow.from_client_secrets_file(
                self.credentials_file,
                scopes=SCOPES,
                redirect_uri=redirect_uri,
                state=state
            )

            flow.fetch_token(authorization_response=authorization_response)
            self.credentials = flow.credentials
            self.service = None  # Clear cached service to rebuild with new credentials
            self._user_email = None
            self._save_credentials()

            logger.info("Gmail OAuth completed successfully")
            return True

        except Exception as e:
            logger.error(f"OAuth callback error: {e}", exc_info=True)
            raise

    def _get_service(self):
        """Get or create Gmail API service, refreshing credentials if needed"""
        # Always verify credentials are valid before returning cached service
        if not self.is_authenticated():
            self.service = None
            raise ValueError("Not authenticated. Please complete OAuth flow first.")
        if not self.service:
            self.service = build('gmail', 'v1', credentials=self.credentials)
        return self.service

    def get_user_email(self) -> Optional[str]:
        """Get the authenticated user's email address"""
        if self._user_email:
            return self._user_email

        try:
            service = self._get_service()
            profile = service.users().getProfile(userId='me').execute()
            self._user_email = profile.get('emailAddress')
            return self._user_email
        except Exception as e:
            logger.error(f"Error getting user email: {e}")
            return None

    def get_recent_emails(self, max_results: int = 10, query: str = None,
                          apply_filter: bool = True) -> List[Dict[str, Any]]:
        """
        Fetch recent emails from inbox.

        Uses a two-phase approach when filtering:
        1. Fetch headers only (fast) to check domain/keyword filters
        2. Fetch full content only for emails that pass the filter

        Args:
            max_results: Maximum number of emails to fetch
            query: Gmail search query (e.g., 'is:unread', 'from:someone@example.com')
            apply_filter: If True, filter emails by domain/keyword settings

        Returns:
            List of email dictionaries (filtered by vacation rental criteria)
        """
        try:
            service = self._get_service()

            # Build query
            search_query = query or 'in:inbox'

            # Fetch more than needed since we'll filter some out
            fetch_count = max_results * 3 if apply_filter else max_results

            # Get message list
            results = service.users().messages().list(
                userId='me',
                maxResults=fetch_count,
                q=search_query
            ).execute()

            messages = results.get('messages', [])
            emails = []
            filtered_count = 0

            for msg in messages:
                if len(emails) >= max_results:
                    break

                if apply_filter:
                    # Phase 1: Fetch headers only (much faster than full content)
                    try:
                        header_data = service.users().messages().get(
                            userId='me', id=msg['id'],
                            format='metadata',
                            metadataHeaders=['From', 'Subject']
                        ).execute()
                        headers = {h['name'].lower(): h['value']
                                   for h in header_data['payload'].get('headers', [])}
                        from_header = headers.get('from', '')
                        _, sender_email = self._parse_email_address(from_header)
                        subject = headers.get('subject', '')

                        if not self.email_matches_filter(
                            {'sender_email': sender_email, 'subject': subject}
                        ):
                            filtered_count += 1
                            logger.debug(f"Filtered out email from {sender_email}: '{subject[:50]}'")
                            continue
                    except Exception as e:
                        logger.warning(f"Error checking email headers {msg['id']}: {e}")
                        continue

                # Phase 2: Fetch full content only for matching emails
                email_data = self.get_email_by_id(msg['id'])
                if email_data:
                    emails.append(email_data)

            if filtered_count > 0:
                logger.info(f"Filtered out {filtered_count} non-vacation-rental emails")

            return emails

        except HttpError as e:
            logger.error(f"Gmail API error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error fetching emails: {e}")
            return []

    def get_email_by_id(self, message_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a single email by ID.

        Args:
            message_id: Gmail message ID

        Returns:
            Email dictionary with parsed content
        """
        try:
            service = self._get_service()

            message = service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()

            return self._parse_email(message)

        except HttpError as e:
            logger.error(f"Gmail API error: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching email {message_id}: {e}")
            return None

    def _parse_email(self, message: Dict) -> Dict[str, Any]:
        """Parse Gmail API message into a cleaner format"""
        headers = {h['name'].lower(): h['value'] for h in message['payload'].get('headers', [])}

        # Extract body
        body = self._get_email_body(message['payload'])

        # Parse sender
        from_header = headers.get('from', '')
        sender_name, sender_email = self._parse_email_address(from_header)

        return {
            'id': message['id'],
            'thread_id': message['threadId'],
            'subject': headers.get('subject', '(No Subject)'),
            'from': from_header,
            'sender_name': sender_name,
            'sender_email': sender_email,
            'to': headers.get('to', ''),
            'date': headers.get('date', ''),
            'body': body,
            'snippet': message.get('snippet', ''),
            'labels': message.get('labelIds', []),
            'is_unread': 'UNREAD' in message.get('labelIds', [])
        }

    def _get_email_body(self, payload: Dict) -> str:
        """Extract email body from payload"""
        body = ""

        if 'body' in payload and payload['body'].get('data'):
            body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
        elif 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    if 'data' in part['body']:
                        body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                        break
                elif part['mimeType'] == 'text/html' and not body:
                    if 'data' in part['body']:
                        html_body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                        body = self._html_to_text(html_body)
                elif 'parts' in part:
                    # Nested multipart
                    body = self._get_email_body(part)
                    if body:
                        break

        return self._clean_email_body(body)

    @staticmethod
    def _html_to_text(html: str) -> str:
        """Convert HTML to clean plain text"""
        import html as html_module

        # Remove style and script blocks entirely
        text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)

        # Convert <br> and block elements to newlines
        text = re.sub(r'<br\s*/?\s*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</(?:p|div|tr|li|h[1-6])>', '\n', text, flags=re.IGNORECASE)

        # Strip remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)

        # Decode HTML entities
        text = html_module.unescape(text)

        return text

    @staticmethod
    def _clean_email_body(body: str) -> str:
        """Clean email body: remove quoted replies, signatures, and excessive whitespace"""
        if not body:
            return ""

        lines = body.splitlines()
        cleaned = []

        for line in lines:
            stripped = line.strip()

            # Stop at quoted reply markers
            # English: "On ... wrote:"
            if re.match(r'^On .+ wrote:\s*$', stripped):
                break
            # German: "Am ... schrieb ...:"
            if re.match(r'^Am .+ schrieb .+:\s*$', stripped):
                break
            # Generic: "--- Original Message ---" or "---------- Forwarded message"
            if re.match(r'^-{2,}\s*(Original Message|Forwarded message|Urspr)', stripped, re.IGNORECASE):
                break
            # Gmail-style: "> " quoted lines (stop at first block of quotes)
            if stripped.startswith('>'):
                break
            # Email signature delimiter
            if stripped == '--':
                break

            cleaned.append(line)

        text = '\n'.join(cleaned)

        # Collapse excessive blank lines to max 2
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Collapse excessive spaces
        text = re.sub(r'[ \t]{2,}', ' ', text)

        return text.strip()

    def _parse_email_address(self, address: str) -> Tuple[str, str]:
        """Parse 'Name <email@example.com>' format"""
        import re
        match = re.match(r'(?:"?([^"]*)"?\s)?<?([^>]+@[^>]+)>?', address)
        if match:
            name = match.group(1) or ''
            email = match.group(2)
            return name.strip(), email.strip()
        return '', address.strip()

    def send_email(
            self,
            to: str,
            subject: str,
            body: str,
            thread_id: str = None,
            reply_to_message_id: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Send an email.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body (plain text)
            thread_id: Thread ID to reply in (for threading)
            reply_to_message_id: Message ID to reply to (for References header)

        Returns:
            Sent message info or None on failure
        """
        try:
            service = self._get_service()
            sender = self.get_user_email()

            # Create message
            message = MIMEMultipart()
            message['to'] = to
            message['from'] = sender
            message['subject'] = subject

            # Add threading headers if replying
            if reply_to_message_id:
                # Fetch original message for headers
                original = service.users().messages().get(
                    userId='me',
                    id=reply_to_message_id,
                    format='metadata',
                    metadataHeaders=['Message-ID', 'References']
                ).execute()

                orig_headers = {h['name']: h['value'] for h in original['payload'].get('headers', [])}
                original_message_id = orig_headers.get('Message-ID', '')

                if original_message_id:
                    message['In-Reply-To'] = original_message_id
                    references = orig_headers.get('References', '')
                    message['References'] = f"{references} {original_message_id}".strip()

                # Ensure subject has Re: prefix
                if not subject.lower().startswith('re:'):
                    message['subject'] = f"Re: {subject}"

            message.attach(MIMEText(body, 'plain'))

            # Encode message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

            # Send
            send_body = {'raw': raw_message}
            if thread_id:
                send_body['threadId'] = thread_id

            sent = service.users().messages().send(
                userId='me',
                body=send_body
            ).execute()

            logger.info(f"Email sent successfully. Message ID: {sent['id']}")
            return sent

        except HttpError as e:
            logger.error(f"Gmail API error sending email: {e}")
            return None
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return None

    def mark_as_read(self, message_id: str) -> bool:
        """Mark an email as read"""
        try:
            service = self._get_service()
            service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            return True
        except Exception as e:
            logger.error(f"Error marking email as read: {e}")
            return False

    def get_unread_emails(self, max_results: int = 20, apply_filter: bool = True) -> List[Dict[str, Any]]:
        """
        Get unread emails from inbox (filtered for vacation rentals).

        Args:
            max_results: Maximum number of emails to return
            apply_filter: If True, only return vacation rental related emails

        Returns:
            List of filtered unread emails
        """
        return self.get_recent_emails(
            max_results=max_results,
            query='is:unread in:inbox',
            apply_filter=apply_filter
        )

    def get_thread(self, thread_id: str) -> List[Dict[str, Any]]:
        """
        Get all messages in a thread.

        Args:
            thread_id: Gmail thread ID

        Returns:
            List of email dictionaries in chronological order
        """
        try:
            service = self._get_service()

            thread = service.users().threads().get(
                userId='me',
                id=thread_id,
                format='full'
            ).execute()

            messages = []
            for msg in thread.get('messages', []):
                parsed = self._parse_email(msg)
                messages.append(parsed)

            return messages

        except Exception as e:
            logger.error(f"Error fetching thread {thread_id}: {e}")
            return []

    def setup_push_notifications(self, webhook_url: str) -> Optional[Dict]:
        """
        Set up push notifications for new emails.
        Note: Requires a publicly accessible HTTPS webhook URL.

        Args:
            webhook_url: The webhook URL to receive notifications

        Returns:
            Watch response or None on failure
        """
        try:
            service = self._get_service()

            request_body = {
                'labelIds': ['INBOX'],
                'topicName': webhook_url,  # This should be a Cloud Pub/Sub topic
                'labelFilterAction': 'include'
            }

            response = service.users().watch(
                userId='me',
                body=request_body
            ).execute()

            logger.info(f"Push notifications set up. Expiration: {response.get('expiration')}")
            return response

        except Exception as e:
            logger.error(f"Error setting up push notifications: {e}")
            return None

    def disconnect(self) -> bool:
        """Remove stored credentials (disconnect Gmail)"""
        try:
            if os.path.exists(self.token_file):
                os.remove(self.token_file)
            self.credentials = None
            self.service = None
            self._user_email = None
            logger.info("Gmail disconnected successfully")
            return True
        except Exception as e:
            logger.error(f"Error disconnecting Gmail: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get current Gmail connection status"""
        configured = self.is_configured()
        authenticated = self.is_authenticated()

        status = {
            'configured': configured,
            'authenticated': authenticated,
            'email': self.get_user_email() if authenticated else None
        }

        # Add hint when token exists but auth fails (refresh token expired)
        if configured and not authenticated and os.path.exists(self.token_file):
            status['needs_reauth'] = True
            logger.info("Gmail token exists but is invalid - re-authorization needed")

        return status


# Global instance
_gmail_service: Optional[GmailService] = None


def init_gmail_service(credentials_file: str = None, token_file: str = None) -> GmailService:
    """Initialize the Gmail service"""
    global _gmail_service
    _gmail_service = GmailService(credentials_file, token_file)
    logger.info("Gmail Service initialized")
    return _gmail_service


def get_gmail_service() -> GmailService:
    """Get the Gmail service instance"""
    global _gmail_service
    if not _gmail_service:
        _gmail_service = GmailService()
    return _gmail_service
