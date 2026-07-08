"""Tests for the Chat Playtest export + per-chat notes.

The export turns the durable playtest record (Conversation + Messages +
escalated flag) plus the best-effort in-memory event log and the per-chat
note into a single readable Markdown file the team (and Claude) can review
after a playtest session.

``build_markdown`` is a pure function — given a list of chat dicts it returns
the Markdown string — so it is tested in isolation without a DB or AI.
Notes round-trip through a JSON sidecar in the instance folder.
"""

from datetime import datetime

from ChatBotAI.services import playtest_export


def _chat(**overrides):
    """A minimal chat dict with sensible defaults; override per test."""
    base = {
        'id': 42,
        'guest_name': 'Test Gast',
        'platform': 'playtest',
        'escalated': False,
        'escalated_at': None,
        'created_at': datetime(2026, 6, 12, 10, 0, 0),
        'messages': [
            {'sender_type': 'guest', 'content': 'Wie ist das WLAN-Passwort?',
             'sent_at': datetime(2026, 6, 12, 10, 0, 5)},
            {'sender_type': 'ai', 'content': 'Das WLAN-Passwort ist urlaubsmagie2026.',
             'sent_at': datetime(2026, 6, 12, 10, 0, 8)},
        ],
        'note': '',
        'events': [],
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# build_markdown
# --------------------------------------------------------------------------

def test_markdown_includes_transcript_with_sender_labels():
    md = playtest_export.build_markdown([_chat()], generated_at=datetime(2026, 6, 12, 11, 0, 0))
    assert 'Wie ist das WLAN-Passwort?' in md
    assert 'Das WLAN-Passwort ist urlaubsmagie2026.' in md
    # Sender roles must be distinguishable in the output
    assert 'guest' in md.lower()
    assert 'ai' in md.lower()


def test_markdown_header_reports_chat_count_and_timestamp():
    md = playtest_export.build_markdown(
        [_chat(id=1), _chat(id=2)],
        generated_at=datetime(2026, 6, 12, 11, 30, 0),
    )
    assert '2' in md  # two chats
    assert '2026-06-12' in md  # generated-at date appears


def test_markdown_flags_escalated_chats():
    escalated = _chat(id=7, escalated=True, escalated_at=datetime(2026, 6, 12, 10, 1, 0))
    md = playtest_export.build_markdown([escalated], generated_at=datetime(2026, 6, 12, 11, 0, 0))
    assert 'ESCALATED' in md.upper()


def test_markdown_does_not_flag_non_escalated_chats():
    md = playtest_export.build_markdown([_chat(escalated=False)], generated_at=datetime(2026, 6, 12, 11, 0, 0))
    assert 'ESCALATED' not in md.upper()


def test_markdown_includes_per_chat_note():
    noted = _chat(note='Antwort war erfunden -> sollte eskalieren')
    md = playtest_export.build_markdown([noted], generated_at=datetime(2026, 6, 12, 11, 0, 0))
    assert 'Antwort war erfunden -> sollte eskalieren' in md


def test_markdown_includes_events_when_present():
    chat = _chat(events=[
        {'event_type': 'escalation_check', 'detail': 'Escalation TRIGGERED (reason=money)',
         'timestamp': 1781000000.0},
        {'event_type': 'ai_response_generated', 'detail': 'AI response generated (40 chars)',
         'timestamp': 1781000001.0},
    ])
    md = playtest_export.build_markdown([chat], generated_at=datetime(2026, 6, 12, 11, 0, 0))
    assert 'escalation_check' in md
    assert 'Escalation TRIGGERED (reason=money)' in md
    assert 'ai_response_generated' in md


def test_markdown_handles_no_chats():
    md = playtest_export.build_markdown([], generated_at=datetime(2026, 6, 12, 11, 0, 0))
    # Should produce a valid document, not crash, and signal emptiness
    assert isinstance(md, str)
    assert '0' in md


# --------------------------------------------------------------------------
# notes sidecar (round-trip)
# --------------------------------------------------------------------------

def test_save_and_load_note_round_trip(tmp_path):
    playtest_export.save_note(str(tmp_path), 42, 'WiFi-Frage gut beantwortet')
    notes = playtest_export.load_notes(str(tmp_path))
    assert notes['42'] == 'WiFi-Frage gut beantwortet'


def test_save_note_overwrites_previous(tmp_path):
    playtest_export.save_note(str(tmp_path), 42, 'erste Notiz')
    playtest_export.save_note(str(tmp_path), 42, 'zweite Notiz')
    notes = playtest_export.load_notes(str(tmp_path))
    assert notes['42'] == 'zweite Notiz'


def test_save_note_keeps_other_chats(tmp_path):
    playtest_export.save_note(str(tmp_path), 1, 'Notiz eins')
    playtest_export.save_note(str(tmp_path), 2, 'Notiz zwei')
    notes = playtest_export.load_notes(str(tmp_path))
    assert notes['1'] == 'Notiz eins'
    assert notes['2'] == 'Notiz zwei'


def test_load_notes_on_missing_file_returns_empty(tmp_path):
    assert playtest_export.load_notes(str(tmp_path)) == {}
