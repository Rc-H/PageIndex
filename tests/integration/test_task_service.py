import asyncio

from pageindex.infrastructure.settings import ServiceSettings
from pageindex.core.services.task_service import IndexTaskService
from pageindex.messages.models import CallbackTarget, IndexTaskRequest, RemoteFileReference
from tests.helpers import SpyCallbackClient, fake_llm_client_factory


async def _wait_for_events(callback_client: SpyCallbackClient, expected_count: int):
    for _ in range(100):
        if len(callback_client.events) >= expected_count:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("callback events not received")


class FailingRemoteFileFetcher:
    async def fetch(self, remote_file):
        del remote_file
        raise RuntimeError("download failed")


def test_submit_reports_failed_result_when_remote_fetch_fails():
    callback_client = SpyCallbackClient()
    service = IndexTaskService(
        ServiceSettings(seq_url="http://seq.local"),
        callback_client=callback_client,
        remote_file_fetcher=FailingRemoteFileFetcher(),
        llm_client_factory=fake_llm_client_factory,
    )

    async def _submit_task():
        await service.submit(
            IndexTaskRequest(
                task_id="task-remote-failed",
                provider_type="openai",
                model="gpt-test",
                index_options={},
                callback=CallbackTarget(url="https://omnix.local/callback", headers={}),
                remote_file=RemoteFileReference(url="https://example.com/missing.md", headers={}),
            )
        )
        await _wait_for_events(callback_client, 3)

    asyncio.run(_submit_task())

    assert [event["stage"] for event in callback_client.events] == ["accepted", "fetching", "failed"]
    assert callback_client.events[-1]["status"] == "failed"
    assert callback_client.events[-1]["error_message"] == "download failed"
