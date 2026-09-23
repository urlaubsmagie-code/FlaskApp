"""Per-message suggest (the lightbulb) is unified onto the hardened rich prompt.

Previously the lightbulb used a separate legacy prompt builder that never got
the anti-hallucination hardening or the [[ESCALATE]] marker, and was told to
"ignore everything else in the conversation". After unification it uses the
same tier-aware template as every other path, with a "reply to THIS specific
message" task variant — so it gets the hardening, the full conversation as
context, and (rich tier) the restored corrections/summary/resolved blocks.

Compact tier stays slim: it gets the target-message task but NOT the
corrections/summary/resolved blocks.
"""

from ChatBotAI.services.ai_service import AIService

HISTORY = [
    {'sender_type': 'guest', 'content': 'Wo ist der Busbahnhof?'},
    {'sender_type': 'ai', 'content': 'Das kläre ich kurz mit dem Team.'},
    {'sender_type': 'guest', 'content': 'Welche Buslinie fährt nach Bad Schandau?'},
]


def _prompt(model, **kw):
    svc = AIService(model=model)
    base = dict(
        guest_profile={'name': 'Mario', 'language': 'German'},
        conversation_history=HISTORY,
        clean_latest='Welche Buslinie fährt nach Bad Schandau?',
        unanswered_count=1,
        tone='friendly_professional',
        host_instructions=None,
        reservation_info=None,
        knowledge_entries=None,
    )
    base.update(kw)
    return svc._build_guest_reply_prompt(**base)


# --- target-message task variant -----------------------------------------

def test_rich_targets_the_specific_message_and_is_hardened():
    out = _prompt('gpt-oss:120b-cloud', target_message_override='Wo ist der Busbahnhof?')
    # Targets the chosen (older) message
    assert 'Wo ist der Busbahnhof?' in out
    # Carries the hardening (escalate marker contract) — the legacy path did NOT
    assert '[[ESCALATE' in out
    # Still has the rest of the conversation as context
    assert 'Bad Schandau' in out


def test_compact_targets_message_too():
    out = _prompt('gemma2:9b', target_message_override='Wo ist der Busbahnhof?')
    assert 'Wo ist der Busbahnhof?' in out
    assert '[[ESCALATE' in out.upper() or '[[escalate' in out


# --- restored context (rich only) -----------------------------------------

CORRECTIONS = [{'label': 'Parken', 'value': 'FALSCH: kostenlos\nRICHTIG: 10€ pro Nacht'}]


def test_rich_restores_corrections():
    out = _prompt('gpt-oss:120b-cloud', corrections=CORRECTIONS)
    assert 'never repeat a mistake' in out
    assert 'Parken' in out


def test_rich_restores_summary_and_resolved():
    out = _prompt(
        'gpt-oss:120b-cloud',
        conversation_summary='Gast hat nach Check-in gefragt.',
        resolved_topics=['Check-in Zeit', 'WLAN-Passwort'],
    )
    assert 'Gast hat nach Check-in gefragt.' in out
    assert 'Check-in Zeit' in out


def test_compact_stays_slim_no_corrections():
    out = _prompt('gemma2:9b', corrections=CORRECTIONS,
                  conversation_summary='irgendwas', resolved_topics=['X'])
    assert 'Past corrections' not in out
    assert 'Parken' not in out
