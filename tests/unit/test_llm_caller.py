import asyncio

import httpx
import openai

from pageindex.core.utils import llm_caller


class _NoOpLimiter:
    def wait(self):
        return None

    async def wait_async(self):
        return None


def _install_stubs(monkeypatch, client):
    monkeypatch.setattr(llm_caller, "get_active_llm_client", lambda: client)
    monkeypatch.setattr(llm_caller, "get_rate_limiter", lambda: _NoOpLimiter())
    monkeypatch.setattr(llm_caller, "resolve_model_name", lambda name: name)
    monkeypatch.setattr(llm_caller.time, "sleep", lambda _: None)


def _bad_request():
    return openai.BadRequestError(
        message="bad image",
        response=httpx.Response(status_code=400, request=httpx.Request("POST", "http://example.com")),
        body=None,
    )


def _server_error():
    return openai.InternalServerError(
        message="boom",
        response=httpx.Response(status_code=500, request=httpx.Request("POST", "http://example.com")),
        body=None,
    )


class _CountingClient:
    def __init__(self, exc):
        self.exc = exc
        self.calls = 0

    def generate_text(self, **kwargs):
        del kwargs
        self.calls += 1
        raise self.exc

    def generate_text_with_finish_reason(self, **kwargs):
        del kwargs
        self.calls += 1
        raise self.exc

    async def generate_text_async(self, **kwargs):
        del kwargs
        self.calls += 1
        raise self.exc


def test_call_llm_fails_fast_on_bad_request(monkeypatch):
    client = _CountingClient(_bad_request())
    _install_stubs(monkeypatch, client)

    result = llm_caller.call_llm("m", "p")

    assert result == "Error"
    assert client.calls == 1


def test_call_llm_retries_on_server_error(monkeypatch):
    client = _CountingClient(_server_error())
    _install_stubs(monkeypatch, client)

    result = llm_caller.call_llm("m", "p")

    assert result == "Error"
    assert client.calls == llm_caller.MAX_RETRIES


def test_call_llm_with_finish_reason_fails_fast_on_bad_request(monkeypatch):
    client = _CountingClient(_bad_request())
    _install_stubs(monkeypatch, client)

    result = llm_caller.call_llm_with_finish_reason("m", "p")

    assert result == ("Error", "non_retryable")
    assert client.calls == 1


def test_call_llm_async_fails_fast_on_bad_request(monkeypatch):
    client = _CountingClient(_bad_request())
    _install_stubs(monkeypatch, client)

    async def _no_sleep(_):
        return None

    monkeypatch.setattr(llm_caller.asyncio, "sleep", _no_sleep)

    result = asyncio.run(llm_caller.call_llm_async("m", "p"))

    assert result == "Error"
    assert client.calls == 1
