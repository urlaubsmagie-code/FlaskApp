import os
import pytest
from ChatBotAI.services.prompt_tier import detect_tier


@pytest.mark.parametrize("model_name,expected", [
    # Local small models → compact
    ("gemma2:9b", "compact"),
    ("qwen3:8b", "compact"),
    ("qwen3:14b", "compact"),
    ("mistral:7b-instruct", "compact"),
    ("llama3.2:3b", "compact"),
    # Cloud models → rich (cloud suffix wins regardless of size pattern)
    ("gpt-oss:120b-cloud", "rich"),
    ("kimi-k2:1t-cloud", "rich"),
    ("qwen3-coder:480b-cloud", "rich"),
    ("deepseek-v3.1:671b-cloud", "rich"),
    # Big local models (≥70B) → rich
    ("llama3.1:70b", "rich"),
    ("mistral:200b", "rich"),
    # Edge cases → compact (safe default)
    ("", "compact"),
    ("unknown-model", "compact"),
])
def test_detect_tier(model_name, expected):
    assert detect_tier(model_name) == expected


def test_detect_tier_handles_none():
    assert detect_tier(None) == "compact"


def test_detect_tier_is_case_insensitive():
    assert detect_tier("GPT-OSS:120B-CLOUD") == "rich"
    assert detect_tier("Gemma2:9B") == "compact"


def test_force_override_via_env(monkeypatch):
    monkeypatch.setenv("FORCE_PROMPT_TIER", "rich")
    assert detect_tier("gemma2:9b") == "rich"
    monkeypatch.setenv("FORCE_PROMPT_TIER", "compact")
    assert detect_tier("gpt-oss:120b-cloud") == "compact"


def test_force_override_invalid_value_is_ignored(monkeypatch):
    monkeypatch.setenv("FORCE_PROMPT_TIER", "invalid")
    # Falls back to normal detection
    assert detect_tier("gemma2:9b") == "compact"
    assert detect_tier("gpt-oss:120b-cloud") == "rich"
