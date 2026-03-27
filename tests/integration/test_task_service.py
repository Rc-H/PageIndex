import asyncio

from pageindex.infrastructure.settings import ServiceSettings
from pageindex.core.services.task_service import IndexTaskService
from pageindex.messages.models import CallbackTarget, IndexTaskRequest, RemoteFileReference
from tests.helpers import FakeDocumentIndexer, FakePdfPagePreviewService, SpyCallbackClient, fake_llm_client_factory


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


def test_submit_includes_page_previews_in_completed_result():
    callback_client = SpyCallbackClient()
    service = IndexTaskService(
        ServiceSettings(seq_url="http://seq.local"),
        callback_client=callback_client,
        document_indexer=FakeDocumentIndexer(),
        page_preview_service=FakePdfPagePreviewService(
            previews=[
                {"page_no": 1, "attachment_id": "11111111-1111-1111-1111-111111111111"},
                {"page_no": 3, "attachment_id": "33333333-3333-3333-3333-333333333333"},
            ]
        ),
        llm_client_factory=fake_llm_client_factory,
    )

    async def _submit_task():
        await service.submit(
            IndexTaskRequest(
                task_id="task-preview",
                index_options={},
                callback=CallbackTarget(url="https://omnix.local/callback", headers={}),
                uploaded_file=None,
                remote_file=RemoteFileReference(url="https://example.com/handbook.pdf", headers={}),
            )
        )
        await _wait_for_events(callback_client, 4)

    class PreviewRemoteFileFetcher:
        async def fetch(self, remote_file):
            del remote_file
            from pageindex.messages.models import SubmittedFile

            return SubmittedFile(original_name="handbook.pdf", content=b"%PDF-1.4")

    service._remote_file_fetcher = PreviewRemoteFileFetcher()
    asyncio.run(_submit_task())

    completed_event = callback_client.events[-1]
    assert completed_event["status"] == "completed"
    assert completed_event["result"]["page_previews"] == [
        {"page_no": 1, "attachment_id": "11111111-1111-1111-1111-111111111111"},
        {"page_no": 3, "attachment_id": "33333333-3333-3333-3333-333333333333"},
    ]


def test_submit_keeps_content_images_in_completed_result():
    callback_client = SpyCallbackClient()

    class ContentImageDocumentIndexer(FakeDocumentIndexer):
        async def index(self, file_path, index_options, llm_client):
            result = await super().index(file_path, index_options, llm_client)
            result["content_images"] = [
                {
                    "page_no": 7,
                    "block_no": 9,
                    "file_name": "handbook.pdf-page-7.png",
                    "attachment_id": "77777777-7777-7777-7777-777777777777",
                }
            ]
            return result

    service = IndexTaskService(
        ServiceSettings(seq_url="http://seq.local"),
        callback_client=callback_client,
        document_indexer=ContentImageDocumentIndexer(),
        page_preview_service=FakePdfPagePreviewService(),
        llm_client_factory=fake_llm_client_factory,
    )

    async def _submit_task():
        await service.submit(
            IndexTaskRequest(
                task_id="task-content-image",
                index_options={},
                callback=CallbackTarget(url="https://omnix.local/callback", headers={}),
                uploaded_file=None,
                remote_file=RemoteFileReference(url="https://example.com/handbook.pdf", headers={}),
            )
        )
        await _wait_for_events(callback_client, 4)

    class PreviewRemoteFileFetcher:
        async def fetch(self, remote_file):
            del remote_file
            from pageindex.messages.models import SubmittedFile

            return SubmittedFile(original_name="handbook.pdf", content=b"%PDF-1.4")

    service._remote_file_fetcher = PreviewRemoteFileFetcher()
    asyncio.run(_submit_task())

    completed_event = callback_client.events[-1]
    assert completed_event["status"] == "completed"
    assert completed_event["result"]["content_images"] == [
        {
            "page_no": 7,
            "block_no": 9,
            "file_name": "handbook.pdf-page-7.png",
            "attachment_id": "77777777-7777-7777-7777-777777777777",
        }
    ]
