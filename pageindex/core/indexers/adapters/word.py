from __future__ import annotations

from pageindex.core.indexers.pipeline.context import PipelineContext
from pageindex.core.indexers.pipeline.step_01_outline_discovery import extract_docx_nodes, require_word_document
from pageindex.core.indexers.pipeline.step_03_tree_construction import build_tree_from_nodes
from pageindex.core.indexers.pipeline.step_05_enrichment import (
    create_clean_structure_for_description,
    format_structure,
    generate_doc_description,
    generate_summaries_for_markdown_structure,
)
from pageindex.core.indexers.pipeline.step_06_finalize import build_index_result
from pageindex.core.utils.tree import write_node_id


class WordAdapter:
    async def build(self, context: PipelineContext):
        WordDocument = require_word_document()
        path = context.source_path

        document = WordDocument(str(path))
        flat_nodes = extract_docx_nodes(document, context.doc_name or path.stem)
        tree_structure = build_tree_from_nodes(flat_nodes)

        if context.options.if_add_node_id == "yes":
            write_node_id(tree_structure)

        if context.options.if_add_node_summary == "yes":
            tree_structure = format_structure(
                tree_structure,
                order=["title", "node_id", "summary", "prefix_summary", "text", "line_num", "nodes"],
            )
            tree_structure = await generate_summaries_for_markdown_structure(
                tree_structure,
                summary_token_threshold=context.options.summary_token_threshold,
                model=context.model,
            )
            if context.options.if_add_node_text == "no":
                tree_structure = format_structure(
                    tree_structure,
                    order=["title", "node_id", "summary", "prefix_summary", "line_num", "nodes"],
                )
        elif context.options.if_add_node_text == "yes":
            tree_structure = format_structure(
                tree_structure,
                order=["title", "node_id", "text", "line_num", "nodes"],
            )
        else:
            tree_structure = format_structure(
                tree_structure,
                order=["title", "node_id", "line_num", "nodes"],
            )

        doc_description = None
        if context.options.if_add_doc_description == "yes":
            doc_description = generate_doc_description(
                create_clean_structure_for_description(tree_structure),
                model=context.model,
            )

        return build_index_result(doc_name=path.stem, structure=tree_structure, doc_description=doc_description)
