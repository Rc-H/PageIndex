from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pageindex.infrastructure.llm import LLMClient

if TYPE_CHECKING:
    from pageindex.core.indexers.document_indexer import IndexingOptions


@dataclass
class PipelineContext:
    source_path: str | Path
    provider_type: str
    model: str
    options: "IndexingOptions"
    llm_client: LLMClient | None
    doc_name: str | None = None
    page_list: list[Any] | None = None
    pdf_tables_by_page: dict[int, list[dict[str, Any]]] | None = None
    outline: list[dict[str, Any]] | None = None
    tree: list[dict[str, Any]] | None = None
    logger: Any = None
