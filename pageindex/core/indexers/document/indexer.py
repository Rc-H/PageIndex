from __future__ import annotations

import asyncio
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pageindex.infrastructure.llm import LLMClient, use_llm_client
from pageindex.core.indexers.document.docx_parser import extract_docx_nodes, require_word_document
from pageindex.core.indexers.markdown.indexer import build_tree_from_nodes, generate_summaries_for_structure_md, md_to_tree
from pageindex.core.indexers.pdf.indexer import page_index_main
from pageindex.core.utils.config import ConfigLoader
from pageindex.core.utils.structure_ops import (
    create_clean_structure_for_description,
    format_structure,
    generate_doc_description,
)
from pageindex.core.utils.tree import write_node_id


@dataclass(frozen=True)
class IndexerDependencies:
    libreoffice_command: str
    doc_conversion_timeout_seconds: int


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

    async def index(self, file_path: str | Path, provider_type: str, model: str, index_options: dict[str, Any], llm_client: LLMClient) -> dict[str, Any]:
        del provider_type
        path = Path(file_path)
        file_type = infer_file_type(path.name)
        handler = {
            "pdf": self._index_pdf,
            "markdown": self._index_markdown,
            "docx": self._index_docx,
            "doc": self._index_doc,
        }[file_type]
        return await handler(path, model, index_options, llm_client)

    async def _index_pdf(self, path, model, index_options, llm_client):
        opt = ConfigLoader().load({"model": model, **index_options})

        def _run():
            with use_llm_client(llm_client):
                return page_index_main(str(path), opt)
        return await asyncio.to_thread(_run)

    async def _index_markdown(self, path, model, index_options, llm_client):
        opt = ConfigLoader().load({
            "model": model,
            "if_add_node_summary": index_options.get("if_add_node_summary", "yes"),
            "if_add_doc_description": index_options.get("if_add_doc_description", "no"),
            "if_add_node_text": index_options.get("if_add_node_text", "no"),
            "if_add_node_id": index_options.get("if_add_node_id", "yes"),
            "if_thinning": index_options.get("if_thinning", "no"),
            "thinning_threshold": index_options.get("thinning_threshold", 5000),
            "summary_token_threshold": index_options.get("summary_token_threshold", 200),
        })
        with use_llm_client(llm_client):
            return await md_to_tree(
                md_path=str(path),
                if_thinning=opt.if_thinning == "yes",
                min_token_threshold=opt.thinning_threshold,
                if_add_node_summary=opt.if_add_node_summary,
                summary_token_threshold=opt.summary_token_threshold,
                model=opt.model,
                if_add_doc_description=opt.if_add_doc_description,
                if_add_node_text=opt.if_add_node_text,
                if_add_node_id=opt.if_add_node_id,
            )

    async def _index_docx(self, path, model, index_options, llm_client):
        WordDocument = require_word_document()
        if_add_node_id = index_options.get("if_add_node_id", "yes")
        if_add_node_summary = index_options.get("if_add_node_summary", "yes")
        if_add_doc_description = index_options.get("if_add_doc_description", "no")
        if_add_node_text = index_options.get("if_add_node_text", "no")
        summary_token_threshold = int(index_options.get("summary_token_threshold", 200))

        document = WordDocument(str(path))
        flat_nodes = extract_docx_nodes(document, path.stem)
        tree_structure = build_tree_from_nodes(flat_nodes)

        if if_add_node_id == "yes":
            write_node_id(tree_structure)

        tree_structure = self._apply_formatting_and_summaries(
            tree_structure, model, llm_client,
            if_add_node_summary, if_add_node_text, summary_token_threshold,
        )

        result: dict[str, Any] = {"doc_name": path.stem, "structure": tree_structure}
        if if_add_doc_description == "yes":
            with use_llm_client(llm_client):
                result["doc_description"] = generate_doc_description(
                    create_clean_structure_for_description(tree_structure), model=model,
                )
        return result

    async def _index_doc(self, path, model, index_options, llm_client):
        with tempfile.TemporaryDirectory() as temp_dir:
            process = subprocess.run(
                [self._dependencies.libreoffice_command, "--headless", "--convert-to", "docx", "--outdir", temp_dir, str(path)],
                capture_output=True, text=True,
                timeout=self._dependencies.doc_conversion_timeout_seconds, check=False,
            )
            if process.returncode != 0:
                raise RuntimeError(f"DOC conversion failed with exit code {process.returncode}: {process.stderr.strip() or process.stdout.strip()}")
            converted_path = Path(temp_dir) / f"{path.stem}.docx"
            if not converted_path.exists():
                raise RuntimeError("DOC conversion did not produce a DOCX file")
            return await self._index_docx(converted_path, model, index_options, llm_client)

    def _apply_formatting_and_summaries(self, tree_structure, model, llm_client, if_add_node_summary, if_add_node_text, summary_token_threshold):
        if if_add_node_summary == "yes":
            tree_structure = format_structure(tree_structure, order=["title", "node_id", "summary", "prefix_summary", "text", "line_num", "nodes"])
            with use_llm_client(llm_client):
                tree_structure = asyncio.run(generate_summaries_for_structure_md(tree_structure, summary_token_threshold=summary_token_threshold, model=model))
            if if_add_node_text == "no":
                tree_structure = format_structure(tree_structure, order=["title", "node_id", "summary", "prefix_summary", "line_num", "nodes"])
        else:
            if if_add_node_text == "yes":
                tree_structure = format_structure(tree_structure, order=["title", "node_id", "text", "line_num", "nodes"])
            else:
                tree_structure = format_structure(tree_structure, order=["title", "node_id", "line_num", "nodes"])
        return tree_structure
