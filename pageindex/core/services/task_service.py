from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any, Callable

import httpx

from pageindex.core.indexers import DocumentIndexer, IndexerDependencies
from pageindex.core.services.page_preview_service import PdfPagePreviewService
from pageindex.infrastructure.llm import LLMClient, LLMProviderFactory
from pageindex.infrastructure.settings import LLMSettings, ServiceSettings, load_settings
from pageindex.messages.models import CallbackTarget, IndexTaskRequest, RemoteFileReference, SubmittedFile


class RemoteFileFetcher:
    def __init__(self, timeout_seconds: int):
        self._timeout_seconds = timeout_seconds

    async def fetch(self, remote_file: RemoteFileReference) -> SubmittedFile:
        timeout = httpx.Timeout(self._timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout, headers=remote_file.headers) as client:
            response = await client.get(remote_file.url)
            response.raise_for_status()

        file_name = self._infer_name(remote_file.url, response.headers)
        return SubmittedFile(original_name=file_name, content=response.content)

    @staticmethod
    def _infer_name(url: str, headers: httpx.Headers) -> str:
        content_disposition = headers.get("content-disposition", "")
        if "filename=" in content_disposition:
            candidate = content_disposition.split("filename=", 1)[1].strip().strip('"')
            if candidate:
                return candidate
        name = Path(url.split("?", 1)[0]).name
        return name or "remote-file.bin"


class CallbackClient:
    def __init__(self, timeout_seconds: int, retry_count: int):
        self._timeout_seconds = timeout_seconds
        self._retry_count = retry_count

    async def send(self, callback: CallbackTarget, payload: dict[str, Any]) -> None:
        timeout = httpx.Timeout(self._timeout_seconds)
        last_error: Exception | None = None
        for attempt in range(self._retry_count):
            try:
                async with httpx.AsyncClient(timeout=timeout, headers=callback.headers) as client:
                    response = await client.post(callback.url, json=payload)
                    response.raise_for_status()
                    return
            except Exception as exc:  # pragma: no cover - retried path
                last_error = exc
                if attempt < self._retry_count - 1:
                    await asyncio.sleep(min(attempt + 1, 3))
        if last_error is not None:
            raise last_error


class IndexTaskService:
    def __init__(
        self,
        settings: ServiceSettings,
        llm_settings: LLMSettings | None = None,
        callback_client: CallbackClient | None = None,
        remote_file_fetcher: RemoteFileFetcher | None = None,
        document_indexer: DocumentIndexer | None = None,
        page_preview_service: PdfPagePreviewService | None = None,
        llm_client_factory: Callable[[], LLMClient] | None = None,
    ):
        self._settings = settings
        self._llm_settings = llm_settings or load_settings().llm
        self._callback_client = callback_client or CallbackClient(
            timeout_seconds=settings.callback_timeout_seconds,
            retry_count=settings.callback_retry_count,
        )
        self._remote_file_fetcher = remote_file_fetcher or RemoteFileFetcher(
            timeout_seconds=settings.remote_file_timeout_seconds
        )
        self._document_indexer = document_indexer or DocumentIndexer(
            IndexerDependencies(
                libreoffice_command=settings.libreoffice_command,
                doc_conversion_timeout_seconds=settings.doc_conversion_timeout_seconds,
                provider_type=self._llm_settings.provider,
                model=self._llm_settings.model,
            )
        )
        self._page_preview_service = page_preview_service or PdfPagePreviewService(dpi=settings.page_preview_dpi)
        self._llm_client_factory = llm_client_factory or (lambda: LLMProviderFactory.create(self._llm_settings))
        self._background_tasks: set[asyncio.Task] = set()
        self._concurrency_semaphore = asyncio.Semaphore(settings.max_concurrent_tasks)

    async def submit(self, task_request: IndexTaskRequest) -> None:
        task = asyncio.create_task(self._run(task_request))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _run(self, task_request: IndexTaskRequest) -> None:
        file_name = task_request.uploaded_file.original_name if task_request.uploaded_file else None
        try:
            await self._send_progress(task_request, "accepted", "accepted", 0, file_name)
            submitted_file = task_request.uploaded_file
            if submitted_file is None and task_request.remote_file is not None:
                await self._send_progress(task_request, "running", "fetching", 10, file_name)
                submitted_file = await self._remote_file_fetcher.fetch(task_request.remote_file)
                file_name = submitted_file.original_name

            if submitted_file is None:
                raise ValueError("Either uploaded_file or remote_file must be provided")

            await self._send_progress(task_request, "running", "indexing", 60, submitted_file.original_name)

            async with self._concurrency_semaphore:
                with tempfile.TemporaryDirectory() as temp_dir:
                    local_path = Path(temp_dir) / submitted_file.original_name
                    local_path.write_bytes(submitted_file.content)
                    llm_client = self._llm_client_factory()

                    # Run the indexer in a dedicated thread with its own event
                    # loop.  The pipeline contains many synchronous blocking
                    # calls (sync LLM HTTP requests via call_llm(), PDF table
                    # extraction via pdfplumber/camelot, PyMuPDF page reads)
                    # that would freeze the main asyncio event loop and prevent
                    # concurrent request handling.  By running each indexing
                    # task in its own thread+event-loop, blocking calls only
                    # stall that thread while the main loop stays responsive.
                    result = await asyncio.to_thread(
                        self._run_indexer_sync,
                        local_path,
                        task_request.index_options,
                        llm_client,
                    )

                    page_previews = await asyncio.to_thread(
                        self._page_preview_service.generate, local_path
                    )
                    if page_previews:
                        result["page_previews"] = page_previews

            await self._send_progress(task_request, "running", "finalizing", 90, submitted_file.original_name)
            await self._callback_client.send(
                task_request.callback,
                {
                    "task_id": task_request.task_id,
                    "event_type": "result",
                    "status": "completed",
                    "progress_percent": 100,
                    "stage": "completed",
                    "file_name": submitted_file.original_name,
                    "provider_type": self._llm_settings.provider,
                    "model": self._llm_settings.model,
                    "result": result,
                    "error_message": None,
                },
            )
        except Exception as exc:
            try:
                await self._callback_client.send(
                    task_request.callback,
                    {
                        "task_id": task_request.task_id,
                        "event_type": "result",
                        "status": "failed",
                        "progress_percent": 100,
                        "stage": "failed",
                        "file_name": file_name,
                        "provider_type": self._llm_settings.provider,
                        "model": self._llm_settings.model,
                        "result": None,
                        "error_message": str(exc),
                    },
                )
            except Exception:
                return

    def _run_indexer_sync(
        self,
        local_path: Path,
        index_options: dict,
        llm_client: LLMClient,
    ) -> dict:
        """Run the async indexer in a dedicated event loop on the current thread.

        This isolates synchronous blocking calls (LLM HTTP, PDF parsing) so
        they do not freeze the main asyncio event loop.
        """
        return asyncio.run(
            self._document_indexer.index(
                file_path=local_path,
                index_options=index_options,
                llm_client=llm_client,
            )
        )

    async def _send_progress(
        self,
        task_request: IndexTaskRequest,
        status: str,
        stage: str,
        progress_percent: int,
        file_name: str | None,
    ) -> None:
        await self._callback_client.send(
            task_request.callback,
            {
                "task_id": task_request.task_id,
                "event_type": "progress",
                "status": status,
                "progress_percent": progress_percent,
                "stage": stage,
                "file_name": file_name,
                "provider_type": self._llm_settings.provider,
                "model": self._llm_settings.model,
                "result": None,
                "error_message": None,
            },
        )
