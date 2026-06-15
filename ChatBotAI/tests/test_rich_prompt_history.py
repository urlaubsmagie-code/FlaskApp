"""Rich-tier prompt must include the full two-sided conversation history
(option "C") so the cloud model is aware of what was already said.

Compact tier (small local models like gemma2:9b) stays slim — only the last
couple of host/AI replies — to keep small models focused on the current
message. So the same earlier GUEST line appears in rich but not in compact.
"""

from ChatBotAI.services.ai_service import AIService

HISTORY = [
    {'sender_type': 'guest', 'content': 'Wo ist der Busbahnhof?'},
    {'sender_type': 'ai', 'content': 'Das kläre ich kurz mit dem Team und melde mich.'},
]
LATEST = 'Welche Buslinie fährt nach Bad Schandau?'


def _render(model):
    svc = AIService(model=model)
    return svc._build_guest_reply_prompt(
        guest_profile={'name': 'Mario', 'language': 'German'},
        conversation_history=HISTORY,
        clean_latest=LATEST,
        unanswered_count=1,
        tone='friendly_professional',
        host_instructions=None,
        reservation_info=None,
        knowledge_entries=None,
    )


def test_rich_prompt_includes_earlier_guest_message():
    out = _render('gpt-oss:120b-cloud')
    # The earlier GUEST turn must be present — proves two-sided history.
    assert 'Wo ist der Busbahnhof?' in out
    # And UMI's own earlier reply too.
    assert 'Das kläre ich kurz mit dem Team' in out


def test_compact_prompt_omits_earlier_guest_message():
    out = _render('gemma2:9b')
    # Compact stays slim: the earlier GUEST line is NOT injected...
    assert 'Wo ist der Busbahnhof?' not in out
    # ...but UMI's recent host reply still is.
    assert 'Das kläre ich kurz mit dem Team' in out
