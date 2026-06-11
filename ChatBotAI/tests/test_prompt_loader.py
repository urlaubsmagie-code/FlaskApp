"""Smoke tests for prompt_loader. Verifies templates exist and render."""

from ChatBotAI.services.prompt_loader import load_prompt, list_available_tones


def test_shared_blocks_load():
    """Shared blocks render as plain strings (no template syntax in them today)."""
    out = load_prompt("core_identity", tier="shared")
    assert "UMI" in out
    assert "Urlaubsmagie" in out

    out = load_prompt("language_rule", tier="shared")
    assert "guest's language" in out
    assert "German quality" in out


def test_tone_files_load():
    for tone in ["friendly_professional", "formal", "casual", "concise"]:
        out = load_prompt(tone, tier="shared/tone")
        assert out.strip(), f"tone file {tone} is empty"


def test_list_available_tones_returns_four():
    tones = list_available_tones()
    assert set(tones) == {"friendly_professional", "formal", "casual", "concise"}


def test_rich_guest_reply_renders():
    out = load_prompt(
        "guest_reply",
        tier="rich",
        tone_instruction="Be warm.",
        now_str="06 May 2026",
        guest_name="Max",
        guest_language="German",
        reservation_compact=None,
        host_instructions=None,
        knowledge_entries=None,
        recent_host_replies=None,
        unanswered_count=1,
        task_text="Hallo!",
        guest_profile={"name": "Max"},
    )
    assert "UMI" in out
    assert "Du always" in out
    assert "Sign-off rule" in out
    assert "06 May 2026" in out
