import json
import time

from fastapi.testclient import TestClient

from pageindex.api.app import create_app
from pageindex.infrastructure.settings import ServiceSettings
from pageindex.core.services.task_service import IndexTaskService
from tests.helpers import FakeDocumentIndexer, FakeRemoteFileFetcher, SpyCallbackClient, fake_llm_client_factory


def _build_service(should_fail: bool = False):
    callback_client = SpyCallbackClient()
    service = IndexTaskService(
        ServiceSettings(),
        callback_client=callback_client,
        remote_file_fetcher=FakeRemoteFileFetcher(),
        document_indexer=FakeDocumentIndexer(should_fail=should_fail),
        llm_client_factory=fake_llm_client_factory,
    )
    return service, callback_client


def _wait_for_events(callback_client: SpyCallbackClient, expected_count: int):
    for _ in range(50):
        if len(callback_client.events) >= expected_count:
            return
        time.sleep(0.05)
    raise AssertionError("callback events not received")


def test_multipart_single_file_returns_accepted_and_emits_callbacks():
    service, callback_client = _build_service()
    app = create_app(ServiceSettings(), task_service=service)

    with TestClient(app) as client:
        response = client.post(
            "/v1/index-tasks",
            data={
                "task_id": "task-1",
                "provider_type": "openai",
                "model": "gpt-test",
                "index_options": json.dumps({"if_add_node_summary": "yes"}),
                "callback_url": "http://omnix.local/api/PageIndex/callback",
                "callback_headers": json.dumps({"Authorization": "Bearer token"}),
            },
            files=[("file", ("sample.md", b"# Intro\nHello", "text/markdown"))],
        )

        assert response.status_code == 202
        assert response.json() == {"task_id": "task-1", "status": "accepted"}

    _wait_for_events(callback_client, 4)
    assert [item["status"] for item in callback_client.events] == [
        "accepted",
        "running",
        "running",
        "completed",
    ]
    assert callback_client.events[-1]["result"]["structure"][0]["title"] == "Intro"


def test_remote_url_submission_returns_accepted_and_emits_callbacks():
    service, callback_client = _build_service()
    app = create_app(ServiceSettings(), task_service=service)

    with TestClient(app) as client:
        response = client.post(
            "/v1/index-tasks",
            json={
                "task_id": "task-remote",
                "provider_type": "openai",
                "model": "gpt-test",
                "index_options": {"if_add_node_summary": "yes"},
                "callback_url": "http://omnix.local/api/PageIndex/callback",
                "callback_headers": {"Authorization": "Bearer token"},
                "remote_file_url": "https://example.com/test.md",
                "remote_file_headers": {"X-Test": "1"},
            },
        )

        assert response.status_code == 202

    _wait_for_events(callback_client, 4)
    assert callback_client.events[1]["stage"] == "fetching"
    assert callback_client.events[-1]["status"] == "completed"


def test_failed_indexing_emits_failed_callback():
    service, callback_client = _build_service(should_fail=True)
    app = create_app(ServiceSettings(), task_service=service)

    with TestClient(app) as client:
        response = client.post(
            "/v1/index-tasks",
            data={
                "task_id": "task-failed",
                "provider_type": "openai",
                "model": "gpt-test",
                "callback_url": "http://omnix.local/api/PageIndex/callback",
            },
            files=[("file", ("sample.md", b"# Intro\nHello", "text/markdown"))],
        )

        assert response.status_code == 202

    _wait_for_events(callback_client, 3)
    assert callback_client.events[-1]["status"] == "failed"
    assert callback_client.events[-1]["error_message"] == "index failed"


def test_missing_callback_url_returns_bad_request():
    service, _ = _build_service()
    app = create_app(ServiceSettings(), task_service=service)

    with TestClient(app) as client:
        response = client.post(
            "/v1/index-tasks",
            data={
                "task_id": "task-1",
                "provider_type": "openai",
                "model": "gpt-test",
            },
            files=[("file", ("sample.md", b"# Intro\nHello", "text/markdown"))],
        )

    assert response.status_code == 400
    assert "callback_url" in response.json()["detail"]


def test_missing_file_and_remote_url_returns_bad_request():
    service, _ = _build_service()
    app = create_app(ServiceSettings(), task_service=service)

    with TestClient(app) as client:
        response = client.post(
            "/v1/index-tasks",
            json={
                "task_id": "task-1",
                "provider_type": "openai",
                "model": "gpt-test",
                "callback_url": "http://omnix.local/api/PageIndex/callback",
            },
        )

    assert response.status_code == 400
    assert "Either file or remote_file_url" in response.json()["detail"]


def test_file_and_remote_url_together_returns_bad_request():
    service, _ = _build_service()
    app = create_app(ServiceSettings(), task_service=service)

    with TestClient(app) as client:
        response = client.post(
            "/v1/index-tasks",
            data={
                "task_id": "task-1",
                "provider_type": "openai",
                "model": "gpt-test",
                "callback_url": "http://omnix.local/api/PageIndex/callback",
                "remote_file_url": "https://example.com/test.md",
            },
            files=[("file", ("sample.md", b"# Intro\nHello", "text/markdown"))],
        )

    assert response.status_code == 400
    assert "mutually exclusive" in response.json()["detail"]


def test_invalid_index_options_json_returns_bad_request():
    service, _ = _build_service()
    app = create_app(ServiceSettings(), task_service=service)

    with TestClient(app) as client:
        response = client.post(
            "/v1/index-tasks",
            data={
                "task_id": "task-1",
                "provider_type": "openai",
                "model": "gpt-test",
                "callback_url": "http://omnix.local/api/PageIndex/callback",
                "index_options": "{bad",
            },
            files=[("file", ("sample.md", b"# Intro\nHello", "text/markdown"))],
        )

    assert response.status_code == 400
    assert "index_options" in response.json()["detail"]


def test_invalid_callback_headers_json_returns_bad_request():
    service, _ = _build_service()
    app = create_app(ServiceSettings(), task_service=service)

    with TestClient(app) as client:
        response = client.post(
            "/v1/index-tasks",
            data={
                "task_id": "task-1",
                "provider_type": "openai",
                "model": "gpt-test",
                "callback_url": "http://omnix.local/api/PageIndex/callback",
                "callback_headers": "{bad",
            },
            files=[("file", ("sample.md", b"# Intro\nHello", "text/markdown"))],
        )

    assert response.status_code == 400
    assert "callback_headers" in response.json()["detail"]


def test_invalid_remote_file_headers_json_returns_bad_request():
    service, _ = _build_service()
    app = create_app(ServiceSettings(), task_service=service)

    with TestClient(app) as client:
        response = client.post(
            "/v1/index-tasks",
            data={
                "task_id": "task-1",
                "provider_type": "openai",
                "model": "gpt-test",
                "callback_url": "http://omnix.local/api/PageIndex/callback",
                "remote_file_url": "https://example.com/test.md",
                "remote_file_headers": "{bad",
            },
            files=[("file", ("sample.md", b"# Intro\nHello", "text/markdown"))],
        )

    assert response.status_code == 400
    assert "remote_file_headers" in response.json()["detail"]


def test_json_request_requires_object_body():
    service, _ = _build_service()
    app = create_app(ServiceSettings(), task_service=service)

    with TestClient(app) as client:
        response = client.post(
            "/v1/index-tasks",
            content='["not-an-object"]',
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 400
    assert "must be an object" in response.json()["detail"]


def test_json_request_rejects_non_object_callback_headers():
    service, _ = _build_service()
    app = create_app(ServiceSettings(), task_service=service)

    with TestClient(app) as client:
        response = client.post(
            "/v1/index-tasks",
            json={
                "task_id": "task-headers",
                "provider_type": "openai",
                "model": "gpt-test",
                "callback_url": "http://omnix.local/api/PageIndex/callback",
                "remote_file_url": "https://example.com/test.md",
                "callback_headers": ["not", "a", "mapping"],
            },
        )

    assert response.status_code == 400
    assert "callback_headers" in response.json()["detail"]


def test_multipart_request_rejects_non_object_index_options():
    service, _ = _build_service()
    app = create_app(ServiceSettings(), task_service=service)

    with TestClient(app) as client:
        response = client.post(
            "/v1/index-tasks",
            data={
                "task_id": "task-options",
                "provider_type": "openai",
                "model": "gpt-test",
                "callback_url": "http://omnix.local/api/PageIndex/callback",
                "index_options": '["not-an-object"]',
            },
            files=[("file", ("sample.md", b"# Intro\nHello", "text/markdown"))],
        )

    assert response.status_code == 400
    assert "index_options" in response.json()["detail"]
