"""Cloud models run in parallel; local models stay serialized (GPU safety)."""
import threading
import time

from ChatBotAI.services.ai_service import AIService


class _FakeResp:
    status_code = 200

    def json(self):
        return {'message': {'content': 'ok'}, 'eval_count': 1}


def _run_concurrent(model, monkeypatch, n=3, delay=0.3):
    """Fire n _call_chat_api calls at once; return wall-clock seconds."""
    svc = AIService(model=model, timeout=30)

    def fake_post(*a, **k):
        time.sleep(delay)          # simulate the model round-trip
        return _FakeResp()

    import ChatBotAI.services.ai_service as mod
    monkeypatch.setattr(mod.requests, 'post', fake_post)

    threads = [threading.Thread(target=lambda: svc._call_chat_api([{'role': 'user', 'content': 'hi'}]))
               for _ in range(n)]
    t0 = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return time.monotonic() - t0


def test_cloud_model_calls_run_in_parallel(monkeypatch):
    # 3 calls x 0.3s each. Parallel → ~0.3s, not ~0.9s.
    wall = _run_concurrent('gpt-oss:120b-cloud', monkeypatch, n=3, delay=0.3)
    assert wall < 0.6, f"cloud calls serialized ({wall:.2f}s) — should overlap"


def test_local_model_calls_are_serialized(monkeypatch):
    # Same load, local model → the GPU lock forces ~0.9s.
    wall = _run_concurrent('gemma2:9b', monkeypatch, n=3, delay=0.3)
    assert wall >= 0.85, f"local calls overlapped ({wall:.2f}s) — GPU lock not held"


def test_cloud_models_get_bounded_thinking(monkeypatch):
    # Unbounded thinking on glm/kimi ate the whole num_predict → empty reply.
    sent = {}

    def fake_post(url, json=None, **k):
        sent['payload'] = json
        return _FakeResp()

    import ChatBotAI.services.ai_service as mod
    monkeypatch.setattr(mod.requests, 'post', fake_post)
    msgs = [{'role': 'user', 'content': 'hi'}]

    AIService(model='glm-5.3-flash:cloud', timeout=30)._call_chat_api(msgs)
    assert sent['payload']['think'] == 'medium'

    AIService(model='gemma2:9b', timeout=30)._call_chat_api(msgs)  # local models 400 on 'think'
    assert 'think' not in sent['payload']


def test_is_cloud_model_detection():
    assert AIService._is_cloud_model('gpt-oss:120b-cloud')
    assert not AIService._is_cloud_model('gemma2:9b')
    assert not AIService._is_cloud_model(None)
