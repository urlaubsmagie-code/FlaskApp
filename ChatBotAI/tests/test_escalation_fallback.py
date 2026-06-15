"""Tests for the broadened escalation *safety net*
(``MessageRouter._is_escalation_response``).

The model is instructed to end an escalation with the ``[[ESCALATE: reason]]``
marker, but it sometimes writes the holding message and silently drops the
marker (observed 2026-06-12: a "…melde mich gleich bei dir" reply that never
escalated). The phrase fallback is the deterministic backstop.

The old fallback only caught 'kollegen'/'kollegin'/'colleague' — but the
prompt's OWN canonical holding line is "Das kläre ich kurz mit dem Team und
melde mich gleich", which contains none of those. These tests pin the broadened
backstop AND guard the false positives (sign-off "Team Urlaubsmagie", the guest
being invited to reach out, plain factual answers).
"""

import pytest

from ChatBotAI.services.message_router import MessageRouter

is_esc = MessageRouter._is_escalation_response


# --------------------------------------------------------------------------
# Should escalate — holding / follow-up promises (the model couldn't answer)
# --------------------------------------------------------------------------

ESCALATING = [
    "Ich frage kurz bei meinen Kollegen nach.",                       # legacy trigger kept
    "Das kläre ich kurz mit dem Team und melde mich gleich bei dir.", # prompt's canonical example
    "melde mich gleich bei dir",                                      # the exact 2026-06-12 leak
    "Klar, ich schaue mal, welche schönen Spazierwege es rund um "
    "Sebnitz gibt und melde mich gleich bei dir.",                    # the real playtest reply
    "Wir melden uns kurz dazu.",                                      # vague reassurance variant
    "Da komme ich gleich darauf zurück.",                            # darauf zurück
    "I'll get back to you shortly.",                                  # English
    "Let me come back to you on that.",                               # English
    "I'll check with the team and let you know.",                     # English coordination
    "Lo consulto con el equipo y te aviso enseguida.",                # Spanish
]


@pytest.mark.parametrize("text", ESCALATING)
def test_holding_messages_escalate(text):
    assert is_esc(text) is True, text


# --------------------------------------------------------------------------
# Should NOT escalate — answers, sign-offs, guest-invitations
# --------------------------------------------------------------------------

NOT_ESCALATING = [
    "Das WLAN-Passwort ist urlaubsmagie2026.",                        # plain answer
    "Ja, das Leitungswasser kannst du bedenkenlos trinken.",          # plain answer
    "Liebe Grüße, Elena, Imke, Anna-Lena, und Sebastian - "
    "Team Urlaubsmagie",                                              # sign-off mentions "Team"
    "Melde dich gerne, wenn du noch Fragen hast!",                    # GUEST reaches out (du, not mich)
    "Sag mir einfach Bescheid, wenn du etwas brauchst.",              # guest tells us
    "Der Check-in ist ab 15:00 Uhr.",                                 # plain answer
]


@pytest.mark.parametrize("text", NOT_ESCALATING)
def test_normal_replies_do_not_escalate(text):
    assert is_esc(text) is False, text


def test_empty_is_safe():
    assert is_esc("") is False
    assert is_esc(None) is False
