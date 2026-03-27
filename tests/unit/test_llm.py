import asyncio
from types import SimpleNamespace

from pageindex.infrastructure.llm import AnthropicLLMClient, LLMProviderFactory, OpenAICompatibleLLMClient
from pageindex.infrastructure.settings import LLMSettings


_FAKE_RESPONSE = SimpleNamespace(
    choices=[SimpleNamespace(message=SimpleNamespace(content="hello"), finish_reason="stop")]
)
_FAKE_ANTHROPIC_RESPONSE = SimpleNamespace(
    content=[SimpleNamespace(type="text", text="hello")],
    stop_reason="end_turn",
)
_LAST_OPENAI_CREATE_KWARGS = {}


class _FakeCompletions:
    def create(self, **kwargs):
        global _LAST_OPENAI_CREATE_KWARGS
        _LAST_OPENAI_CREATE_KWARGS = dict(kwargs)
        return _FAKE_RESPONSE


class _FakeAsyncCompletions:
    async def create(self, **kwargs):
        global _LAST_OPENAI_CREATE_KWARGS
        _LAST_OPENAI_CREATE_KWARGS = dict(kwargs)
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


class _FakeAnthropicMessages:
    def create(self, model, max_tokens, messages, temperature):
        del model, max_tokens, messages, temperature
        return _FAKE_ANTHROPIC_RESPONSE


class _FakeAsyncAnthropicMessages:
    async def create(self, model, max_tokens, messages, temperature):
        del model, max_tokens, messages, temperature
        return _FAKE_ANTHROPIC_RESPONSE


class _FakeAnthropicClient:
    def __init__(self, *args, **kwargs):
        del args, kwargs
        self.messages = _FakeAnthropicMessages()


class _FakeAsyncAnthropicClient:
    def __init__(self, *args, **kwargs):
        del args, kwargs
        self.messages = _FakeAsyncAnthropicMessages()

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


def test_openai_compatible_client_passes_provider_request_kwargs(monkeypatch):
    monkeypatch.setattr("pageindex.infrastructure.llm.openai.OpenAI", _FakeSyncClient)

    client = LLMProviderFactory.create(
        LLMSettings(
            provider="vllm",
            openai_compatible_api_key="test-key",
            openai_compatible_base_url="http://localhost:8000/v1",
            openai_compatible_request_kwargs={
                "chat_template_kwargs": {"enable_thinking": False},
                "stream": False,
            },
        )
    )

    assert client.generate_text("Qwen3.5-35B-A3B", "hello") == "hello"
    assert _LAST_OPENAI_CREATE_KWARGS["stream"] is False
    assert _LAST_OPENAI_CREATE_KWARGS["temperature"] == 0
    assert _LAST_OPENAI_CREATE_KWARGS["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": False},
    }


def test_openai_compatible_client_supports_multimodal_content(monkeypatch):
    monkeypatch.setattr("pageindex.infrastructure.llm.openai.OpenAI", _FakeSyncClient)

    client = LLMProviderFactory.create(_settings())
    content = [
        {"type": "text", "text": "describe"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abcd"}},
    ]

    assert client.generate_text_from_content("gpt-test", content) == "hello"
    assert _LAST_OPENAI_CREATE_KWARGS["messages"] == [{"role": "user", "content": content}]


def test_openai_compatible_json_response_overrides_provider_response_format(monkeypatch):
    monkeypatch.setattr("pageindex.infrastructure.llm.openai.OpenAI", _FakeSyncClient)

    client = LLMProviderFactory.create(
        LLMSettings(
            provider="vllm",
            openai_compatible_api_key="test-key",
            openai_compatible_request_kwargs={"response_format": {"type": "text"}},
        )
    )

    assert client.generate_text("Qwen3.5-35B-A3B", "hello", json_response=True) == "hello"
    assert _LAST_OPENAI_CREATE_KWARGS["response_format"] == {"type": "json_object"}


def test_anthropic_client_uses_factory(monkeypatch):
    monkeypatch.setattr("pageindex.infrastructure.llm.client.anthropic.Anthropic", _FakeAnthropicClient)

    client = LLMProviderFactory.create(
        LLMSettings(
            provider="anthropic",
            anthropic_api_key="anthropic-key",
            anthropic_base_url="http://anthropic.example.com",
        )
    )

    assert isinstance(client, AnthropicLLMClient)
    assert client.generate_text("claude-test", "hello") == "hello"


def test_anthropic_async_client_returns_response(monkeypatch):
    monkeypatch.setattr("pageindex.infrastructure.llm.client.anthropic.AsyncAnthropic", _FakeAsyncAnthropicClient)

    client = LLMProviderFactory.create(
        LLMSettings(
            provider="anthropic",
            anthropic_api_key="anthropic-key",
        )
    )

    assert asyncio.run(client.generate_text_async("claude-test", "hello")) == "hello"


def test_anthropic_finish_reason_maps_max_tokens(monkeypatch):
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="hello")],
        stop_reason="max_tokens",
    )

    class _MaxTokensMessages:
        def create(self, model, max_tokens, messages, temperature):
            del model, max_tokens, messages, temperature
            return response

    class _MaxTokensClient:
        def __init__(self, *args, **kwargs):
            del args, kwargs
            self.messages = _MaxTokensMessages()

    monkeypatch.setattr("pageindex.infrastructure.llm.client.anthropic.Anthropic", _MaxTokensClient)

    client = LLMProviderFactory.create(
        LLMSettings(
            provider="anthropic",
            anthropic_api_key="anthropic-key",
        )
    )

    assert client.generate_text_with_finish_reason("claude-test", "hello") == ("hello", "max_output_reached")


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


def test_factory_raises_when_anthropic_api_key_missing():
    try:
        LLMProviderFactory.create(LLMSettings(provider="anthropic"))
        assert False, "expected missing API key"
    except ValueError as exc:
        assert "Missing API key" in str(exc)
