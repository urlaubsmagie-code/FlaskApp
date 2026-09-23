"""Durable send-attempt history, independent of mutable message delivery flags.

No message text, authentication headers or response bodies are recorded.
This observes transport attempts; it never retries a send.
"""

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock
from datetime import datetime, timezone

from flask import current_app, has_app_context

logger = logging.getLogger(__name__)
_write_lock = Lock()


def record_delivery_event(attempt_id, event, **fields):
    if not has_app_context():
        return
    directory = current_app.config.get('CHATBOT_LOG_DIR')
    if not directory:
        directory = (current_app.instance_path if current_app.testing
                     else Path(__file__).resolve().parents[1] / 'instance')
    payload = {'timestamp': datetime.now(timezone.utc).isoformat(),
               'attempt_id': attempt_id, 'event': event, **fields}
    try:
        with _write_lock:
            Path(directory).mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(Path(directory) / 'delivery_attempts.jsonl',
                                          maxBytes=10 * 1024 * 1024, backupCount=5,
                                          encoding='utf-8', delay=True)
            try:
                handler.emit(logging.LogRecord('delivery', logging.INFO, __file__, 0,
                                               json.dumps(payload), (), None))
            finally:
                handler.close()
    except Exception:
        # An unavailable audit file must not turn a successful send into a
        # reported failure (which could prompt a duplicate human retry).
        logger.exception('Could not write delivery audit event %s', attempt_id)
