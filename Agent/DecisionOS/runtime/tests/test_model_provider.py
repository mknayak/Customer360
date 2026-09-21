import json

from decision_os.model_provider import ModelRequest, OpenAICompatibleModelProvider


def test_openai_compatible_provider_builds_bounded_chat_request(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "grounded answer"}}]}).encode()

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("decision_os.model_provider.urlopen", fake_urlopen)
    provider = OpenAICompatibleModelProvider("https://llm.example", "secret", "test-model", 3)
    response = provider.complete(ModelRequest("Why?", ("[e1] evidence",), ("rag.search",)))
    assert response.text == "grounded answer"
    assert captured["url"] == "https://llm.example/v1/chat/completions"
    assert captured["body"]["model"] == "test-model"
    assert captured["timeout"] == 3


def test_openai_compatible_provider_does_not_duplicate_v1_path(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"ok"}}]}'

    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        return Response()

    monkeypatch.setattr("decision_os.model_provider.urlopen", fake_urlopen)
    OpenAICompatibleModelProvider("https://llm.example/v1/", "secret", "test-model").complete(ModelRequest("Why?"))
    assert captured["url"] == "https://llm.example/v1/chat/completions"
