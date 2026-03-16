import asyncio
from types import SimpleNamespace

from pageindex.infrastructure.llm import LLMProviderFactory, OpenAICompatibleLLMClient
from pageindex.infrastructure.settings import LLMSettings


_FAKE_RESPONSE = SimpleNamespace(
    choices=[SimpleNamespace(message=SimpleNamespace(content="hello"), finish_reason="stop")]
)


class _FakeCompletions:
    def create(self, model, messages, temperature):
        del model, messages, temperature
        return _FAKE_RESPONSE


class _FakeAsyncCompletions:
    async def create(self, model, messages, temperature):
        del model, messages, temperature
        return _FAKE_RESPONSE


class _FakeSyncClient:
    def __init__(self, *args, **kwargs):
        del args, kwargs
        self.chat = SimpleNamespace(completions=_FakeCompletions())


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        del args, kwargs
        self.chat = SimpleNamespace(completions=_FakeAsyncCompletions())

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb


def _settings(provider="openai_compatible", api_key="test-key", base_url="http://example.com"):
    return LLMSettings(
        provider=provider,
        openai_compatible_api_key=api_key,
        openai_compatible_base_url=base_url,
    )


def test_openai_compatible_client_uses_factory(monkeypatch):
    monkeypatch.setattr("pageindex.infrastructure.llm.openai.OpenAI", _FakeSyncClient)
    monkeypatch.setattr("pageindex.infrastructure.llm.openai.AsyncOpenAI", _FakeAsyncClient)

    client = LLMProviderFactory.create(_settings())

    assert isinstance(client, OpenAICompatibleLLMClient)
    assert client.generate_text("gpt-test", "hello") == "hello"


def test_openai_compatible_client_keeps_chat_history_immutable(monkeypatch):
    monkeypatch.setattr("pageindex.infrastructure.llm.openai.OpenAI", _FakeSyncClient)

    client = LLMProviderFactory.create(_settings())
    history = [{"role": "system", "content": "stay"}]

    client.generate_text("gpt-test", "hello", chat_history=history)

    assert history == [{"role": "system", "content": "stay"}]


def test_openai_compatible_async_client_returns_response(monkeypatch):
    monkeypatch.setattr("pageindex.infrastructure.llm.openai.AsyncOpenAI", _FakeAsyncClient)

    client = LLMProviderFactory.create(_settings())

    assert asyncio.run(client.generate_text_async("gpt-test", "hello")) == "hello"


def test_factory_raises_for_unsupported_provider():
    try:
        LLMProviderFactory.create(LLMSettings(provider="unsupported"))
        assert False, "expected unsupported provider"
    except ValueError as exc:
        assert "Unsupported provider" in str(exc)


def test_factory_raises_when_api_key_missing():
    try:
        LLMProviderFactory.create(LLMSettings(provider="openai_compatible"))
        assert False, "expected missing API key"
    except ValueError as exc:
        assert "Missing API key" in str(exc)
