from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pageindex.core.indexers.adapters.markdown import MarkdownAdapter
from pageindex.core.indexers.adapters.pdf import PdfAdapter
from pageindex.core.indexers.adapters.word import WordAdapter
from pageindex.core.indexers.pipeline.context import PipelineContext
from pageindex.core.utils.config import ConfigLoader
from pageindex.infrastructure.llm import LLMClient, use_llm_client


@dataclass(frozen=True)
class IndexerDependencies:
    libreoffice_command: str
    doc_conversion_timeout_seconds: int
    provider_type: str = "openai"
    model: str = "gpt-4o-2024-11-20"


@dataclass(frozen=True)
class IndexingOptions:
    model: str
    toc_check_page_num: int
    max_page_num_each_node: int
    max_token_num_each_node: int
    if_add_node_id: str
    if_add_node_summary: str
    if_add_doc_description: str
    if_add_node_text: str
    if_thinning: str
    thinning_threshold: int
    summary_token_threshold: int
    doc_conversion_timeout_seconds: int

    @classmethod
    def from_raw(cls, raw_options: dict[str, Any] | None = None) -> "IndexingOptions":
        raw = raw_options or {}
        cleaned = {key: value for key, value in raw.items() if value is not None}
        config = ConfigLoader().load(cleaned)
        return cls(**vars(config))


def infer_file_type(file_name: str) -> str:
    suffix = Path(file_name).suffix.lower()
    mapping = {".pdf": "pdf", ".md": "markdown", ".markdown": "markdown", ".docx": "docx", ".doc": "doc"}
    file_type = mapping.get(suffix)
    if file_type is None:
        raise ValueError(f"Unsupported file type: {file_name}")
    return file_type


class DocumentIndexer:
    def __init__(self, dependencies: IndexerDependencies):
        self._dependencies = dependencies
        self._pdf_adapter = PdfAdapter()
        self._markdown_adapter = MarkdownAdapter()
        self._word_adapter = WordAdapter()

    async def index(
        self,
        file_path: str | Path,
        index_options: dict[str, Any],
        llm_client: LLMClient,
    ) -> dict[str, Any]:
        path = Path(file_path)
        file_type = infer_file_type(path.name)
        options = IndexingOptions.from_raw({"model": self._dependencies.model, **index_options})

        handler = {
            "pdf": self._index_pdf,
            "markdown": self._index_markdown,
            "docx": self._index_docx,
            "doc": self._index_doc,
        }[file_type]
        return await handler(path, options, llm_client)

    async def _index_pdf(self, path: Path, options: IndexingOptions, llm_client: LLMClient):
        context = PipelineContext(
            source_path=path,
            provider_type=self._dependencies.provider_type,
            model=options.model,
            options=options,
            llm_client=llm_client,
            doc_name=path.stem,
        )
        with use_llm_client(llm_client):
            return await self._pdf_adapter.build(context)

    async def _index_markdown(self, path: Path, options: IndexingOptions, llm_client: LLMClient):
        context = PipelineContext(
            source_path=path,
            provider_type=self._dependencies.provider_type,
            model=options.model,
            options=options,
            llm_client=llm_client,
            doc_name=path.stem,
        )
        with use_llm_client(llm_client):
            return await self._markdown_adapter.build(context)

    async def _index_docx(self, path: Path, options: IndexingOptions, llm_client: LLMClient):
        context = PipelineContext(
            source_path=path,
            provider_type=self._dependencies.provider_type,
            model=options.model,
            options=options,
            llm_client=llm_client,
            doc_name=path.stem,
        )
        with use_llm_client(llm_client):
            return await self._word_adapter.build(context)

    async def _index_doc(self, path: Path, options: IndexingOptions, llm_client: LLMClient):
        with tempfile.TemporaryDirectory() as temp_dir:
            process = subprocess.run(
                [
                    self._dependencies.libreoffice_command,
                    "--headless",
                    "--convert-to",
                    "docx",
                    "--outdir",
                    temp_dir,
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=self._dependencies.doc_conversion_timeout_seconds,
                check=False,
            )
            if process.returncode != 0:
                raise RuntimeError(
                    f"DOC conversion failed with exit code {process.returncode}: "
                    f"{process.stderr.strip() or process.stdout.strip()}"
                )
            converted_path = Path(temp_dir) / f"{path.stem}.docx"
            if not converted_path.exists():
                raise RuntimeError("DOC conversion did not produce a DOCX file")
            return await self._index_docx(converted_path, options, llm_client)
