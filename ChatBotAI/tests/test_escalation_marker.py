"""Unit tests for the [[ESCALATE: reason]] control-marker parser and the
phrase-based escalation fallback."""

from ChatBotAI.services.ai_service import AIService
from ChatBotAI.services.message_router import MessageRouter


def test_extracts_reason_and_strips_marker():
    txt = "Das kläre ich kurz mit dem Team und melde mich gleich.\n[[ESCALATE: money]]"
    clean, reason = AIService.parse_escalation(txt)
    assert reason == "money"
    assert "ESCALATE" not in clean
    assert clean == "Das kläre ich kurz mit dem Team und melde mich gleich."


def test_no_marker_returns_none_and_unchanged_text():
    txt = "Das WLAN-Passwort ist urlaubsmagie2026."
    clean, reason = AIService.parse_escalation(txt)
    assert reason is None
    assert clean == txt


def test_marker_is_case_and_spacing_tolerant():
    for raw in ["[[escalate:safety]]", "[[ ESCALATE : safety ]]", "[[ESCALATE safety]]"]:
        clean, reason = AIService.parse_escalation("Hallo.\n" + raw)
        assert reason == "safety", raw
        assert "[[" not in clean, raw


def test_empty_or_unknown_reason_normalises():
    clean, reason = AIService.parse_escalation("Text.\n[[ESCALATE:]]")
    assert reason == "unspecified"
    assert clean == "Text."


def test_none_input_is_safe():
    assert AIService.parse_escalation(None) == (None, None)


def test_phrase_fallback_still_detects_kollegen():
    assert MessageRouter._is_escalation_response("Ich frage kurz bei meinen Kollegen nach.") is True
    assert MessageRouter._is_escalation_response("Das WLAN-Passwort ist urlaubsmagie2026.") is False
