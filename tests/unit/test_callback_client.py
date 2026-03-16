import asyncio
import json

import httpx

from pageindex.core.services.task_service import CallbackClient
from pageindex.messages.models import CallbackTarget


def test_callback_client_posts_payload():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    httpx.AsyncClient = _Client
    try:
        client = CallbackClient(timeout_seconds=1, retry_count=1)
        asyncio.run(
            client.send(
                CallbackTarget(url="https://omnix.local/callback", headers={"Authorization": "Bearer token"}),
                {"task_id": "task-1", "status": "completed"},
            )
        )
    finally:
        httpx.AsyncClient = original

    assert captured["headers"]["authorization"] == "Bearer token"
    assert json.loads(captured["body"])["task_id"] == "task-1"


def test_callback_client_retries_until_success():
    attempts = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(500, json={"error": "retry"})
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    httpx.AsyncClient = _Client
    try:
        client = CallbackClient(timeout_seconds=1, retry_count=3)
        asyncio.run(
            client.send(
                CallbackTarget(url="https://omnix.local/callback", headers={}),
                {"task_id": "task-1", "status": "completed"},
            )
        )
    finally:
        httpx.AsyncClient = original

    assert attempts["count"] == 3


def test_callback_client_raises_after_retries_exhausted():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "still failing"})

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    httpx.AsyncClient = _Client
    try:
        client = CallbackClient(timeout_seconds=1, retry_count=2)
        try:
            asyncio.run(
                client.send(
                    CallbackTarget(url="https://omnix.local/callback", headers={}),
                    {"task_id": "task-1", "status": "completed"},
                )
            )
            assert False, "expected retry exhaustion"
        except httpx.HTTPStatusError:
            pass
    finally:
        httpx.AsyncClient = original
