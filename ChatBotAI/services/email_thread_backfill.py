"""Reconstruct existing conversations from two-sided Gmail email threads.

See docs/superpowers/specs/2026-06-26-email-thread-backfill-design.md.
"""
import logging
from typing import Optional

from ..models import AISettings

logger = logging.getLogger(__name__)

DEFAULT_HOST_ADDRESSES = {
    'buchungsanfrage.urlaubsmagie@gmail.com',
    'buchungsanfrage.urlaubsmagie@googlemail.com',
    'urlaubsmagie@gmail.com',
    'urlaubsmagie@host.smoobu.com',
}


def get_host_addresses() -> set:
    """Lowercased set of addresses that count as 'us' (owner side)."""
    raw = AISettings.get('email_host_addresses', None)
    if not raw:
        return set(DEFAULT_HOST_ADDRESSES)
    return {part.strip().lower() for part in raw.split(',') if part.strip()}


def get_thread_backfill_config() -> dict:
    """Typed settings for thread backfill, with safe defaults."""
    def _bool(key, default):
        return AISettings.get(key, 'true' if default else 'false') == 'true'

    def _int(key, default):
        try:
            return int(AISettings.get(key, str(default)))
        except (TypeError, ValueError):
            return default

    return {
        'auto_enabled': _bool('email_thread_backfill_auto', False),
        'lookback_days': _int('email_thread_backfill_lookback_days', 180),
        'window_minutes': _int('email_thread_backfill_window_minutes', 10),
    }
