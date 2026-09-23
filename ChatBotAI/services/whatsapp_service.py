"""
WhatsApp integration via the local Baileys bridge (whatsapp_bridge/).

The bridge is a Node sidecar linked to a WhatsApp account as an extra device.
This module is only the HTTP client for it — everything WhatsApp-specific
(pairing, protocol, reconnect) lives in the sidecar.

Unofficial client: violates WhatsApp's ToS, the number can be banned. Kept
behind WHATSAPP_BRIDGE_URL so it is simply absent unless deliberately enabled.
"""

import logging
import os
import shutil
import subprocess
import time
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# Bridge listens on loopback only, so a short timeout is right — a slow reply
# means the sidecar is wedged, not that the network is far away.
TIMEOUT = 15

BRIDGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'whatsapp_bridge')
START_COOLDOWN = 30   # seconds: node needs a moment before /status answers


class WhatsAppService:
    def __init__(self, base_url=None, secret=None):
        self.base_url = (base_url or os.environ.get('WHATSAPP_BRIDGE_URL', '')).rstrip('/')
        self.secret = secret or os.environ.get('WHATSAPP_BRIDGE_SECRET', '')
        self._last_start = 0.0

    def is_configured(self):
        return bool(self.base_url)

    def is_running(self):
        """The bridge answered /status (linked or not)."""
        return 'error' not in self.get_status()

    def start_bridge(self):
        """Launch `node index.js` detached, so it outlives this request and a Flask
        restart. Returns the pid, or None if a start is already under way.

        Output goes to whatsapp_bridge/bridge.log — there is no console window
        like the one start_whatsapp_bridge.bat opens.
        """
        # ponytail: in-process cooldown, not a lock file. Two workers clicking at
        # once could still start two bridges; the second dies on the busy port.
        if time.monotonic() - self._last_start < START_COOLDOWN:
            return None
        node = shutil.which('node') or r'C:\Program Files\nodejs\node.exe'
        env = {**os.environ,
               'WHATSAPP_BRIDGE_SECRET': self.secret,
               'WHATSAPP_BRIDGE_PORT': str(urlparse(self.base_url).port or 3001),
               'FLASK_URL': os.environ.get('FLASK_URL', 'http://127.0.0.1')}
        flags = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
        with open(os.path.join(BRIDGE_DIR, 'bridge.log'), 'ab') as log:
            proc = subprocess.Popen([node, 'index.js'], cwd=BRIDGE_DIR, env=env,
                                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                    creationflags=flags)
        self._last_start = time.monotonic()
        logger.info("WhatsApp bridge started from UMI (pid %s)", proc.pid)
        return proc.pid

    def _headers(self):
        return {'Content-Type': 'application/json', 'X-Bridge-Secret': self.secret}

    def get_status(self):
        """{'connected': bool, 'user': str|None, 'qr_pending': bool} — never raises."""
        if not self.is_configured():
            return {'connected': False, 'error': 'not configured'}
        try:
            r = requests.get(f'{self.base_url}/status', headers=self._headers(), timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            logger.warning("WhatsApp bridge status failed: %s", e)
            return {'connected': False, 'error': str(e)}

    def reconnect(self):
        """Ask the bridge to reconnect now, skipping its cooldown.
        Returns (http_status, body). The bridge decides whether it's allowed."""
        if not self.is_configured():
            return 400, {'error': 'WhatsApp bridge not configured'}
        try:
            r = requests.post(f'{self.base_url}/reconnect', headers=self._headers(), json={}, timeout=TIMEOUT)
            return r.status_code, r.json()
        except (requests.RequestException, ValueError) as e:
            logger.warning("WhatsApp reconnect failed: %s", e)
            return 502, {'error': 'Bridge nicht erreichbar – läuft sie?'}

    def send_message(self, jid, text):
        """Send text to a WhatsApp JID. Returns the bridge result dict, or None.

        None means "not delivered" — callers must surface that rather than
        storing the message as sent.
        """
        if not self.is_configured():
            return None
        try:
            r = requests.post(f'{self.base_url}/send', headers=self._headers(),
                              json={'jid': jid, 'text': text}, timeout=TIMEOUT)
            if r.status_code != 200:
                logger.warning("WhatsApp send failed (%s): %s", r.status_code, r.text[:200])
                return None
            return r.json()
        except requests.RequestException as e:
            logger.warning("WhatsApp send failed: %s", e)
            return None


_whatsapp_service = None


def get_whatsapp_service():
    global _whatsapp_service
    if _whatsapp_service is None:
        _whatsapp_service = WhatsAppService()
    return _whatsapp_service
