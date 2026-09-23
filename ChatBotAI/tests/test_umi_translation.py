import json
import pytest

from ChatBotAI.services.ai_service import AIService
from ChatBotAI import routes


def test_translation_uses_only_selected_text_and_short_prompt(monkeypatch):
    ai = AIService(model='kimi-k3:cloud')
    captured = {}
    def call(messages, **kwargs):
        captured.update(messages=messages, **kwargs)
        return json.dumps({'translation': 'Wo ist der Schlüssel?'})
    monkeypatch.setattr(ai, '_call_chat_api', call)
    assert ai.translate_message('Где ключ?') == 'Wo ist der Schlüssel?'
    assert len(captured['messages']) == 2
    assert captured['messages'][1] == {'role': 'user', 'content': 'Где ключ?'}
    assert 'German' in captured['messages'][0]['content']
    assert captured['timeout'] == 60
    assert captured['translation'] is True
    ai.translate_message('Hallo', 'en')
    assert 'English' in captured['messages'][0]['content']


@pytest.mark.parametrize('response', [None, '', 'Here is the translation', '{}',
                                      '{"translation": ""}', '{"translation": 123}',
                                      '{"translation": "cut off', '[]'])
def test_invalid_model_output_is_not_shown_as_translation(monkeypatch, response):
    ai = AIService()
    monkeypatch.setattr(ai, '_call_chat_api', lambda *a, **kw: response)
    with pytest.raises(ValueError):
        ai.translate_message('Hello')


def test_chat_cache_uses_umi_and_does_not_cache_failures(monkeypatch):
    calls = []
    class AI:
        def translate_message(self, text, target):
            calls.append((text, target))
            if len(calls) == 1:
                raise ValueError('temporarily unavailable')
            return 'Hallo'
    monkeypatch.setattr(routes, 'get_ai_service', lambda: AI())
    routes._translate_cached.cache_clear()
    try:
        with pytest.raises(ValueError):
            routes._translate_cached('Hello', 'de')
        assert routes._translate_cached('Hello', 'de') == 'Hallo'
        assert routes._translate_cached('Hello', 'de') == 'Hallo'
        assert len(calls) == 2
    finally:
        routes._translate_cached.cache_clear()


def test_translation_payload_overrides_reply_settings_and_rejects_truncation(monkeypatch):
    from ChatBotAI.services import ai_service
    from ChatBotAI.models import AISettings
    ai = AIService(model='kimi-k3:cloud')
    captured = []
    monkeypatch.setattr(AISettings, 'get', lambda key: {
        'ai_temperature': '0.9', 'ai_max_tokens': '50', 'ai_reasoning_effort': 'high'
    }.get(key))
    class Response:
        status_code = 200
        def json(self):
            return {'message': {'content': '{"translation":"Hallo"}'},
                    'done_reason': 'length' if len(captured) > 1 else 'stop'}
    def post(url, json, timeout):
        captured.append(json)
        return Response()
    monkeypatch.setattr(ai_service.requests, 'post', post)
    assert ai.translate_message('Hello') == 'Hallo'
    assert captured[0]['format'] == 'json'
    assert captured[0]['think'] == 'low'
    assert captured[0]['options'] == {'temperature': 0, 'num_predict': 1024}
    with pytest.raises(ValueError):
        ai.translate_message('Hello')
