"""Knowledge extraction runs behind the Cloudflare tunnel (~100s HTTP cut). The
extraction AI call must use a timeout BELOW that limit, so a slow cloud model
returns a clean JSON error the UI can show/retry instead of a proxy 524 whose
non-JSON body breaks the client (observed: 'Wissensextraktion fehlgeschlagen')."""
from ChatBotAI.services.ai_service import AIService, KNOWLEDGE_EXTRACT_TIMEOUT_S


def test_extraction_timeout_is_capped_below_proxy_limit(monkeypatch):
    ai = AIService(timeout=120)  # base timeout deliberately ABOVE the 100s cut
    captured = {}

    def fake_generate(prompt, system=None, timeout=None, model=None):
        captured['timeout'] = timeout
        return '[]'  # valid empty JSON array

    monkeypatch.setattr(ai, 'generate_response', fake_generate)
    # reasoning_model normally reads AISettings (needs app+db); stub it out.
    monkeypatch.setattr(AIService, 'reasoning_model',
                        property(lambda self: 'test-model'))

    result = ai.extract_knowledge_from_message('Check-in ab 16 Uhr.')

    assert result == []
    assert captured['timeout'] == KNOWLEDGE_EXTRACT_TIMEOUT_S
    assert captured['timeout'] < 100, 'must be under the Cloudflare ~100s cut'


def test_cap_constant_is_below_cloudflare_limit():
    # Guard the invariant itself so a future bump above 100 is caught.
    assert KNOWLEDGE_EXTRACT_TIMEOUT_S < 100
