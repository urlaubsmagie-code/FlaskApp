"""
In-memory event buffer for Chat Playtest.
Captures pipeline events during playtest conversations for the live event log.
"""

import time
from collections import deque
from threading import Lock
from typing import Dict, List, Tuple, Any

# Per-conversation event buffers: { conversation_id: deque of events }
_buffers: Dict[int, deque] = {}
_lock = Lock()
_MAX_EVENTS = 200


def playtest_log(conversation_id: int, event_type: str, detail: str):
    """Append an event to the playtest buffer for a conversation."""
    event = {
        'index': 0,  # Set below under lock
        'timestamp': time.time(),
        'event_type': event_type,
        'detail': detail,
    }
    with _lock:
        if conversation_id not in _buffers:
            _buffers[conversation_id] = deque(maxlen=_MAX_EVENTS)
        buf = _buffers[conversation_id]
        event['index'] = len(buf)
        buf.append(event)


def get_events(conversation_id: int, since_index: int = 0) -> Tuple[List[Dict[str, Any]], int]:
    """Return events after since_index and the new cursor.

    Returns:
        (events_list, new_cursor) — pass new_cursor as since_index on next call.
    """
    with _lock:
        buf = _buffers.get(conversation_id)
        if not buf:
            return [], 0
        events = [e for e in buf if e['index'] >= since_index]
        new_cursor = buf[-1]['index'] + 1 if buf else 0
    return events, new_cursor


def clear_buffer(conversation_id: int):
    """Clear the event buffer for a conversation."""
    with _lock:
        _buffers.pop(conversation_id, None)
