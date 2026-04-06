"""
In-memory debug log handler for ChatBotAI.
Stores recent log entries in a ring buffer accessible via the debug page.
"""

import logging
import time
from collections import deque
from datetime import datetime
from threading import Lock
from typing import List, Dict, Any, Optional


class DebugLogHandler(logging.Handler):
    """Custom log handler that stores entries in a ring buffer."""

    def __init__(self, max_entries: int = 500):
        super().__init__()
        self._entries: deque = deque(maxlen=max_entries)
        self._lock = Lock()
        self._error_count = 0
        self._warning_count = 0

    def emit(self, record: logging.LogRecord):
        try:
            entry = {
                'timestamp': datetime.fromtimestamp(record.created).isoformat(),
                'level': record.levelname,
                'logger': record.name,
                'message': self.format(record),
                'module': record.module,
                'funcName': record.funcName,
                'lineno': record.lineno,
            }
            if record.exc_info and record.exc_info[0]:
                entry['exception'] = self.format(record)

            with self._lock:
                self._entries.append(entry)
                if record.levelno >= logging.ERROR:
                    self._error_count += 1
                elif record.levelno >= logging.WARNING:
                    self._warning_count += 1
        except Exception:
            self.handleError(record)

    def get_entries(self, level: Optional[str] = None,
                    logger_name: Optional[str] = None,
                    limit: int = 200) -> List[Dict]:
        with self._lock:
            entries = list(self._entries)
        # Newest first
        entries.reverse()
        if level:
            level_upper = level.upper()
            level_no = getattr(logging, level_upper, None)
            if level_no is not None:
                entries = [e for e in entries if getattr(logging, e['level'], 0) >= level_no]
        if logger_name:
            entries = [e for e in entries if logger_name in e['logger']]
        return entries[:limit]

    def get_stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                'total': len(self._entries),
                'errors': self._error_count,
                'warnings': self._warning_count,
            }

    def clear(self):
        with self._lock:
            self._entries.clear()
            self._error_count = 0
            self._warning_count = 0


class ApiTracker:
    """Tracks API call statistics for Smoobu, Gmail, Ollama."""

    def __init__(self, max_entries: int = 100):
        self._calls: deque = deque(maxlen=max_entries)
        self._lock = Lock()

    def record(self, service: str, method: str, endpoint: str,
               status_code: Optional[int] = None, duration_ms: float = 0,
               error: Optional[str] = None):
        entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'service': service,
            'method': method,
            'endpoint': endpoint,
            'status_code': status_code,
            'duration_ms': round(duration_ms, 1),
            'error': error,
        }
        with self._lock:
            self._calls.append(entry)

    def get_calls(self, service: Optional[str] = None,
                  limit: int = 50) -> List[Dict]:
        with self._lock:
            calls = list(self._calls)
        calls.reverse()
        if service:
            calls = [c for c in calls if c['service'] == service]
        return calls[:limit]

    def get_summary(self) -> Dict[str, Any]:
        with self._lock:
            calls = list(self._calls)
        summary = {}
        for svc in ('smoobu', 'gmail', 'ollama'):
            svc_calls = [c for c in calls if c['service'] == svc]
            errors = [c for c in svc_calls if c.get('error') or (c.get('status_code') and c['status_code'] >= 400)]
            avg_ms = 0
            if svc_calls:
                avg_ms = sum(c['duration_ms'] for c in svc_calls) / len(svc_calls)
            summary[svc] = {
                'total_calls': len(svc_calls),
                'errors': len(errors),
                'avg_duration_ms': round(avg_ms, 1),
            }
        return summary


# Global instances
_log_handler: Optional[DebugLogHandler] = None
_api_tracker: Optional[ApiTracker] = None


def init_debug_service(app) -> DebugLogHandler:
    """Attach the in-memory log handler to the root logger."""
    global _log_handler, _api_tracker

    _log_handler = DebugLogHandler(max_entries=500)
    _log_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    _log_handler.setLevel(logging.DEBUG)
    logging.getLogger().addHandler(_log_handler)

    _api_tracker = ApiTracker(max_entries=200)

    return _log_handler


def get_log_handler() -> Optional[DebugLogHandler]:
    return _log_handler


def get_api_tracker() -> Optional[ApiTracker]:
    return _api_tracker
