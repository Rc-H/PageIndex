import json
import time

import pytest
from fastapi.testclient import TestClient

from pageindex.api import app as api_app
from pageindex.core.services.task_service import IndexTaskService
from pageindex.infrastructure.settings import ServiceSettings
from tests.helpers import FakeDocumentIndexer, FakeRemoteFileFetcher, SpyCallbackClient, fake_llm_client_factory


TEST_SERVICE_SETTINGS = ServiceSettings(seq_url="")
CALLBACK_URL = "http://omnix.local/api/PageIndex/callback"
SAMPLE_FILE = [("file", ("sample.md", b"# Intro\nHello", "text/markdown"))]


def _build_service(should_fail: bool = False):
    callback_client = SpyCallbackClient()
    service = IndexTaskService(
        TEST_SERVICE_SETTINGS,
        callback_client=callback_client,
        remote_file_fetcher=FakeRemoteFileFetcher(),
        document_indexer=FakeDocumentIndexer(should_fail=should_fail),
        llm_client_factory=fake_llm_client_factory,
    )
    return service, callback_client


def _build_app(should_fail: bool = False):
    service, callback_client = _build_service(should_fail=should_fail)
    api_app.configure_logging = lambda **kwargs: None
    return api_app.create_app(TEST_SERVICE_SETTINGS, task_service=service), callback_client


def _wait_for_events(callback_client: SpyCallbackClient, expected_count: int):
    for _ in range(50):
        if len(callback_client.events) >= expected_count:
            return
        time.sleep(0.05)
    raise AssertionError("callback events not received")


def test_multipart_single_file_returns_accepted_and_emits_callbacks():
    app, callback_client = _build_app()

    with TestClient(app) as client:
        response = client.post(
            "/v1/index-tasks",
            data={
                "task_id": "task-1",
                "index_options": json.dumps({"if_add_node_summary": "yes"}),
                "callback_url": CALLBACK_URL,
                "callback_headers": json.dumps({"Authorization": "Bearer token"}),
            },
            files=SAMPLE_FILE,
        )

    assert response.status_code == 202
    assert response.json() == {"task_id": "task-1", "status": "accepted"}

    _wait_for_events(callback_client, 4)
    assert [event["status"] for event in callback_client.events] == [
        "accepted",
        "running",
        "running",
        "completed",
    ]
    assert callback_client.events[-1]["result"]["structure"][0]["title"] == "Intro"


def test_remote_url_submission_returns_accepted_and_emits_callbacks():
    app, callback_client = _build_app()

    with TestClient(app) as client:
        response = client.post(
            "/v1/index-tasks",
            json={
                "task_id": "task-remote",
                "index_options": {"if_add_node_summary": "yes"},
                "callback_url": CALLBACK_URL,
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
    app, callback_client = _build_app(should_fail=True)

    with TestClient(app) as client:
        response = client.post(
            "/v1/index-tasks",
            data={
                "task_id": "task-failed",
                "callback_url": CALLBACK_URL,
            },
            files=SAMPLE_FILE,
        )

    assert response.status_code == 202

    _wait_for_events(callback_client, 3)
    assert callback_client.events[-1]["status"] == "failed"
    assert callback_client.events[-1]["error_message"] == "index failed"


@pytest.mark.parametrize(
    ("request_kind", "payload", "expected_detail"),
    [
        ("multipart", {"task_id": "task-1", "file": True}, "callback_url"),
        ("json", {"task_id": "task-1", "callback_url": CALLBACK_URL}, "Either file or remote_file_url"),
        (
            "multipart",
            {"task_id": "task-1", "callback_url": CALLBACK_URL, "remote_file_url": "https://example.com/test.md", "file": True},
            "mutually exclusive",
        ),
        ("multipart", {"task_id": "task-1", "callback_url": CALLBACK_URL, "index_options": "{bad}", "file": True}, "index_options"),
        ("multipart", {"task_id": "task-1", "callback_url": CALLBACK_URL, "callback_headers": "{bad}", "file": True}, "callback_headers"),
        (
            "multipart",
            {
                "task_id": "task-1",
                "callback_url": CALLBACK_URL,
                "remote_file_url": "https://example.com/test.md",
                "remote_file_headers": "{bad}",
                "file": True,
            },
            "remote_file_headers",
        ),
        ("raw-json", '["not-an-object"]', "must be an object"),
        (
            "json",
            {
                "task_id": "task-headers",
                "callback_url": CALLBACK_URL,
                "remote_file_url": "https://example.com/test.md",
                "callback_headers": ["not", "a", "mapping"],
            },
            "callback_headers",
        ),
    ],
)
def test_index_task_request_validation_returns_bad_request(request_kind, payload, expected_detail):
    app, _ = _build_app()

    with TestClient(app) as client:
        if request_kind == "multipart":
            data = {key: value for key, value in payload.items() if key != "file"}
            files = SAMPLE_FILE if payload.get("file") else None
            response = client.post("/v1/index-tasks", data=data, files=files)
        elif request_kind == "json":
            response = client.post("/v1/index-tasks", json=payload)
        else:
            response = client.post(
                "/v1/index-tasks",
                content=payload,
                headers={"content-type": "application/json"},
            )

    assert response.status_code == 400
    assert expected_detail in response.json()["detail"]


def test_multipart_request_rejects_non_object_index_options():
    app, _ = _build_app()

    with TestClient(app) as client:
        response = client.post(
            "/v1/index-tasks",
            data={
                "task_id": "task-options",
                "callback_url": CALLBACK_URL,
                "index_options": '["not-an-object"]',
            },
            files=SAMPLE_FILE,
        )

    assert response.status_code == 400
    assert "index_options" in response.json()["detail"]
