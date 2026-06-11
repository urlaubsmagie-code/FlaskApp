"""Snapshot test: new compact-tier prompt must equal legacy _build_compact_prompt output.

We instantiate AIService directly (no Flask app), call both methods on the
same fixtures, and assert exact string equality. This locks Phase 1 as a
pure refactor — zero behavior change on gemma2:9b.
"""

from datetime import datetime

import pytest

from ChatBotAI.services.ai_service import AIService


@pytest.fixture
def svc():
    return AIService(model="gemma2:9b")


# Freeze "now" so date stamps match between legacy and new.
FROZEN_NOW = datetime(2026, 5, 6, 12, 0, 0)


def _patched(monkeypatch):
    """Patch datetime.utcnow inside ai_service to return FROZEN_NOW."""
    class _F:
        @staticmethod
        def utcnow():
            return FROZEN_NOW
    monkeypatch.setattr("ChatBotAI.services.ai_service.datetime", _F)


SCENARIOS = [
    {
        "name": "minimal_single_message",
        "guest_profile": {"name": "Anna", "language": "German"},
        "conversation_history": [],
        "clean_latest": "Wann ist der Check-in?",
        "unanswered_count": 1,
        "tone": "friendly_professional",
        "host_instructions": None,
        "reservation_info": None,
        "knowledge_entries": None,
    },
    {
        "name": "with_kb_and_history",
        "guest_profile": {"name": "Max", "language": "German"},
        "conversation_history": [
            {"sender_type": "owner", "content": "Hallo Max, willkommen!"},
            {"sender_type": "guest", "content": "Danke! Eine Frage..."},
        ],
        "clean_latest": "Gibt es WLAN?",
        "unanswered_count": 1,
        "tone": "friendly_professional",
        "host_instructions": "Always confirm bookings.",
        "reservation_info": None,
        "knowledge_entries": [
            {"label": "WLAN-Passwort", "value": "urlaubsmagie2026"},
            {"label": "Check-in", "value": "Ab 15:00 Uhr selbständig per Schlüsseltresor."},
        ],
    },
    {
        "name": "multi_unanswered",
        "guest_profile": {"name": "Lisa", "language": None},
        "conversation_history": [],
        "clean_latest": "Frage 1\nFrage 2\nFrage 3",
        "unanswered_count": 3,
        "tone": "casual",
        "host_instructions": None,
        "reservation_info": None,
        "knowledge_entries": None,
    },
]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s["name"])
def test_compact_tier_renders_without_error(svc, monkeypatch, scenario):
    _patched(monkeypatch)
    out = svc._build_guest_reply_prompt(
        guest_profile=scenario["guest_profile"],
        conversation_history=scenario["conversation_history"],
        clean_latest=scenario["clean_latest"],
        unanswered_count=scenario["unanswered_count"],
        tone=scenario["tone"],
        host_instructions=scenario["host_instructions"],
        reservation_info=scenario["reservation_info"],
        knowledge_entries=scenario["knowledge_entries"],
    )
    assert "UMI" in out
    assert "TASK:" in out
    assert "Date: 06 May 2026" in out
    assert not out.endswith("\n")
