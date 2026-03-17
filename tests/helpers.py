from __future__ import annotations

from io import BytesIO
from typing import Any

from pageindex.infrastructure.llm import LLMClient

try:
    from docx import Document
except Exception:  # pragma: no cover - optional dependency for test env
    Document = None


class FakeLLMClient(LLMClient):
    def generate_text(self, model: str, prompt: str, chat_history=None) -> str:
        del model, prompt, chat_history
        return "fake-response"

    def generate_text_with_finish_reason(self, model: str, prompt: str, chat_history=None) -> tuple[str, str]:
        del model, prompt, chat_history
        return "fake-response", "finished"

    async def generate_text_async(self, model: str, prompt: str, chat_history=None) -> str:
        del model, prompt, chat_history
        return "fake-response"


def fake_llm_client_factory() -> LLMClient:
    return FakeLLMClient()


class SpyCallbackClient:
    def __init__(self):
        self.events: list[dict[str, Any]] = []

    async def send(self, callback, payload: dict[str, Any]) -> None:
        del callback
        self.events.append(payload)


class FakeRemoteFileFetcher:
    def __init__(self, file_name: str = "remote.md", content: bytes = b"# Remote\nHello"):
        self.file_name = file_name
        self.content = content

    async def fetch(self, remote_file):
        del remote_file
        from pageindex.messages.models import SubmittedFile

        return SubmittedFile(original_name=self.file_name, content=self.content)


class FakeDocumentIndexer:
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail

    async def index(self, file_path, index_options, llm_client):
        del index_options, llm_client
        if self.should_fail:
            raise RuntimeError("index failed")
        return {
            "doc_name": getattr(file_path, "stem", "sample"),
            "structure": [{"title": "Intro", "node_id": "0001"}],
        }


def build_docx_bytes() -> bytes:
    if Document is None:
        raise RuntimeError("python-docx is required for DOCX test fixtures")
    document = Document()
    document.add_heading("Executive Summary", level=1)
    document.add_paragraph("Revenue increased year over year.")
    document.add_heading("Details", level=2)
    document.add_paragraph("Operating margin also improved.")
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
