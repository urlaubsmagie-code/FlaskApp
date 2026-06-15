"""Export Chat Playtest sessions to a readable Markdown log + per-chat notes.

Playtest conversations are durable (``Conversation`` rows tagged
``platform='playtest'`` with their ``Message`` rows and the ``escalated``
flag). This module turns that record — plus the best-effort in-memory event
log and a per-chat note — into a single Markdown file so the team and Claude
can review a playtest session afterwards.

Two pieces:

* ``build_markdown(chats, generated_at)`` — pure: chat dicts -> Markdown.
* notes sidecar — ``save_note`` / ``load_notes`` persist free-text notes per
  conversation in ``<instance>/playtest_notes.json`` (no DB migration needed).
* ``export_playtest_log(app)`` — gathers everything from the DB + event buffer
  and writes ``PLAYTEST_LOG.md`` next to this package.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

NOTES_FILENAME = 'playtest_notes.json'
LOG_FILENAME = 'PLAYTEST_LOG.md'

# Package root (ChatBotAI/) — the log is written here so it sits beside CLAUDE.md.
_PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --------------------------------------------------------------------------
# Notes sidecar
# --------------------------------------------------------------------------

def _notes_path(instance_path: str) -> str:
    return os.path.join(instance_path, NOTES_FILENAME)


def load_notes(instance_path: str) -> Dict[str, str]:
    """Return the {conversation_id(str): note} map, or {} if none saved yet."""
    path = _notes_path(instance_path)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_note(instance_path: str, conversation_id: int, text: str) -> None:
    """Persist a single chat's note, preserving notes for other chats."""
    notes = load_notes(instance_path)
    notes[str(conversation_id)] = text
    os.makedirs(instance_path, exist_ok=True)
    with open(_notes_path(instance_path), 'w', encoding='utf-8') as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# Markdown builder (pure)
# --------------------------------------------------------------------------

_ROLE_LABEL = {
    'guest': 'guest (Gast)',
    'owner': 'owner (Host)',
    'ai': 'ai (UMI)',
}


def _fmt(dt: Optional[datetime]) -> str:
    return dt.strftime('%Y-%m-%d %H:%M:%S') if isinstance(dt, datetime) else ''


def build_markdown(chats: List[Dict[str, Any]], generated_at: datetime) -> str:
    """Render playtest chat dicts into a Markdown review log.

    Each chat dict: id, guest_name, platform, escalated, escalated_at,
    created_at, messages[{sender_type, content, sent_at}], note, events.
    """
    lines: List[str] = []
    lines.append('# UMI Playtest Log')
    lines.append('')
    lines.append(f'_Generated: {_fmt(generated_at)} — {len(chats)} playtest chat(s)._')
    lines.append('')
    lines.append('> Events are best-effort (in-memory; lost on server restart). '
                 'Transcript, escalation flag and notes are durable.')
    lines.append('')

    if not chats:
        lines.append('No playtest conversations found.')
        lines.append('')
        return '\n'.join(lines)

    for chat in chats:
        flag = ' — **[ESCALATED]**' if chat.get('escalated') else ''
        lines.append(f"## Chat #{chat.get('id')} — {chat.get('guest_name', 'Unknown')}{flag}")
        lines.append('')
        meta = [f"created: {_fmt(chat.get('created_at'))}"]
        if chat.get('escalated'):
            meta.append(f"escalated_at: {_fmt(chat.get('escalated_at'))}")
        lines.append('`' + ' | '.join(meta) + '`')
        lines.append('')

        note = (chat.get('note') or '').strip()
        if note:
            lines.append(f'> **Notiz:** {note}')
            lines.append('')

        lines.append('### Transcript')
        lines.append('')
        for msg in chat.get('messages', []):
            role = _ROLE_LABEL.get(msg.get('sender_type'), msg.get('sender_type', '?'))
            ts = _fmt(msg.get('sent_at'))
            content = (msg.get('content') or '').strip()
            lines.append(f'- **[{role}]** _{ts}_')
            for ln in content.splitlines() or ['']:
                lines.append(f'  {ln}')
        lines.append('')

        events = chat.get('events') or []
        if events:
            lines.append('### Pipeline events')
            lines.append('')
            lines.append('```')
            for ev in events:
                etype = ev.get('event_type', '?')
                detail = ev.get('detail', '')
                lines.append(f'{etype}: {detail}')
            lines.append('```')
            lines.append('')

        lines.append('---')
        lines.append('')

    return '\n'.join(lines)


# --------------------------------------------------------------------------
# DB -> Markdown export
# --------------------------------------------------------------------------

def export_playtest_log(app) -> Dict[str, Any]:
    """Gather all playtest conversations and write PLAYTEST_LOG.md.

    Returns {success, path, count}. Must be called within an app context.
    """
    from ..models import Conversation, Message
    from .playtest_events import get_events

    notes = load_notes(app.instance_path)

    conversations = Conversation.query.filter_by(platform='playtest') \
        .order_by(Conversation.created_at.asc()).all()

    chats: List[Dict[str, Any]] = []
    for conv in conversations:
        messages = Message.query.filter_by(conversation_id=conv.id) \
            .order_by(Message.sent_at.asc()).all()
        events, _ = get_events(conv.id, 0)
        chats.append({
            'id': conv.id,
            'guest_name': (conv.guest.name if conv.guest else None) or 'Unknown',
            'platform': conv.platform,
            'escalated': conv.escalated,
            'escalated_at': conv.escalated_at,
            'created_at': conv.created_at,
            'messages': [
                {'sender_type': m.sender_type, 'content': m.content, 'sent_at': m.sent_at}
                for m in messages
            ],
            'note': notes.get(str(conv.id), ''),
            'events': events,
        })

    md = build_markdown(chats, generated_at=datetime.utcnow())
    path = os.path.join(_PACKAGE_ROOT, LOG_FILENAME)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(md)

    return {'success': True, 'path': path, 'count': len(chats)}
