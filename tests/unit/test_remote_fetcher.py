import asyncio

import httpx

from pageindex.core.services.task_service import RemoteFileFetcher
from pageindex.messages.models import RemoteFileReference


def test_remote_file_fetcher_downloads_content():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Test"] == "1"
        return httpx.Response(
            200,
            headers={"content-disposition": 'attachment; filename="hello.md"'},
            content=b"# Hello\nworld",
        )

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    httpx.AsyncClient = _Client
    try:
        fetcher = RemoteFileFetcher(timeout_seconds=1)
        result = asyncio.run(
            fetcher.fetch(
                RemoteFileReference(url="https://example.com/remote.md", headers={"X-Test": "1"})
            )
        )
    finally:
        httpx.AsyncClient = original

    assert result.original_name == "hello.md"
    assert result.content == b"# Hello\nworld"


def test_remote_file_fetcher_falls_back_to_url_name():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"hello")

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    httpx.AsyncClient = _Client
    try:
        fetcher = RemoteFileFetcher(timeout_seconds=1)
        result = asyncio.run(fetcher.fetch(RemoteFileReference(url="https://example.com/path/report.pdf", headers={})))
    finally:
        httpx.AsyncClient = original

    assert result.original_name == "report.pdf"


def test_remote_file_fetcher_raises_on_http_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "missing"})

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    httpx.AsyncClient = _Client
    try:
        fetcher = RemoteFileFetcher(timeout_seconds=1)
        try:
            asyncio.run(fetcher.fetch(RemoteFileReference(url="https://example.com/missing.md", headers={})))
            assert False, "expected HTTPStatusError"
        except httpx.HTTPStatusError:
            pass
    finally:
        httpx.AsyncClient = original
