from ChatBotAI.services.ai_service import AIService


def test_prompt_instructs_german(monkeypatch):
    # Build an instance without __init__ (no network); set only what the method reads.
    svc = AIService.__new__(AIService)
    svc.timeout = 30
    svc.model = 'test-model'
    captured = {}

    # extract_knowledge_from_message calls self.generate_response(prompt, system=system, ...)
    def fake_generate(prompt, system=None, **kwargs):
        captured['system'] = system or ''
        captured['prompt'] = prompt
        return '[]'
    monkeypatch.setattr(svc, 'generate_response', fake_generate)

    svc.extract_knowledge_from_message('The trash goes out on Tuesday')
    blob = (captured['system'] + captured['prompt']).lower()
    assert 'german' in blob or 'deutsch' in blob
