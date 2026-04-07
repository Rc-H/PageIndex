"""DOCX adapter.

Orchestrates the Word indexing pipeline as a sequence of named steps. Each
step delegates to a focused module (body iterator, outline extractor, block
extractor, tree builder, enricher, block finalizer).

Supported by this adapter:
- Top-level paragraphs and tables (tables are textualized into one block)
- Tables nested inside table cells (recursively textualized)
- Inline images (uploaded and substituted with markdown image references)
- Hyperlinks (preserved as markdown links)

NOT supported:
- Real page numbers (Word has no page concept here; ``page_no`` reflects the
  section ordinal of the owning heading)
- bbox / coordinates
- Table structure preservation in metadata (all blocks are
  ``metadata.type = "text"``)
- Merge cell semantics (``gridSpan`` / ``vMerge``) — merged cells appear as
  duplicated values per python-docx defaults
"""

from __future__ import annotations

from typing import Any

from pageindex.core.indexers.pipeline.context import PipelineContext
from pageindex.core.indexers.pipeline.step_01_outline_discovery import (
    extract_docx_blocks,
    extract_docx_nodes,
    iter_docx_body_items,
    require_word_document,
)
from pageindex.core.indexers.pipeline.step_03_tree_construction import build_tree_from_nodes
from pageindex.core.indexers.pipeline.step_05_enrichment import (
    create_clean_structure_for_description,
    format_structure,
    generate_doc_description,
    generate_summaries_for_markdown_structure,
)
from pageindex.core.indexers.pipeline.step_06_finalize import build_index_result, finalize_word_blocks
from pageindex.core.utils.tree import write_node_id


class WordAdapter:
    async def build(self, context: PipelineContext) -> dict[str, Any]:
        document = self._open_document(context)
        image_cache: dict[object, str] = {}

        # Walk the body ONCE and materialize the items. Both the outline
        # extractor and the block extractor consume the same list, so the
        # LLM-driven field-table expander inside the iterator runs at most
        # once per table.
        body_items = self._materialize_body_items(document, image_cache, context)

        flat_nodes = self._extract_outline(body_items, context)
        raw_blocks = self._extract_raw_blocks(body_items)

        tree_structure = self._build_tree(flat_nodes)
        self._assign_node_ids(tree_structure)

        await self._maybe_enrich_with_summaries(tree_structure, context)
        blocks, char_count, token_count = self._finalize_blocks(raw_blocks, tree_structure, context)
        doc_description = self._maybe_generate_doc_description(tree_structure, context)

        tree_structure = self._apply_visibility_order(tree_structure, context)

        return build_index_result(
            doc_name=self._resolve_doc_name(context),
            structure=tree_structure,
            doc_description=doc_description,
            char_count=char_count,
            token_count=token_count,
            extract={"blocks": blocks},
            location_unit="section",
        )

    def _open_document(self, context: PipelineContext):
        document_class = require_word_document()
        return document_class(str(context.source_path))

    def _materialize_body_items(self, document, image_cache, context: PipelineContext):
        return list(
            iter_docx_body_items(
                document,
                image_cache,
                doc_name=context.doc_name or context.source_path.stem,
                model=context.model,
            )
        )

    def _extract_outline(self, body_items, context: PipelineContext):
        return extract_docx_nodes(body_items, context.doc_name or context.source_path.stem)

    def _extract_raw_blocks(self, body_items):
        return extract_docx_blocks(body_items)

    def _build_tree(self, flat_nodes):
        return build_tree_from_nodes(flat_nodes)

    def _assign_node_ids(self, tree_structure):
        # Always assign node ids — the block→node link in metadata depends on
        # them. The ``if_add_node_id`` option only controls whether the id is
        # *visible* in the final structure (handled by the order list in
        # ``_apply_visibility_order``).
        write_node_id(tree_structure)

    async def _maybe_enrich_with_summaries(self, tree_structure, context: PipelineContext):
        if context.options.if_add_node_summary != "yes":
            return
        await generate_summaries_for_markdown_structure(
            tree_structure,
            summary_token_threshold=context.options.summary_token_threshold,
            model=context.model,
        )

    def _finalize_blocks(self, raw_blocks, tree_structure, context: PipelineContext):
        return finalize_word_blocks(raw_blocks, tree_structure, model=context.model)

    def _maybe_generate_doc_description(self, tree_structure, context: PipelineContext):
        if context.options.if_add_doc_description != "yes":
            return None
        return generate_doc_description(
            create_clean_structure_for_description(tree_structure),
            model=context.model,
        )

    def _apply_visibility_order(self, tree_structure, context: PipelineContext):
        order = self._build_visibility_order(context)
        return format_structure(tree_structure, order=order)

    def _build_visibility_order(self, context: PipelineContext) -> list[str]:
        order: list[str] = ["title"]
        if context.options.if_add_node_id == "yes":
            order.append("node_id")
        if context.options.if_add_node_summary == "yes":
            order.extend(["summary", "prefix_summary"])
            if context.options.if_add_node_text == "yes":
                order.append("text")
        elif context.options.if_add_node_text == "yes":
            order.append("text")
        order.extend(["line_num", "start_index", "end_index", "nodes"])
        return order

    def _resolve_doc_name(self, context: PipelineContext) -> str:
        return context.source_path.stem
