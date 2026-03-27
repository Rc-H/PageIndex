import json

import httpx

from pageindex.core.utils import image_upload
from pageindex.core.utils.image_upload import upload_attachment_bytes


def test_upload_attachment_bytes_returns_uuid(monkeypatch):
    async_called = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        async_called["count"] += 1
        return httpx.Response(200, json={"data": {"uuid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}})

    transport = httpx.MockTransport(handler)
    original = httpx.Client

    class _Client(httpx.Client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setenv("PAGEINDEX_ATTACHMENT_UPLOAD_DOMAIN", "https://omnix.local")
    monkeypatch.setenv("PAGEINDEX_ATTACHMENT_UPLOAD_API_KEY", "secret")
    httpx.Client = _Client
    try:
        attachment_id = upload_attachment_bytes(b"png", "preview.png", "image/png")
    finally:
        httpx.Client = original

    assert attachment_id == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert async_called["count"] == 1


def test_upload_image_bytes_returns_uuid_markdown_and_optional_header(monkeypatch):
    monkeypatch.setenv("PAGEINDEX_ATTACHMENT_UPLOAD_DOMAIN", "http://localhost:8080")
    monkeypatch.setenv("PAGEINDEX_ATTACHMENT_UPLOAD_API_KEY", "secret-key")

    image_upload.load_settings.cache_clear() if hasattr(image_upload.load_settings, "cache_clear") else None

    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"uuid": "45296a84-ba5c-418a-add1-d5b7dff86bd4"}}

    class _Client:
        def __init__(self, timeout, headers=None):
            captured["timeout"] = timeout
            captured["headers"] = headers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, files):
            captured["url"] = url
            captured["files"] = files
            return _Response()

    monkeypatch.setattr(image_upload.httpx, "Client", _Client)

    markdown = image_upload.upload_image_bytes(b"abc", "sample.png", "image/png")

    assert markdown == "![image](45296a84-ba5c-418a-add1-d5b7dff86bd4)"
    assert captured["url"] == "http://localhost:8080/api/Attachment/upload"
    assert captured["headers"] == {"x-api-key": "secret-key"}


def test_upload_image_bytes_omits_api_key_header_when_empty(monkeypatch):
    monkeypatch.setenv("PAGEINDEX_ATTACHMENT_UPLOAD_DOMAIN", "http://localhost:8080")
    monkeypatch.delenv("PAGEINDEX_ATTACHMENT_UPLOAD_API_KEY", raising=False)

    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"uuid": "uuid-only"}}

    class _Client:
        def __init__(self, timeout, headers=None):
            captured["headers"] = headers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, files):
            del url, files
            return _Response()

    monkeypatch.setattr(image_upload.httpx, "Client", _Client)

    markdown = image_upload.upload_image_bytes(b"abc", "sample.png", "image/png")

    assert markdown == "![image](uuid-only)"
    assert captured["headers"] is None


def test_upload_image_bytes_uses_custom_alt_text(monkeypatch):
    monkeypatch.setenv("PAGEINDEX_ATTACHMENT_UPLOAD_DOMAIN", "http://localhost:8080")

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"uuid": "image-uuid"}}

    class _Client:
        def __init__(self, timeout, headers=None):
            del timeout, headers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, files):
            del url, files
            return _Response()

    monkeypatch.setattr(image_upload.httpx, "Client", _Client)

    markdown = image_upload.upload_image_bytes(b"abc", "sample.png", "image/png", alt_text="图表总览")

    assert markdown == "![图表总览](image-uuid)"
